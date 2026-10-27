"""意见复核开发集：A=用户已判定的 e3 额外意见（67 条：成立 13→采纳、成立但次要 21→次要不写、不成立 33→不采纳，原因取自“不成立原因”表）；
B=开发集标准答案里的专家意见（采纳）。输入沿用 data/eval_v2/audit_dev.jsonl 的小节，任务段落与训练样本一致。
Usage: python3 -I build_judge_dev.py <data_dir> <额外意见_待判定.xlsx> <不成立原因_待标注.xlsx> [out=data/eval_v2/judge_dev.jsonl]"""
import sys, json, re, runpy, os, openpyxl
D, X1, X2 = sys.argv[1:4]; OUT = sys.argv[4] if len(sys.argv) > 4 else f'{D}/eval_v2/judge_dev.jsonl'
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_judge.py'), encoding='utf-8').read()
TASK = re.search(r"TASK = \((.*?)\)\n", src, re.S).group(1); TASK = eval('(' + TASK + ')')
R = {r['id']: r for r in map(json.loads, open(f'{D}/eval_v2/audit_dev.jsonl', encoding='utf-8'))}
why = {}
for r in openpyxl.load_workbook(X2)['原因'].iter_rows(min_row=3, values_only=True):
    if r[1]: why[(r[1], r[2], r[3])] = r[5]
V = {'成立': ('采纳', '成立'), '成立但次要': ('次要不写', '成立但次要')}
rows = []
for k, r in enumerate(openpyxl.load_workbook(X1)['待判定'].iter_rows(min_row=3, values_only=True)):
    if not r[1] or not r[8]: continue
    sid, rule, text, quote, j = r[1], r[4], r[5], r[6], r[8]
    if j == '不成立':
        rt = why.get((sid, rule, text)); assert rt, (sid, rule, text[:20]); v = ('不采纳', rt)
    else: v = V[j]
    rows.append(dict(sid=sid, rule=rule, text=text, v=v, kind='A额外意见'))
for sid, rec in R.items():
    obj = json.loads(rec['gold'].split('</think>')[1])
    for f in obj['findings']: rows.append(dict(sid=sid, rule=f['rule_id'], text=f['problem'] + f['suggestion'], v=('采纳', '成立'), kind='B专家意见'))
out = []
for i, x in enumerate(rows):
    rec = R[x['sid']]; user = rec['prompt'].split('【任务】')[0] + f"【候选意见】\n规则：{x['rule']}\n意见：{x['text']}\n\n" + TASK
    out.append(dict(id=f"JD{i + 1:03d}_{x['sid']}", project=rec['project'], system=rec['system'].replace('【任务类型】小节审核', '【任务类型】意见复核'), prompt=user,
                    gold=json.dumps(dict(task='意见复核', verdict=x['v'][0], reason_type=x['v'][1]), ensure_ascii=False), meta=dict(kind=x['kind'], verdict=x['v'][0], reason_type=x['v'][1], rule_id=x['rule'], task_type='意见复核')))
with open(OUT, 'w', encoding='utf-8') as f:
    for o in out: f.write(json.dumps(o, ensure_ascii=False) + '\n')
import collections
print(len(out), dict(collections.Counter((o['meta']['kind'], o['meta']['verdict']) for o in out)))
