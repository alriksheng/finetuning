"""T1 整理版：只改格式，不改意见内容来源（新实验组方案_盲审重建.md 第 3 节）。
对每条审核样本：
  1. 意见按首条证据在输入中的位置排序（JSON 和思考同步）；
  2. JSON 字段顺序改为 evidence 在前；
  3. 思考改为“每条意见一段”：摘录（程序按该条意见的证据引文生成）→ 核对（取自原思考中与该条对应的段落）→ 归类（规则 + 易混规则判别句）；
  4. 保留原“定位/比对”开头、“条文”行；“结论”里“一是…二是…”条数与意见数一致时按新顺序重排。
原思考的文字不改写，只切分、归位；对应不上的意见写“与意见 k 同依据”，并记入报告。
Usage: python3 -I build_t1.py <data_dir> [src=out/samples.jsonl] [dst=out_t1/samples.jsonl]"""
import sys, os, json, re, yaml, collections, itertools
D = sys.argv[1]
src = os.path.join(D, sys.argv[2] if len(sys.argv) > 2 else 'out/samples.jsonl')
dst = os.path.join(D, sys.argv[3] if len(sys.argv) > 3 else 'out_t1/samples.jsonl')
os.makedirs(os.path.dirname(dst), exist_ok=True)
R = {r['rule_id']: r for r in yaml.safe_load(open(os.path.join(D, 'rules/rules.yaml'), encoding='utf-8'))}
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
spec = importlib.util.spec_from_file_location('acs', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'add_classification_step.py'))
# DIS 表直接复用 add_classification_step.py 里的判别句（避免两处维护）：只取字典，不执行主流程
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'add_classification_step.py'), encoding='utf-8').read()
_m = re.search(r'^DIS = \{.*?^\}', _src, re.S | re.M)
DIS = eval(_m.group(0)[len('DIS = '):])
tg = lambda r: f"“{R[r]['tag']}”（{r}）" if r in R else r
ORDER = ['evidence', 'issue_type', 'rule_id', 'verdict', 'clause_ids', 'basis_type', 'problem', 'suggestion', 'part']
HEAD = re.compile(r'^(定位|比对|核对[一二三四五六七八九十]?|规则判断|条文|结论|判断|问题[一二三四五六七八九十]|要点[一二三四五六七八九十]|复核|逐项核对|关联)(?=[：:（(])')


def grams(s, n=3):
    s = re.sub(r'\s+', '', s); return {s[i:i + n] for i in range(len(s) - n + 1)}


def split_blocks(t):
    blocks = []
    for l in t.split('\n'):
        if HEAD.match(l) or not blocks: blocks.append([l])
        else: blocks[-1].append(l)
    return ['\n'.join(b).strip() for b in blocks]


def first_pos(f, prompt):
    ps = [prompt.find(q['quote']) for q in f['evidence'] if q.get('quote')]
    ps = [p for p in ps if p >= 0]
    return min(ps) if ps else 10 ** 9


def conclusion_reorder(s, perm):
    """s: 结论正文；perm[new_i]=该位置对应的原结论条序号。按“X是”切分，条数与意见数一致才重排。"""
    pos = [m.start() for m in re.finditer(r'[一二三四五六七八九十]是', s)]
    if len(pos) != len(perm) or pos[0] != 0 and s[:pos[0]].strip(): return None
    segs = [s[pos[i]:pos[i + 1] if i + 1 < len(pos) else None][2:].strip().rstrip('；;。') for i in range(len(pos))]
    num = '一二三四五六七八九十'
    return '；'.join(f'{num[i]}是{segs[perm[i]]}' for i in range(len(perm))) + '。'


