"""拒绝采样（RFT）样本构建：用模型在“没见过这些项目”的情况下采样的输出，替换通过核验的专家样本。
Usage: python3 -I build_rft_samples.py <data_dir> --pool pool_a.jsonl:eval_out/pool_a_c50e3.jsonl [--pool ...] [--out out_rft]
核验（一个采样输出全部通过才算“干净正确”）：
  1. JSON 可解析，findings 条数 = 标准意见条数，且与标准意见一一对应命中（文本召回 ≥0.4，或 规则相同且命中一半以上标准引文）；不含任何没匹配的额外意见
  2. 所有引文逐字出现在输入里；条文编号都在输入的【条文】里；规则编号在【审核重点】里；意见文字不含条文编号
  3. 思考：不循环，长度 300~4000 字，不把“专家”当作意见来源，表号/附件号/页码都在输入或意见里，算式经 check_arith 核验
替换规则：某输入有干净正确输出 → 用它（多个时取引文覆盖标准引文最多的）作训练目标；否则保留专家原样本。没有采样结果的项目（c25 训练过的 26 个）保持原样。
输出 <out>/samples.jsonl（与 out/samples.jsonl 同格式，替换处 meta.rft=True）、report.txt、preview.md、tiers.jsonl（每条标准意见被几次采样命中，供样本分层用）。"""
import sys, os, re, json, difflib, collections, random, runpy
D = sys.argv[1]; args = sys.argv[2:]
pools = [a.split(':') for i, a in enumerate(args) if i and args[i - 1] == '--pool']; OUT = os.path.join(D, args[args.index('--out') + 1] if '--out' in args else 'out_rft'); os.makedirs(OUT, exist_ok=True)
CHK = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'checks.py')); check_arith = CHK['check_arith']
squash = lambda s: re.sub(r'\s+', '', s or '')
bg = lambda s: collections.Counter(s[i:i + 2] for i in range(len(s) - 1))
def recall(g, p):
    g, p = bg(squash(g)), bg(squash(p)); return sum((g & p).values()) / max(1, sum(g.values()))
def qh(x, y):
    x, y = squash(x), squash(y)
    if not x or not y: return False
    m = difflib.SequenceMatcher(None, x, y, autojunk=False).find_longest_match(0, len(x), 0, len(y)).size
    return m >= 10 and m >= 0.5 * min(len(x), len(y))
Q = lambda f: [e.get('quote', '') for e in (f.get('evidence') or []) if isinstance(e, dict)]
T = lambda f: (f.get('problem') or '') + (f.get('suggestion') or '')
ID_RE = re.compile(r'\b(P\d+(?:-[A-Za-z0-9]+)+)\b')
SRC_EXPERT = re.compile(r'专家(?:们)?(?:另|也|还)?(?:要求|所提|提到|引用|称|指出|质疑|认为|意见|表述|所指|所述|按原|所引|提出|建议|关于|明确|在意见|的意见|原话|所称|所说|指定|要点|已提出|已采纳|曾提)')
ENT_REF = re.compile(r'(?<![代图])表\s?\d+(?:[-－—]\d+)*|附件\s?\d+|第\s?\d+\s?页')
def parse(t):
    t = (t or '').split('</think>')[-1].strip(); i = t.find('{')
    try: return json.JSONDecoder().raw_decode(t[i:])[0]
    except Exception: return None
def hit(g, f):
    gq = Q(g); ev = bool(gq) and sum(any(qh(x, y) for y in Q(f)) for x in gq) / len(gq) >= 0.5
    return recall(T(g), T(f)) >= 0.4 or (g.get('rule_id') == f.get('rule_id') and ev)
def loopish(t, w=20, rep=6):
    c = collections.Counter(t[i:i + w] for i in range(0, max(0, len(t) - w)))
    return any(v >= rep for v in c.values())
def matched(gold, F):
    """findings 与标准意见一一对应（简单二分匹配）。"""
    if len(gold) != len(F): return None
    cand = [[j for j, f in enumerate(F) if hit(g, f)] for g in gold]; owner = {}
    def try_(i, seen):
        for j in cand[i]:
            if j in seen: continue
            seen.add(j)
            if j not in owner or try_(owner[j], seen): owner[j] = i; return True
        return False
    return owner if all(try_(i, set()) for i in range(len(gold))) else None
def check(o, gold, prompt):
    reasons = []
    th, _, js = o.partition('</think>'); th = th.replace('<think>', '').strip()
    ob = parse(o)
    if not isinstance(ob, dict) or not isinstance(ob.get('findings'), list) or not all(isinstance(f, dict) for f in ob['findings']): return None, ['不可解析'], th
    F = ob['findings']; hay = squash(prompt)
    if matched(gold, F) is None: reasons.append('意见与标准意见不一一对应（有漏或有额外）')
    if any(not Q(f) or any(squash(q) not in hay for q in Q(f)) for f in F): reasons.append('引文非逐字或无引文')
    cl = set(ID_RE.findall(prompt.split('【条文】')[-1].split('【审核重点】')[0])); foc = prompt.split('【审核重点】')[-1].split('【任务】')[0]
    if any(c not in cl for f in F for c in (f.get('clause_ids') or [])): reasons.append('条文编号不在输入里')
    if any(f.get('rule_id') and f['rule_id'] not in foc for f in F): reasons.append('规则不在审核重点里')
    if any(ID_RE.search(T(f)) for f in F): reasons.append('意见含条文编号')
    if any(len(T(f)) > 400 for f in F): reasons.append('意见过长')
    if loopish(th): reasons.append('思考循环')
    if not 300 <= len(th) <= 4000: reasons.append('思考长度不合规')
    if SRC_EXPERT.search(th): reasons.append('思考把专家当来源')
    rendered = json.dumps(ob, ensure_ascii=False)
    for e in set(ENT_REF.findall(th)):
        if squash(e) not in hay and squash(e) not in squash(rendered): reasons.append('思考引用的表号/页码不在输入里'); break
    e_ar, _ = check_arith(th, prompt)
    if e_ar: reasons.append('算式核验不通过')
    return ob, reasons, th
