"""检查专家规则对应情况：哪些条目已对应、哪些未对应、是否重复对应、拟新增规则清单。
用法：python3 -I scripts/check_expert_mapping.py data/rules"""
import glob, json, os, runpy, sys, collections
D = sys.argv[1]
pts = {json.loads(l)['pid']: json.loads(l) for l in open(os.path.join(D, 'expert_points.jsonl'), encoding='utf-8')}
seen, new, by = collections.Counter(), collections.Counter(), collections.Counter()
for f in sorted(glob.glob(os.path.join(D, 'expert_mapping', '*.py'))):
    for m in runpy.run_path(f)['MAPPING']:
        for p in m['pids']:
            assert p in pts, f'{f}: 不存在的条目 {p}'
            seen[p] += 1
        by[m['rule']] += 1
        if m['rule'].startswith('NEW:'): new[m['rule']] += 1
dup = [p for p, n in seen.items() if n > 1]
left = [p for p in pts if p not in seen]
print(f'已对应 {len(seen)}/{len(pts)}；重复 {dup or "无"}；拟新增规则 {dict(new) or "无"}')
print('各规则审核点数', dict(by))
sec = collections.Counter(pts[p]['section'].split(' > ')[0][:24] for p in left)
print('未对应（按部分）', dict(sec))
