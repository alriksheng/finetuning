"""按 data/splits.yaml 生成 LLaMA-Factory 训练、开发、测试文件（方案 v4 2.1、2.6、2.12、3.2）。

Usage: python3 -I make_splits.py <data_dir> [splits 文件名，默认 splits.yaml] [输出目录名，默认 train]
输出 data/train/：
  audit_<split>_<think|nothink>.json   领域样本（sharegpt 格式，含 system）；train 中精标样本按权重复制
  rule_<RULE>_train_<variant>.json     规则专项训练样本（splits.yaml 中 in_train=true 时才生成）
  rule_<RULE>_<split>_<card|tag|none>.json   规则内化验证三组（dev / test 项目）
  dataset_info.json, split_report.txt
"""
import sys, os, re, json, collections, itertools
import yaml

DATA = sys.argv[1]
CFG = yaml.safe_load(open(os.path.join(DATA, sys.argv[2] if len(sys.argv) > 2 else 'splits.yaml'), encoding='utf-8'))
OUT = os.path.join(DATA, sys.argv[3] if len(sys.argv) > 3 else 'train'); os.makedirs(OUT, exist_ok=True)
SYN_KINDS = ('model_supplement', 'candidate_no_issue', 'synthetic_clause_rewrite', 'synthetic_clause_irrelevant')   # 2.6：老师生成、未经专家确认的补充问题和无问题样本计入合成
NOTHINK = lambda a: '<think>\n\n</think>\n\n' + re.sub(r'(?s)^<think>.*?</think>\s*', '', a)
THINK = lambda a: re.sub(r'(?s)</think>\s*', '</think>\n\n', a, count=1)   # 与 Qwen3 聊天模板一致：</think> 后空一行（2026-10-23）

proj, errs, rep = {}, [], []
for g, v in CFG['groups'].items():
    for p in v['projects']:
        if p in proj: errs.append(f'{p} 出现在两个组中')
        proj[p] = dict(group=g, split=v['split'], annotation=v.get('annotation', '自动标注'))
if any(v['split'] not in ('train', 'dev', 'test') for v in CFG['groups'].values()): errs.append('split 只能是 train / dev / test')

load = lambda f: [json.loads(l) for l in open(os.path.join(DATA, f), encoding='utf-8')] if os.path.exists(os.path.join(DATA, f)) else []
think = load('out/samples.jsonl') + (load('out/candidates_no_issue.jsonl') if CFG.get('include_candidates') else [])
sg = lambda r, content: dict(system=r['system'], conversations=[{'from': 'human', 'value': r['messages'][0]['content']}, {'from': 'gpt', 'value': content}])

files, info, stats = collections.defaultdict(list), {}, collections.Counter()
syn_units = 0.0; real_units = 0
for r in think:
    pid = r['meta']['project_id']
    if pid not in proj: errs.append(f"{r['id']}: 项目 {pid} 未在 splits.yaml 中分组"); continue
    sp, ann = proj[pid]['split'], proj[pid]['annotation']
    w = CFG['weights'].get(ann, 1) if sp == 'train' else 1
    kinds = r['meta'].get('member_source_kinds') or [r['meta'].get('source_kind', 'expert')]
    if sp == 'train':
        syn_units += sum(k in SYN_KINDS for k in kinds) / len(kinds); real_units += 1
    for var in CFG['thinking']:
        a = THINK(r['messages'][1]['content']) if var == 'think' else NOTHINK(r['messages'][1]['content'])
        files[f'audit_{sp}_{var}'] += [sg(r, a)] * w
    stats[(sp, pid)] += 1

RCAP = CFG.get('rule_cap', 0.30)                 # 专项样本占训练集（加权后的行数）的上限
KEEP_NA = CFG.get('keep_na_per_project', 2)      # 每个项目保留的“不适用”逐项判断条数


def rule_class(r):
    """专项样本分类：汇总、合成、驱动成本、不适用、无对应成本项、需人工核对（共 6 类）。"""
    m = r['meta']
    return '汇总' if m['step'] == '汇总' else '合成' if m['synthetic'] else m.get('judgment')


