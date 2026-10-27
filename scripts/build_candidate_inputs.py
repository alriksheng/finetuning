"""候选意见流水线 第 1 步：给“没有专家意见的小节”构造模型输入（格式同训练样本）。
Usage: python3 -I build_candidate_inputs.py data data/cand/cand_inputs.jsonl [min_chars=200]
范围：splits.yaml 里 split=train 的项目中，report 为 .md 的项目；小节取 specs/sections/<P>.json 的 units，排除与 specs 里已标注小节行范围重叠的、字数不足、annex 类。
输入的组成同 build.py：项目信息 + 报告段落 + 事实卡（无）+ 条文（clause_map 按项目类型和小节 kind）+ 审核重点（focus_map）+ 任务。"""
import sys, os, re, json, glob, runpy, yaml
D, OUT = sys.argv[1], sys.argv[2]; MIN = int(sys.argv[3]) if len(sys.argv) > 3 else 200
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, 'build.py'), encoding='utf-8').read()
SYSTEM_BASE = eval(re.search(r'SYSTEM_BASE = (\(.*?\))\nsystem_for', src, re.S).group(1))
CLAUSES = {c['clause_id']: c for c in json.load(open(f'{D}/clauses/clauses.json', encoding='utf-8'))}
RULES = {r['rule_id']: r for r in yaml.safe_load(open(f'{D}/rules/rules.yaml', encoding='utf-8'))}
PROJ = json.load(open(f'{D}/specs/projects.json', encoding='utf-8'))
CMAP = yaml.safe_load(open(f'{D}/specs/clause_map.yaml', encoding='utf-8')); FMAP = yaml.safe_load(open(f'{D}/specs/focus_map.yaml', encoding='utf-8'))
split = {p: v['split'] for g in [yaml.safe_load(open(f'{D}/splits.yaml', encoding='utf-8'))['groups']] for k, v in g.items() for p in v['projects']}
cline = lambda c: f"[{c['clause_id']}｜{c['effective_from']}] {c['text']}"
rows, skipped = [], {}
for f in sorted(glob.glob(f'{D}/specs/P*.py')):
    sp = runpy.run_path(f); pid = sp['SOURCE']
    if split.get(pid) != 'train': continue
    sj = f'{D}/specs/sections/{pid}.json'; md = f'{D}/raw/reports/{pid}.md'
    if not (os.path.exists(sj) and os.path.exists(md)): skipped[pid] = '无切分或非 md'; continue
    lines = open(md, encoding='utf-8').read().split('\n'); P = PROJ[pid]; pt = P['ptype']
    used = set()
    for s in sp['SECTIONS'].values():
        for a, b in s.get('lines', []): used.update(range(a, b + 1))
    for u in json.load(open(sj, encoding='utf-8'))['units']:
        a, b = u['lines']; kind = u['kind']; base = kind[4:] if kind.startswith('abs_') else kind
        if set(range(a, b + 1)) & used or u['chars'] < MIN or kind == 'annex' or base not in FMAP[pt] or base not in CMAP[pt]: continue
        text = '\n'.join(lines[a - 1:b]); mapped = CMAP[pt][base]; focus = FMAP[pt][base]
        user = '\n\n'.join([f"【项目信息】\n项目：{P['name']}；报告类型：完整报告；分析金额：{P['amount']}；预算主管部门：{P['agency']}；评审时点：待填",
                            f"【报告段落】\n[{u['path']}] {text}", '【事实卡】\n（本任务无相关字段）',
                            '【条文】\n' + '\n'.join(cline(CLAUSES[c]) for c in mapped if c in CLAUSES),
                            '【审核重点】' + '；'.join(f"{RULES[r]['tag']}（{r}）" for r in focus), '【任务】对本小节提出评审意见。'])
        rows.append(dict(id=f"C_{pid}_{u['id']}", project=pid, system=SYSTEM_BASE + '\n【任务类型】小节审核', prompt=user, gold='', meta=dict(unit=u['id'], path=u['path'], kind=kind, chars=u['chars'], lines=u['lines'])))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as fo:
    for r in rows: fo.write(json.dumps(r, ensure_ascii=False) + '\n')
import collections
print(len(rows), '个小节；项目', len({r['project'] for r in rows}), '；跳过', skipped); print(collections.Counter(r['meta']['kind'] for r in rows).most_common())
print('prompt 字数 P50/P95/max', sorted(len(r['prompt']) for r in rows)[len(rows)//2], sorted(len(r['prompt']) for r in rows)[int(len(rows)*.95)], max(len(r['prompt']) for r in rows))
