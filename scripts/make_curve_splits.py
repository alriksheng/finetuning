"""学习曲线实验：从 splits.yaml 随机保留一部分训练组，其余训练组改为 drop（不进任何文件）。
Usage: python3 -I make_curve_splits.py <data_dir> <fraction> <seed> <out_yaml>
按组抽样（同组项目一起保留），开发集、测试集不变。"""
import sys, yaml, random, os
D, frac, seed, out = sys.argv[1], float(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
cfg = yaml.safe_load(open(os.path.join(D, 'splits.yaml'), encoding='utf-8'))
tr = [g for g, v in cfg['groups'].items() if v['split'] == 'train']
n_proj = lambda gs: sum(len(cfg['groups'][g]['projects']) for g in gs)
tot = n_proj(tr); random.Random(seed).shuffle(tr)
keep, k = [], 0
for g in tr:
    if k >= frac * tot: break
    keep.append(g); k += len(cfg['groups'][g]['projects'])
for g in tr:
    if g not in keep: cfg['groups'][g]['split'] = 'drop'
cfg['experiment'] = f'curve{int(frac * 100)}'
yaml.safe_dump(cfg, open(os.path.join(D, out), 'w', encoding='utf-8'), allow_unicode=True, sort_keys=False)
print(f'保留训练项目 {k}/{tot}（{len(keep)} 组）')
