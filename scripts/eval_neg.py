"""反事实“无问题”评测：模型在已无问题的小节上应该不出意见。
Usage: python3 -I eval_neg.py --inputs data/eval/audit_dev_neg.jsonl --pred <pred.jsonl> --name <name> [--out data/eval] [--pos-pred <对应正例预测>]
指标：可解析率、沉默率（findings 为空的样本占比）、平均意见数/样本、误报样本明细。
给了 --pos-pred（同一模型在对应正例 audit_<dev|test>.jsonl 上的预测）时，另算“改动敏感度”：正例有意见、反事实无意见的样本占比。"""
import argparse, json, os, re, difflib, collections
ap = argparse.ArgumentParser()
ap.add_argument('--inputs', required=True); ap.add_argument('--pred', required=True); ap.add_argument('--name', required=True); ap.add_argument('--out', default='data/eval')
ap.add_argument('--pos-pred'); a = ap.parse_args()
def parse(t):
    t = (t or '').split('</think>')[-1].strip(); i = t.find('{')
    try: return json.JSONDecoder().raw_decode(t[i:])[0]
    except Exception: return None
inp = {r['id']: r for r in map(json.loads, open(a.inputs, encoding='utf-8'))}
pred = {r['id']: r for r in map(json.loads, open(a.pred, encoding='utf-8'))}
pos = {r['id']: r for r in map(json.loads, open(a.pos_pred, encoding='utf-8'))} if a.pos_pred else {}
squash = lambda s: re.sub(r'\s+', '', s or '')
bigrams = lambda s: collections.Counter(s[i:i + 2] for i in range(len(s) - 1))
def recall(g, p):
    g, p = bigrams(squash(g)), bigrams(squash(p)); return sum((g & p).values()) / max(1, sum(g.values()))
def quote_hit(x, y):
    x, y = squash(x), squash(y)
    if not x or not y: return False
    m = difflib.SequenceMatcher(None, x, y, autojunk=False).find_longest_match(0, len(x), 0, len(y))
    return m.size >= 10 and m.size >= 0.5 * min(len(x), len(y))
def same_finding(g, p):
    """预测意见 p 是否重提了被改掉的意见 g：文本召回 ≥0.4，或 规则相同且证据引文重合（与 eval_score 的综合命中同口径）。"""
    gq = [e.get('quote', '') for e in g.get('evidence') or []]; pq = [e.get('quote', '') for e in p.get('evidence') or []]
    ev = bool(gq) and sum(any(quote_hit(x, y) for y in pq) for x in gq) / len(gq) >= 0.5
    return recall((g.get('problem') or '') + (g.get('suggestion') or ''), (p.get('problem') or '') + (p.get('suggestion') or '')) >= 0.4 or (g.get('rule_id') == p.get('rule_id') and ev)
n = ok = silent = nf = flip = flip_n = rep_n = rep_hit = 0; fp = []
for i, r in inp.items():
    n += 1; o = parse((pred.get(i) or {}).get('output')); 
    if not o or not isinstance(o.get('findings'), list): continue
    ok += 1; F = o['findings']; nf += len(F); silent += not F
    dr = r['meta'].get('dropped')
    if dr:
        rep_n += 1; hit = any(isinstance(f, dict) and same_finding(dr, f) for f in F); rep_hit += hit
        if hit: fp.append(dict(id=i, repeated=dr.get('issue_type'), rule=dr.get('rule_id')))
        continue
    if F: fp.append(dict(id=i, n=len(F), types=[f.get('issue_type') for f in F], rules=[f.get('rule_id') for f in F]))
    base = r['meta'].get('base_sample') or i.replace('CF', '')
    pp = parse((pos.get(base) or {}).get('output')) if pos else None
    if pp and isinstance(pp.get('findings'), list):
        flip_n += 1; flip += bool(pp['findings']) and not F
res = dict(name=a.name, samples=n, parse_rate=ok / max(1, n))
if rep_n: res.update(repeat_fixed_finding_rate=rep_hit / rep_n, partial_samples=rep_n)      # 局部修正集：重提已改掉的意见的比例（越低越好）
else: res.update(silence_rate=silent / max(1, ok), findings_per_sample=nf / max(1, ok))
if pos: res.update(positives_compared=flip_n, flip_to_silent=flip / max(1, flip_n))
res['false_positive_samples'] = fp
json.dump(res, open(os.path.join(a.out, f'neg_{a.name}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in res.items() if k != 'false_positive_samples'})
