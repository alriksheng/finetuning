"""生成评测输入（开发集、测试集）。Usage: python3 -I eval_make_inputs.py <data_dir>
读 splits.yaml、out/samples.jsonl、out_rules/<规则>/eval_<card|tag|none>.jsonl，
写 data/eval/audit_<dev|test>.jsonl 和 rule_<规则>_<dev|test>_<card|tag|none>.jsonl。
每行：id、project、system、prompt（给模型的输入）、gold（标准答案，含 <think>）、meta。"""
import sys, os, json, yaml, glob
DATA = sys.argv[1]
cfg = yaml.safe_load(open(os.path.join(DATA, 'splits.yaml'), encoding='utf-8'))
split = {p: v['split'] for g, v in cfg['groups'].items() for p in v['projects']}
OUT = os.path.join(DATA, 'eval'); os.makedirs(OUT, exist_ok=True)
load = lambda f: [json.loads(l) for l in open(f, encoding='utf-8')]
row = lambda r: dict(id=r['id'], project=r['meta']['project_id'], system=r['system'], prompt=r['messages'][0]['content'], gold=r['messages'][1]['content'],
                     meta={k: r['meta'].get(k) for k in ('task_type', 'sample_type', 'step', 'indicator', 'judgment', 'synthetic', 'input_scope', 'base_sample')})
buf, rep = {}, []
for r in load(os.path.join(DATA, 'out/samples.jsonl')):
    sp = split.get(r['meta']['project_id'])
    if sp in ('dev', 'test'): buf.setdefault(f'audit_{sp}', []).append(row(r))
fx = os.path.join(DATA, 'out_fix/samples_fix.jsonl')                    # 反事实无问题样本：dev / test 项目的做误报评测（audit_<dev|test>_neg）
if os.path.exists(fx):
    for r in load(fx):
        sp = split.get(r['meta']['project_id'])
        if sp in ('dev', 'test'): buf.setdefault(f'audit_{sp}_neg', []).append(row(r))
for rule_dir in glob.glob(os.path.join(DATA, 'out_rules/*/')):
    rule = os.path.basename(rule_dir.rstrip('/'))
    for var in ('card', 'tag', 'none'):
        f = os.path.join(rule_dir, f'eval_{var}.jsonl')
        if not os.path.exists(f): continue
        for r in load(f):
            sp = split.get(r['meta']['project_id'])
            if sp in ('dev', 'test'): buf.setdefault(f'rule_{rule}_{sp}_{var}', []).append(row(r))
for name, rows in sorted(buf.items()):
    with open(os.path.join(OUT, name + '.jsonl'), 'w', encoding='utf-8') as f:
        for x in rows: f.write(json.dumps(x, ensure_ascii=False) + '\n')
    rep.append(f'{name}: {len(rows)} 条，项目 {len({x["project"] for x in rows})} 个')
print('\n'.join(rep))