stat = collections.Counter(); log = []
out = []
for line in open(src, encoding='utf-8'):
    r = json.loads(line); stat['总数'] += 1
    prompt = r['messages'][0]['content']; asst = r['messages'][1]['content']
    if r['meta'].get('task_type') not in ('小节审核', '比对包') or '</think>' not in asst:
        out.append(r); stat['不处理'] += 1; continue
    th, js = asst.split('</think>', 1)
    try: obj = json.loads(js.strip())
    except Exception: out.append(r); stat['JSON不可解析'] += 1; continue
    F = obj.get('findings') or []
    if not F: out.append(r); stat['无意见'] += 1; continue
    blocks = split_blocks(th.replace('<think>', '').strip())
    pre = [b for b in blocks if re.match(r'^(定位|比对)', b)]
    cl = [b for b in blocks if b.startswith('条文')]
    cc = [b for b in blocks if b.startswith('结论')]
    mid = [b for b in blocks if b not in pre + cl + cc]
    nf = len(F)
    # ---- 段落 → 意见 ----
    fg = [grams(' '.join(q['quote'] for q in f['evidence']) + f.get('problem', '') + f.get('suggestion', '')) for f in F]
    gm = [grams(b) for b in mid]
    sc = [[len(g & x) / max(1, (len(g) * len(x)) ** 0.5) for x in fg] for g in gm]
    am = [max(range(nf), key=lambda i: s[i]) for s in sc]
    if len(mid) == nf and nf <= 7:                                   # 段数 = 意见数：一一对应，取总重合最大的指派
        owner = list(max(itertools.permutations(range(nf)), key=lambda pm: sum(sc[j][pm[j]] for j in range(nf))))
        stat['段数=意见数'] += 1
        if owner != list(range(nf)): stat['  其中段落顺序与意见顺序不同'] += 1
    else:
        owner = am; stat['段数≠意见数'] += 1
    para = collections.defaultdict(list)
    for b, k in zip(mid, owner): para[k].append(b)
    share = {}
    for k in range(nf):
        if k not in para:                                            # 没有对应段落：借用重合最高的段落所属的意见
            if mid:
                j = max(range(len(mid)), key=lambda j: sc[j][k]); share[k] = owner[j]
            stat['意见无对应段落'] += 1; log.append(('无对应段落', r['id'], k))
    # ---- 排序 ----
    pos = [first_pos(f, prompt) for f in F]
    order = sorted(range(nf), key=lambda i: (pos[i], i))
    if order != list(range(nf)): stat['发生重排'] += 1
    newno = {old: new + 1 for new, old in enumerate(order)}
    # ---- 思考 ----
    seen = {}
    lines = [p for p in pre]
    for new, old in enumerate(order, 1):
        f = F[old]; q = f['evidence']
        ex = '；'.join(f"“{e['quote']}”（{e['source']}｜{e['loc']}）" for e in q)
        seg = [f"意见{new}（{f.get('issue_type') or '—'}）：", f"摘录：{ex}"]
        ps = para.get(old, [])
        if ps:
            clean = [re.sub(r'^(核对[一二三四五六七八九十]?|问题[一二三四五六七八九十]|要点[一二三四五六七八九十]|规则判断)(（[^）]*）)?[：:]\s*', '', p) for p in ps]
            if len(clean) == 1: seg.append('核对：' + clean[0])
            else: seg += [f'核对（{i}）：' + c for i, c in enumerate(clean, 1)]
        elif old in share:
            seg.append(f'核对：与意见{newno[share[old]]}所依据的内容相同，见该条。')
        rid = f.get('rule_id'); head = f'归类：属于{tg(rid)}'
        if rid in seen: seg.append(head + f'，判别同意见{seen[rid]}。')
        else:
            seen[rid] = new
            seg.append(head + ('：' + DIS[rid] if rid in DIS else (f"，关注的问题是：{R[rid]['question']}。" if rid in R else '。')))
        lines.append('\n'.join(seg))
    lines += cl
    if cc:
        body = re.sub(r'^结论[：:]\s*', '', cc[0])
        if order != list(range(nf)):
            if len(mid) == nf and nf <= 7:                              # 结论条序随思考段落顺序：意见 old 的段落序号 = owner 中取值为 old 的位置
                cperm = [owner.index(old) for old in order]
            else: cperm = order
            nb = conclusion_reorder(body, cperm)
            if nb is None: stat['结论未重排'] += 1; nb = body
            else: stat['结论已重排'] += 1
            body = nb
        lines.append('结论：' + body)
    # ---- JSON ----
    newF = []
    for old in order:
        f = F[old]; d = {k: f[k] for k in ORDER if k in f}; d.update({k: v for k, v in f.items() if k not in d}); newF.append(d)
    obj2 = dict(obj); obj2['findings'] = newF
    r['messages'][1]['content'] = '<think>\n' + '\n'.join(lines) + '\n</think>\n' + json.dumps(obj2, ensure_ascii=False)
    r['meta']['format'] = 't1'; stat['已处理'] += 1
    out.append(r)

with open(dst, 'w', encoding='utf-8') as fo:
    for r in out: fo.write(json.dumps(r, ensure_ascii=False) + '\n')
rep = [f'{k}\t{v}' for k, v in stat.items()] + [''] + [str(x) for x in log[:200]]
open(os.path.join(os.path.dirname(dst), 'report.txt'), 'w', encoding='utf-8').write('\n'.join(rep))
print('\n'.join(rep[:len(stat)]))
