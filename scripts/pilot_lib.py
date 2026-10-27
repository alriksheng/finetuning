"""T2 试点辅助：把盲审结果（每条意见的核对/判断文字 + findings）拼成“思考 + JSON”，并校验引文逐字出现在输入中。
用法（交互式盲审时 import）：from pilot_lib import add; add(id, locate, items)。"""
import json, os, re, yaml, sys
D = '/Users/alrik/Documents/Finetuning/data'
R = {r['rule_id']: r for r in yaml.safe_load(open(f'{D}/rules/rules.yaml', encoding='utf-8'))}
_src = open('/Users/alrik/Documents/Finetuning/scripts/add_classification_step.py', encoding='utf-8').read()
DIS = eval(re.search(r'^DIS = \{.*?^\}', _src, re.S | re.M).group(0)[len('DIS = '):])
IN = {json.loads(l)['id']: json.loads(l)['prompt'] for l in open(f'{D}/pilot/blind_in.jsonl', encoding='utf-8')}
OUT = f'{D}/pilot/blind_out.jsonl'
tg = lambda r: f"“{R[r]['tag']}”（{r}）" if r in R else r


def add(id, locate, items):
    """items: [dict(rule, quotes=[(来源, 位置, 引文)], clauses=[...], check=核对文字, judge=判断文字, problem, suggestion, part)]"""
    prompt = IN[id]; errs = []
    pos = lambda it: min([prompt.find(q[2]) for q in it['quotes'] if prompt.find(q[2]) >= 0] or [10 ** 9])
    items = sorted(items, key=pos)
    lines = [f'定位：{locate}'] if locate else []; F = []; seen = {}
    for n, it in enumerate(items, 1):
        for s, loc, q in it['quotes']:
            if q not in prompt: errs.append(f'引文不在输入：{q[:30]}')
        ex = '；'.join(f"“{q}”（{s}｜{loc}）" for s, loc, q in it['quotes'])
        rid = it['rule']; seg = [f"意见{n}（{R[rid]['tag'] if rid in R else rid}）：", f'摘录：{ex}', '核对：' + it['check'], '判断：' + it['judge']]
        head = f'归类：属于{tg(rid)}'
        if rid in seen: seg.append(head + f'，判别同意见{seen[rid]}。')
        else:
            seen[rid] = n; seg.append(head + ('：' + DIS[rid] if rid in DIS else (f"，关注的问题是：{R[rid]['question']}。" if rid in R else '。')))
        lines.append('\n'.join(seg))
        F.append(dict(evidence=[dict(source=s, loc=loc, quote=q) for s, loc, q in it['quotes']], issue_type=R[rid]['tag'] if rid in R else rid, rule_id=rid, verdict='问题',
                      clause_ids=it['clauses'], basis_type=it.get('basis', '政策'), problem=it.get('problem', ''), suggestion=it['suggestion'], part=it.get('part', '')))
    clauses = sorted({c for it in items for c in it['clauses']})
    lines.append('条文：' + '；'.join(clauses))
    out = '<think>\n' + '\n'.join(lines) + '\n</think>\n' + json.dumps(dict(task='小节审核', findings=F), ensure_ascii=False)
    rows = [json.loads(l) for l in open(OUT, encoding='utf-8')] if os.path.exists(OUT) else []
    rows = [r for r in rows if r['id'] != id] + [dict(id=id, output=out)]
    with open(OUT, 'w', encoding='utf-8') as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(id, 'OK' if not errs else errs, f'{len(F)}条意见')
