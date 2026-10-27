"""T2 试点：从训练项目的审核样本中分层抽 40 条，写出盲审输入（不含标准答案）和带标准答案的评测输入。
Usage: python3 -I pilot_select.py <data_dir> [n=40] [seed=20261026]"""
import sys, os, json, random, yaml, collections
D = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 40; seed = int(sys.argv[3]) if len(sys.argv) > 3 else 20261026
cfg = yaml.safe_load(open(os.path.join(D, 'splits.yaml'), encoding='utf-8'))
split = {p: v['split'] for g, v in cfg['groups'].items() for p in v['projects']}
SEEN = {'V3_P001_scope_01', 'V3_P002_proc_purchase_01', 'V3_P002_fund1_merged', 'V3_P002_base_indicator_01', 'V3_P001_base_indicator_01', 'V4_P003_S022', 'V4_P004_S016', 'V4_P004_S009',
        'V6_P012_S002', 'V4_P013_S020', 'V6_P016_S005', 'V6_P017_S002', 'V6_P017_S005'}          # 本会话已经读过标准答案的样本，不进盲审
rows = [json.loads(l) for l in open(os.path.join(D, 'out/samples.jsonl'), encoding='utf-8')]
pool = []
for r in rows:
    m = r['meta']
    if m.get('task_type') != '小节审核' or split.get(m['project_id']) != 'train' or m.get('synthetic') or r['id'] in SEEN: continue
    a = r['messages'][1]['content']
    if '</think>' not in a: continue
    F = json.loads(a.split('</think>')[1])['findings']
    if not F or len(r['messages'][0]['content']) > 7500: continue
    pool.append((r, len(F)))
rnd = random.Random(seed); rnd.shuffle(pool)
quota = {1: round(N * .35), 2: round(N * .25), 3: round(N * .25)}; quota[4] = N - sum(quota.values())
pick, used_proj, cnt = [], collections.Counter(), collections.Counter()
for r, n in sorted(pool, key=lambda x: used_proj[x[0]['meta']['project_id']]):            # 先尽量每个项目取一条
    b = min(n, 4)
    if cnt[b] >= quota[b] or used_proj[r['meta']['project_id']] >= 2: continue
    pick.append((r, n)); cnt[b] += 1; used_proj[r['meta']['project_id']] += 1
    if len(pick) == N: break
pick.sort(key=lambda x: x[0]['id'])
os.makedirs(os.path.join(D, 'pilot'), exist_ok=True)
with open(os.path.join(D, 'pilot/blind_in.jsonl'), 'w', encoding='utf-8') as fb, open(os.path.join(D, 'pilot/audit_pilot.jsonl'), 'w', encoding='utf-8') as fg:
    for r, n in pick:
        fb.write(json.dumps(dict(id=r['id'], prompt=r['messages'][0]['content']), ensure_ascii=False) + '\n')
        fg.write(json.dumps(dict(id=r['id'], project=r['meta']['project_id'], system=r['system'], prompt=r['messages'][0]['content'], gold=r['messages'][1]['content'], meta={'task_type': '小节审核'}), ensure_ascii=False) + '\n')
print(len(pick), dict(cnt), len({r['meta']['project_id'] for r, _ in pick}), '个项目')