orig = {}
for l in open(os.path.join(D, 'out/samples.jsonl'), encoding='utf-8'):
    r = json.loads(l); orig[r['id']] = r
random.seed(0); rep, why, tiers, cover = {}, collections.Counter(), [], collections.Counter()
nin = 0
for inp_f, pred_f in pools:
    inp = {r['id']: r for r in map(json.loads, open(os.path.join(D, 'pool', inp_f), encoding='utf-8'))}
    for line in open(os.path.expanduser(pred_f) if pred_f.startswith(('~', '/')) else os.path.join(D, pred_f), encoding='utf-8'):
        p = json.loads(line); r = inp.get(p['id'])
        if not r: continue
        nin += 1; gold = (parse(r['gold']) or {}).get('findings', []); outs = p.get('outputs') or [p['output']]
        cands = []; hits_per_gold = [0] * len(gold)
        for k, o in enumerate(outs):
            ob, reasons, th = check(o or '', gold, r['prompt'])
            if ob is not None:
                for gi, g in enumerate(gold): hits_per_gold[gi] += any(hit(g, f) for f in ob['findings'] if isinstance(f, dict))
            if ob is None or reasons:
                for x in reasons[:1]: why[x] += 1
                continue
            gq = [q for g in gold for q in Q(g)]
            cov = sum(any(qh(x, q) for f in ob['findings'] for q in Q(f)) for x in gq) / max(1, len(gq))
            cands.append((cov, -len(th), random.random(), k, ob, th))
        tiers.append(dict(id=p['id'], project=r['project'], hits=hits_per_gold, n=len(outs)))
        if cands:
            cov, _, _, k, ob, th = max(cands); rep[p['id']] = (k, ob, th, cov, len(cands), pred_f.split('/')[-1])
out = []
for i, r in orig.items():
    if i in rep:
        k, ob, th, cov, nc, src = rep[i]; r = json.loads(json.dumps(r))
        r['messages'][1]['content'] = '<think>\n' + th + '\n</think>\n' + json.dumps(ob, ensure_ascii=False)
        r['meta'].update(rft=True, rft_source=src, rft_candidates=nc, rft_evidence_coverage=round(cov, 2), reasoning_author='模型采样（' + src.split('_')[-1].split('.')[0] + '），与专家意见逐条核验一致', notes=(r['meta'].get('notes') or '') + '；RFT：训练目标为模型采样输出（通过核验）')
        r['meta']['_expert_content'] = orig[i]['messages'][1]['content']
    out.append(r)
with open(os.path.join(OUT, 'samples.jsonl'), 'w', encoding='utf-8') as fo:
    for r in out:
        r2 = dict(r); r2['meta'] = {k: v for k, v in r['meta'].items() if k != '_expert_content'}; fo.write(json.dumps(r2, ensure_ascii=False) + '\n')
with open(os.path.join(OUT, 'tiers.jsonl'), 'w', encoding='utf-8') as fo:
    for t in tiers: fo.write(json.dumps(t, ensure_ascii=False) + '\n')
rl = [r for r in out if r['meta'].get('rft')]
nf = sum(len(json.loads(r['messages'][1]['content'].split('</think>')[-1])['findings']) for r in rl)
tg = collections.Counter(h for t in tiers for h in t['hits']); tot_g = sum(tg.values())
stable = sum(v for k, v in tg.items() if k >= 4); unstable = sum(v for k, v in tg.items() if 1 <= k <= 3); never = tg.get(0, 0)
rl_rules = collections.Counter(json.loads(r['messages'][1]['content'].split('</think>')[-1])['findings'][0]['rule_id'] for r in rl)
allr = collections.Counter()
for r in orig.values():
    try: [allr.update([f['rule_id']]) for f in json.loads(r['messages'][1]['content'].split('</think>')[-1])['findings']]
    except Exception: pass
lines = [f'采样输入 {nin} 个（{len({t["project"] for t in tiers})} 个项目）；通过核验可替换的 {len(rl)} 个（{len(rl) / nin:.0%}），涉及 {nf} 条意见；其余 {len(orig) - len(rl)} 条样本保持专家原样',
         '未通过的第一原因（每个输出只计第一个原因）：' + str(dict(why.most_common())),
         f'标准意见 {tot_g} 条：被 ≥4/5 次采样命中 {stable}（{stable / tot_g:.0%}），1~3 次 {unstable}（{unstable / tot_g:.0%}），0 次 {never}（{never / tot_g:.0%}）']
open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8').write('\n'.join(lines)); print('\n'.join(lines))
random.seed(1)
with open(os.path.join(OUT, 'preview.md'), 'w', encoding='utf-8') as fo:
    for r in random.sample(rl, min(6, len(rl))):
        fo.write(f"## {r['id']}（引文覆盖 {r['meta']['rft_evidence_coverage']}，候选 {r['meta']['rft_candidates']} 个）\n\n**专家样本（结尾）**\n\n```\n{r['meta']['_expert_content'][-700:]}\n```\n\n**模型采样（替换后，结尾）**\n\n```\n{r['messages'][1]['content'][-700:]}\n```\n\n---\n\n")
