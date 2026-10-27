"""意见复核打分。Usage: python3 -I eval_judge.py --inputs data/eval_v2/judge_dev.jsonl --pred <pred.jsonl>
指标：verdict 三分类准确率；A（用户判定过的 e3 额外意见）：不采纳/次要不写的召回（能拦下多少）、成立意见被误拦率；B（专家意见）：被误拦率；
按“采纳 vs 不采纳+次要不写”二分类给出 precision/recall；reason_type 在不采纳里的准确率。"""
import argparse, json, collections
ap = argparse.ArgumentParser(); ap.add_argument('--inputs', required=True); ap.add_argument('--pred', required=True); a = ap.parse_args()
I = [json.loads(l) for l in open(a.inputs, encoding='utf-8')]; P = {r['id']: r for r in map(json.loads, open(a.pred, encoding='utf-8'))}
def parse(t):
    t = (t or '').split('</think>')[-1]; i = t.find('{')
    try: return json.JSONDecoder().raw_decode(t[i:])[0]
    except Exception: return None
n = collections.Counter(); conf = collections.Counter(); rt_ok = rt_n = 0
for r in I:
    p = P.get(r['id']); o = parse(p['output']) if p else None; m = r['meta']; pv = (o or {}).get('verdict'); n['total'] += 1
    if o is None: n['unparsed'] += 1
    conf[(m['kind'], m['verdict'], pv)] += 1
    if pv == m['verdict']: n['verdict_ok'] += 1
    if m['verdict'] == '不采纳':
        rt_n += 1; rt_ok += (o or {}).get('reason_type') == m['reason_type']
tot = lambda k, v: sum(c for (kk, vv, _), c in conf.items() if kk == k and vv == v)
hit = lambda k, v, pred: sum(c for (kk, vv, pp), c in conf.items() if kk == k and vv == v and pp in pred)
print(f"总 {n['total']}，不可解析 {n['unparsed']}，三分类准确率 {n['verdict_ok'] / n['total']:.1%}")
print(f"A 不采纳 {tot('A额外意见', '不采纳')} 条：判为不采纳 {hit('A额外意见', '不采纳', ['不采纳'])}，判为不采纳或次要不写 {hit('A额外意见', '不采纳', ['不采纳', '次要不写'])}")
print(f"A 次要 {tot('A额外意见', '次要不写')} 条：判为次要不写 {hit('A额外意见', '次要不写', ['次要不写'])}，判为不采纳或次要不写 {hit('A额外意见', '次要不写', ['不采纳', '次要不写'])}")
print(f"A 成立 {tot('A额外意见', '采纳')} 条：判为采纳 {hit('A额外意见', '采纳', ['采纳'])}（误拦 {tot('A额外意见', '采纳') - hit('A额外意见', '采纳', ['采纳'])}）")
print(f"B 专家意见 {tot('B专家意见', '采纳')} 条：判为采纳 {hit('B专家意见', '采纳', ['采纳'])}（误拦率 {1 - hit('B专家意见', '采纳', ['采纳']) / max(1, tot('B专家意见', '采纳')):.1%}）")
print(f"不采纳的原因类型准确率 {rt_ok}/{rt_n}")
