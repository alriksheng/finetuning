"""易混规则合并后的“上限”诊断。Usage: python3 -I diag_rule_groups.py --inputs data/eval/audit_dev.jsonl --pred a.jsonl [--pred b.jsonl ...]
把规则编号按分组映射后再算：规则命中、综合命中（文本命中，或 同组规则且引文达到一半重合）、
以及“预测意见与标准意见引文有重合的配对中，规则编号一致的比例”。
分组 0 = 原口径；1 = 只合并实测的易混对；2 = 按大类合并。结果是上限：它回答“如果把易混规则不当错误，命中率最多能多多少”，不代表真实提升。"""
import argparse, json, re, difflib, collections
ap = argparse.ArgumentParser(); ap.add_argument('--inputs', required=True); ap.add_argument('--pred', action='append', required=True); a = ap.parse_args()
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
def parse(t):
    t = (t or '').split('</think>')[-1].strip(); i = t.find('{')
    try: return json.JSONDecoder().raw_decode(t[i:])[0]
    except Exception: return None
PAIRS = [{'R-BASE-INDICATOR', 'R-BASE-BASIS', 'L3-07'}, {'R-REDUCE-CALC', 'R-REDUCE-VIS', 'R-STD-LINK'}, {'R-COST-PRICE', 'R-COST-CHECK'},
         {'R-BASIC-BUDGET', 'R-BASIC-CONTENT', 'R-SCOPE'}, {'R-PROC-PURCHASE', 'R-PROC-FLOW'}]
def fam(r):
    if r in ('L3-07',) or r.startswith('R-BASE'): return 'BASE'
    if r.startswith(('R-BASIC', 'R-SCOPE', 'R-NEW')): return 'BASIC'
    if r.startswith('R-COST'): return 'COST'
    if r.startswith('R-PROC'): return 'PROC'
    if r.startswith(('R-REDUCE', 'R-STD')): return 'REDUCE'
    if r.startswith('R-POL'): return 'POL'
    return r
def gmap(level, r):
    if level == 0 or not r: return r
    if level == 2: return fam(r)
    for g in PAIRS:
        if r in g: return 'G:' + '+'.join(sorted(g))
    return r
inp = {r['id']: r for r in map(json.loads, open(a.inputs, encoding='utf-8'))}
print(f'{"预测文件":38s} 分组  规则命中  综合命中  引文对上时规则一致')
for pf in a.pred:
    P = {r['id']: r for r in map(json.loads, open(pf, encoding='utf-8'))}
    for lv in (0, 1, 2):
        G = rh = cov = 0; qa = qb = 0
        for i, r in inp.items():
            gold = (parse(r['gold']) or {}).get('findings', []); out = parse((P.get(i) or {}).get('output')) or {}
            F = [f for f in out.get('findings', []) if isinstance(f, dict)] if isinstance(out, dict) else []
            for g in gold:
                G += 1; gr = gmap(lv, g.get('rule_id')); gq = Q(g)
                rh += any(gmap(lv, f.get('rule_id')) == gr for f in F)
                def ev(f): return bool(gq) and sum(any(qh(x, y) for y in Q(f)) for x in gq) / len(gq) >= 0.5
                cov += any(recall(T(g), T(f)) >= 0.4 or (gmap(lv, f.get('rule_id')) == gr and ev(f)) for f in F)
                for f in F:
                    if any(qh(x, y) for x in gq for y in Q(f)):
                        qa += 1; qb += gmap(lv, f.get('rule_id')) == gr
        print(f'{pf.split("/")[-1][:38]:38s} {lv}     {rh / G:6.1%}   {cov / G:6.1%}    {qb}/{qa} = {qb / max(1, qa):.0%}')