def rule_select(rows, budget):
    """专项样本取舍（2026-10-23 起）：按分类平均挑选。
    1. 每个项目“不适用”最多保留 KEEP_NA 条；
    2. 各类配额 = budget / 类数；某类样本不足时全取，缺额平分给其余各类；
    3. 类内各项目轮流取，项目顺序用固定随机种子打乱（rule_seed），避免靠前的项目占满配额。"""
    import random
    pool = collections.defaultdict(list)
    na_seen = collections.Counter()
    for r in rows:
        c = rule_class(r)
        if c == '不适用':
            if na_seen[r['meta']['project_id']] >= KEEP_NA: continue
            na_seen[r['meta']['project_id']] += 1
        pool[c].append(r)
    classes = sorted(pool); quota = {c: 0 for c in classes}; left = budget; open_ = list(classes)
    while left > 0 and open_:                       # 水位法分配配额
        share = max(1, left // len(open_)); progressed = False
        for c in list(open_):
            take = min(share, len(pool[c]) - quota[c], left)
            quota[c] += take; left -= take; progressed |= take > 0
            if quota[c] >= len(pool[c]): open_.remove(c)
            if left <= 0: break
        if not progressed: break
    rng = random.Random(CFG.get('rule_seed', 0)); out = []
    for c in classes:
        by = collections.defaultdict(list)
        for r in pool[c]: by[r['meta']['project_id']].append(r)
        order = sorted(by); rng.shuffle(order); got = []
        while len(got) < quota[c] and any(by.values()):
            for pid in order:
                if by[pid] and len(got) < quota[c]: got.append(by[pid].pop(0))
        out += got
    return out


audit_rows = len(files.get('audit_train_think', []))      # 普通样本训练行数（含精标加权）
for rule, rc in (CFG.get('rules') or {}).items():
    base = f'out_rules/{rule}'
    for var in ('card', 'tag', 'none'):
        for r in load(f'{base}/eval_{var}.jsonl'):
            sp = proj.get(r['meta']['project_id'], {}).get('split')
            if sp in ('dev', 'test'): files[f'rule_{rule}_{sp}_{var}'].append(sg(r, THINK(r['messages'][1]['content'])))
    pool = [r for r in load(f"{base}/train_{rc.get('train_variant', 'tag')}.jsonl") if proj.get(r['meta']['project_id'], {}).get('split') == 'train']
    budget = int(CFG['rule_ratio'] * audit_rows) if CFG.get('rule_ratio') else int(RCAP / (1 - RCAP) * audit_rows)   # rule_ratio：专项 : 普通 的行数比，0.5 即 1:2
    chosen = rule_select(pool, budget)
    na_all = sum(r['meta'].get('judgment') == '不适用' for r in pool)
    cc = collections.Counter(rule_class(r) for r in chosen); pc = collections.Counter(rule_class(r) for r in pool)
    rep.append(f"{rule}：训练项目专项样本 {len(pool)} 条（分类：{dict(pc)}）；每项目不适用 ≤{KEEP_NA} 条，按分类平均挑选，取 {len(chosen)} 条"
               f"（普通 {audit_rows} : 专项 {len(chosen)} = {audit_rows / max(1, len(chosen)):.2f} : 1）；各类取数：{dict(cc)}；涉及项目 {len({r['meta']['project_id'] for r in chosen})} 个")
    if rc.get('in_train'):
        for r in chosen:
            if r['meta'].get('synthetic'): syn_units += 1
            else: real_units += 1
            for var in CFG['thinking']:
                a = THINK(r['messages'][1]['content']) if var == 'think' else NOTHINK(r['messages'][1]['content'])
                files[f"rule_{rule}_train_{var}"].append(sg(r, a))
    else:
        rep.append(f'{rule}：in_train=false（规则卡待专家确认），规则专项样本未进入训练文件；以上为打开后的预计取数')

tot = syn_units + real_units
ratio = syn_units / tot if tot else 0
if ratio > CFG['synthetic_cap']: errs.append(f'合成样本占比 {ratio:.0%} 超过上限 {CFG["synthetic_cap"]:.0%}')
for name, rows in files.items():
    json.dump(rows, open(os.path.join(OUT, name + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    info[name] = dict(file_name=name + '.json', formatting='sharegpt', columns=dict(messages='conversations', system='system'))
json.dump(info, open(os.path.join(OUT, 'dataset_info.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

splits = collections.Counter(v['split'] for v in proj.values())
rep = [f"实验 {CFG['experiment']}；通用逻辑数据：{'加入' if CFG.get('include_general') else '不加入'}",
       '分组：' + '；'.join(f"{g}→{v['split']}（{'、'.join(v['projects'])}）" for g, v in CFG['groups'].items()),
       '各划分项目数：' + str(dict(splits)),
       '样本数（划分, 项目）：' + str(dict(stats)),
       '文件：' + str({k: len(v) for k, v in sorted(files.items())}),
       f'训练集合成样本占比（按样本计，合并样本按成员比例计）：{ratio:.1%}（上限 {CFG["synthetic_cap"]:.0%}）'] + rep
if not splits.get('test'): rep.append('提示：测试集暂未划分（项目到齐后在 splits.yaml 中把对应分组改为 test）')
if not splits.get('dev'): rep.append('提示：开发集暂未划分（项目到齐后从自动标注项目中留 10–15 个，3.2）')
rep += [f'ERROR {e}' for e in errs]
open(os.path.join(OUT, 'split_report.txt'), 'w', encoding='utf-8').write('\n'.join(rep)); print('\n'.join(rep))
sys.exit(1 if errs else 0)
