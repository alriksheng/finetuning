"""T2 试点：把盲审结果与专家意见逐条对齐，输出每条专家意见的状态（命中 / 引文对规则不同 / 仅规则相同 / 漏报）和每条盲审意见是否匹配（疑似误报）。
对齐口径与 eval_score.py 一致（综合命中 = 文本召回≥0.4，或 规则相同且引文命中）。
Usage: python3 -I pilot_align.py <inputs.jsonl> <pred.jsonl> <out_dir>"""
import sys, os, json, re, difflib, collections
inp, prd, out = sys.argv[1:4]
squash = lambda s: re.sub(r'\s+', '', s or '')
bigr = lambda s: collections.Counter(s[i:i + 2] for i in range(len(s) - 1))
def recall(g, p):
    a, b = bigr(squash(g)), bigr(squash(p)); return sum((a & b).values()) / max(1, sum(a.values()))
def qhit(g, p):
    g, p = squash(g), squash(p)
    if not g or not p: return False
    m = difflib.SequenceMatcher(None, g, p, autojunk=False).find_longest_match(0, len(g), 0, len(p)); return m.size >= 10 and m.size >= 0.5 * min(len(g), len(p))
qs = lambda f: [e.get('quote', '') for e in f.get('evidence') or []]
ft = lambda f: (f.get('problem') or '') + (f.get('suggestion') or '')
def parse(t):
    try: return json.loads(t.split('</think>')[-1].strip())
    except Exception: return {'findings': []}
I = {r['id']: r for r in map(json.loads, open(inp, encoding='utf-8'))}; P = {r['id']: r for r in map(json.loads, open(prd, encoding='utf-8'))}
rows, st, byrule = [], collections.Counter(), collections.defaultdict(collections.Counter)
for id_, r in I.items():
    G = parse(r['gold'])['findings']; F = parse(P[id_]['output'])['findings']; used = set()
    for gi, g in enumerate(G):
        gq = qs(g); best = None
        for pj, p in enumerate(F):
            rh = g['rule_id'] == p['rule_id']; eh = bool(gq) and sum(any(qhit(x, y) for y in qs(p)) for x in gq) / len(gq) >= 0.5
            anyq = any(qhit(x, y) for x in gq for y in qs(p)); tr = recall(ft(g), ft(p))
            sc = (rh and eh) * 2 + (tr >= 0.4) * 2 + rh * 0.5 + anyq * 0.5 + tr
            if best is None or sc > best[0]: best = (sc, pj, rh, eh, anyq, tr)
        if best is None: status = '漏报'; pj = None
        else:
            _, pj, rh, eh, anyq, tr = best
            if tr >= 0.4 or (rh and eh): status = '命中'
            elif anyq and not rh: status = '引文对规则不同'
            elif rh and anyq: status = '规则相同引文部分重合'
            elif rh: status = '仅规则相同'
            else: status = '漏报'
        if status == '命中': used.add(pj)
        else: pj = pj if status in ('引文对规则不同', '规则相同引文部分重合') else None
        st[status] += 1; byrule[g['rule_id']][status] += 1
        rows.append(dict(id=id_, project=r['project'], gold_idx=gi, gold_rule=g['rule_id'], status=status, pred_idx=pj, pred_rule=F[pj]['rule_id'] if pj is not None else None))
    extra = [j for j in range(len(F)) if j not in used]
    for j in extra: rows.append(dict(id=id_, project=r['project'], status='盲审多出', pred_idx=j, pred_rule=F[j]['rule_id']))
    st['盲审多出'] += len(extra)
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, 'align.jsonl'), 'w', encoding='utf-8') as f:
    for x in rows: f.write(json.dumps(x, ensure_ascii=False) + '\n')
n = sum(v for k, v in st.items() if k != '盲审多出')
lines = ['状态\t条数\t占专家意见', *[f'{k}\t{v}\t{v / n:.1%}' for k, v in st.items() if k != '盲审多出'], f'盲审多出\t{st["盲审多出"]}\t（{st["盲审多出"] / len(I):.2f} 条/样本）', '', '按专家意见的规则：规则\t命中\t引文对规则不同\t其他']
for k, c in sorted(byrule.items(), key=lambda x: -sum(x[1].values())):
    t = sum(c.values()); lines.append(f'{k}\t{c["命中"]}/{t}\t{c["引文对规则不同"]}\t{t - c["命中"] - c["引文对规则不同"]}')
open(os.path.join(out, 'align_report.txt'), 'w', encoding='utf-8').write('\n'.join(lines)); print('\n'.join(lines))
