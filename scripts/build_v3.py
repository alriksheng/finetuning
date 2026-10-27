"""训练集 v3（2026-10-27）：在 make_splits 的输出上追加程序派生样本和公开数据。见 样本扩容_v3说明.md。

用法：python3 -I scripts/build_v3.py data <基础目录> <输出目录>
  基础目录：make_splits.py 用 splits_v3.yaml 的输出（含 v2 普通样本、L3-07 全量、意见复核），如 train_v3_base。
  输出目录：基础目录全部文件 + 下列新增文件，如 train_v3。

新增（只用训练集项目；开发集、测试集不扩）：
  A1 split_train_think.json    按规则拆分：一条样本有多条规则的，每条规则一个样本。审核重点只留这一项，输出只留这条规则的意见，
                               思考只留这条规则的段落。思考里的段落对应不到具体要点的样本不拆（不硬拆）。
  A2 locate_train_think.json   证据定位：输入小节和一条意见，输出这条意见的引文。新任务类型“证据定位”。
  A3 perturb_train_think.json  输入扰动：打乱条文和审核重点的顺序，删去未用到的条文或加入干扰条文。输出与原样本相同。
  A5 fix_train_think.json      反事实无问题样本（data/out_fix/samples_fix.jsonl 中的训练集项目），审核重点按 v2 补 R-COST-CHECK。
  公开 public_train_think.json 按来源平均分配，合计占训练总行数的 PUBLIC_RATIO；来源文件放在 data/public/<来源>/*.json(l)。
"""
import collections, json, os, random, re, shutil, sys
import yaml

DATA, BASE, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
SEED = 42
PUBLIC_RATIO = 0.20
PUBLIC_SOURCES = ['逻辑与法考', '政府采购投诉', '会计审计税务', '绩效目标与评价']   # 用户 2026-10-27：四类平均分配
CN = '一二三四五六七八九十'
squash = lambda s: re.sub(r'\s+', '', s)
rng = random.Random(SEED)
J = lambda p: json.load(open(p, encoding='utf-8'))


def parse(row):
    u = row['conversations'][0]['value']
    m = re.match(r'\s*<think>(.*?)</think>\s*(.*)$', row['conversations'][1]['value'], re.S)
    if not m:
        return None
    try:
        ans = json.loads(m.group(2))
    except json.JSONDecodeError:
        return None
    if ans.get('task') not in ('小节审核', '比对包') or not isinstance(ans.get('findings'), list):
        return None
    return dict(system=row['system'], prompt=u, think=m.group(1).strip(), ans=ans)


def row(system, prompt, think, ans):
    return dict(system=system, conversations=[{'from': 'human', 'value': prompt},
                                              {'from': 'gpt', 'value': f'<think>\n{think}\n</think>\n\n' + json.dumps(ans, ensure_ascii=False)}])


def quotes_ok(prompt, think):
    hay = squash(prompt)
    return all(squash(seg) in hay for q in re.findall(r'「(.*?)」', think, re.S) for seg in q.split('…') if squash(seg))


def focus(prompt):
    m = re.search(r'【审核重点】(.*?)\n', prompt)
    return [(t.strip(), i) for t, i in re.findall(r'([^；（(]+)[（(]([A-Z][A-Z0-9\-]*)[）)]', m.group(1))] if m else []


def set_focus(prompt, items):
    return re.sub(r'【审核重点】.*?\n', lambda _: '【审核重点】' + '；'.join(f'{t}（{i}）' for t, i in items) + '\n', prompt, count=1)


# ---------- A1 按规则拆分 ----------
def split_by_rule(s):
    F = s['ans']['findings']
    rules = list(dict.fromkeys(f.get('rule_id') for f in F))
    if len(rules) < 2:
        return [], 'single'
    lines = [l.strip() for l in s['think'].split('\n') if l.strip()]
    head = lines[0] if re.match(r'(定位|比对)[:：]', lines[0]) else None
    body = lines[1:] if head else lines
    per, shared, last = collections.defaultdict(list), [], None
    by_rule = {r: [i for i, f in enumerate(F) if f.get('rule_id') == r] for r in rules}
    for l in body:
        if l.startswith('结论'):
            continue
        ks = {CN.index(k) for k in re.findall(r'要点([一二三四五六七八九十])', l) if CN.index(k) < len(F)}
        rk = [r for r in rules if r and r in l and len(by_rule[r]) == 1]
        if len(ks) == 1:
            last = ks.pop()
            per[last].append(l)
        elif not ks and len(rk) == 1:                 # 行内写了规则编号（如“规则判断（L3-07）”）
            last = by_rule[rk[0]][0]
            per[last].append(l)
        elif l.startswith('条文'):
            shared.append(l)
        elif not ks and last is not None:             # 没有标记的段落归到前面最近的要点
            per[last].append(l)
        else:
            return [], 'unmapped'                      # 对应不到要点的推理段落：不拆
    if any(not per[i] for i in range(len(F))):
        return [], 'unmapped'
    fmap = dict(focus(s['prompt']))
    tag = {i: t for t, i in focus(s['prompt'])}
    out = []
    for r in rules:
        idx = [i for i, f in enumerate(F) if f.get('rule_id') == r]
        if r not in tag:
            return [], 'rule_not_in_focus'
        cids = {c for i in idx for c in F[i].get('clause_ids') or []}
        keep_cl = [l for l in shared if any(c in l for c in cids)]
        concl = '；'.join((F[i].get('problem') or '') + (F[i].get('suggestion') or '') for i in idx)
        t = '\n'.join(([head] if head else []) + [l for i in idx for l in per[i]] + keep_cl + ['结论：' + concl])
        if any(c not in t for c in cids):
            return [], 'clause_missing'
        p = set_focus(s['prompt'], [(tag[r], r)])
        if not quotes_ok(p, t):
            return [], 'quote'
        out.append(row(s['system'], p, t, dict(s['ans'], findings=[F[i] for i in idx])))
    return out, 'ok'


# ---------- A2 证据定位 ----------
LOC_SYS = ('你是成本预算绩效分析报告的评审专家。输入给出报告原文、事实卡和一条评审意见。先在思考中说明意见指向的内容，'
           '再在报告段落和事实卡中逐段查找这条意见的依据；然后输出 JSON：task（证据定位）、evidence（每条包含 source、loc、quote，'
           'quote 为报告或事实卡的逐字摘录）。只摘录与这条意见直接相关的原文，不摘录背景性内容。\n【任务类型】证据定位')


def section(prompt, name):
    m = re.search(rf'【{name}】(.*?)(?=\n【|\Z)', prompt, re.S)
    return m.group(0).strip() if m else ''


def common(a, b, n=4):
    a, b = squash(a), squash(b)
    best = ''
    for i in range(len(a)):
        for j in range(i + len(best) + 1, min(len(a), i + 30) + 1):
            if a[i:j] in b:
                best = a[i:j]
            else:
                break
    return best if len(best) >= n else ''


def locate(s):
    out = []
    tag = dict((i, t) for t, i in focus(s['prompt']))
    base = '\n\n'.join(x for x in (section(s['prompt'], '项目信息'), section(s['prompt'], '报告段落'), section(s['prompt'], '事实卡')) if x)
    for f in s['ans']['findings']:
        ev = [e for e in f.get('evidence') or [] if isinstance(e, dict) and e.get('quote')]
        text = (f.get('problem') or '') + (f.get('suggestion') or '')
        if not ev or not text:
            continue
        p = (base + f'\n\n【评审意见】{tag.get(f.get("rule_id"), f.get("issue_type", ""))}：{text}'
             '\n\n【任务】找出报告段落或事实卡中支撑这条评审意见的原文，逐字摘录。')
        steps = [f'意见指向：{f.get("issue_type", "")}。意见原文要点是“{text[:60]}{"…" if len(text) > 60 else ""}”。']
        tlines = [l.strip() for l in s['think'].split('\n') if l.strip() and not re.match(r'(定位|结论|条文)', l.strip())]
        for k, e in enumerate(ev, 1):
            step = f'依据{CN[k - 1] if k <= 10 else k}（{e.get("source", "报告")}）：「{e["quote"]}」'
            key = squash(e['quote'])[:12]
            why = next((l for l in tlines if len(key) >= 6 and key in squash(l) and len(l) <= 220), None)   # 原推理中分析这段引文的一行
            c = common(e['quote'], text, 6)
            if why and quotes_ok(base, why):
                step += f'\n  分析：{why}'
            elif c:
                step += f'\n  意见中的“{c}”出自这段原文。'
            steps.append(step)
        steps.append(f'结论：共摘录 {len(ev)} 段原文。')
        t = '\n'.join(steps)
        if quotes_ok(p, t):
            out.append(row(LOC_SYS, p, t, {'task': '证据定位', 'evidence': ev}))
    return out


# ---------- A3 输入扰动 ----------
CLAUSES = {c['clause_id']: c for c in J(os.path.join(DATA, 'clauses', 'clauses.json'))}
cl_line = lambda c: f"[{c['clause_id']}｜{c['effective_from']}] {c['text']}"


def perturb(s):
    m = re.search(r'(【条文】\n)(.*?)(\n\n【)', s['prompt'], re.S)
    if not m:
        return None
    lines = m.group(2).split('\n')
    ids = [re.match(r'\[([^｜\]]+)｜', l).group(1) if re.match(r'\[([^｜\]]+)｜', l) else None for l in lines]
    if None in ids:
        return None
    used = {c for f in s['ans']['findings'] for c in f.get('clause_ids') or []} | {i for i in ids if i in s['think']}
    pairs = list(zip(ids, lines))
    if rng.random() < 0.5:
        drop = [p for p in pairs if p[0] not in used]
        rng.shuffle(drop)
        n = min(len(drop), max(0, len(pairs) - 3), rng.randint(1, 2))
        pairs = [p for p in pairs if p not in drop[:n]]
        how = f'删去未用条文 {n} 段'
    else:
        pool = [c for c in CLAUSES if c not in ids]
        add = rng.sample(pool, min(len(pool), rng.randint(1, 2)))
        pairs += [(c, cl_line(CLAUSES[c])) for c in add]
        how = f'加入干扰条文 {len(add)} 段'
    rng.shuffle(pairs)
    p = s['prompt'][:m.start(2)] + '\n'.join(l for _, l in pairs) + s['prompt'][m.end(2):]
    items = focus(p)
    rng.shuffle(items)
    p = set_focus(p, items) if items else p
    if p == s['prompt'] or not quotes_ok(p, s['think']):
        return None
    return row(s['system'], p, s['think'], s['ans']), how


# ---------- A5 反事实无问题 ----------
def fix_rows(train_projects):
    out = []
    for l in open(os.path.join(DATA, 'out_fix', 'samples_fix.jsonl'), encoding='utf-8'):
        r = json.loads(l)
        if r['meta'].get('project_id') not in train_projects:
            continue
        u, a = r['messages'][0]['content'], r['messages'][1]['content']
        items = focus(u)
        if items and 'R-COST-CHECK' not in {i for _, i in items}:          # v2 起审核重点统一含 R-COST-CHECK
            u = set_focus(u, items + [('成本数据一致性', 'R-COST-CHECK')])
        out.append(dict(system=r['system'], conversations=[{'from': 'human', 'value': u}, {'from': 'gpt', 'value': a}]))
    return out


def load_public(src):
    d = os.path.join(DATA, 'public', src)
    rows = []
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        f = os.path.join(d, fn)
        if fn.endswith('.json'):
            rows += J(f)
        elif fn.endswith('.jsonl'):
            for r in map(json.loads, open(f, encoding='utf-8')):
                rows.append(dict(system=r['system'], conversations=[{'from': 'human', 'value': r['messages'][0]['content']},
                                                                     {'from': 'gpt', 'value': r['messages'][1]['content']}]))
    for r in rows:
        assert re.match(r'\s*<think>.+?</think>', r['conversations'][1]['value'], re.S), f'{src}：公开样本必须带推理'
    return rows


def main():
    base, out = os.path.join(DATA, BASE), os.path.join(DATA, OUT)
    os.makedirs(out, exist_ok=True)
    for fn in os.listdir(base):
        shutil.copy(os.path.join(base, fn), out)
    cfg = yaml.safe_load(open(os.path.join(DATA, 'splits_v3.yaml'), encoding='utf-8'))
    train_projects = {p for g in cfg['groups'].values() if g.get('split') == 'train' for p in g.get('projects', [])}
    audit, seen = [], set()
    for r in J(os.path.join(base, 'audit_train_think.json')):
        if r['conversations'][0]['value'] in seen:      # 精标加权的重复行只取一次
            continue
        seen.add(r['conversations'][0]['value'])
        s = parse(r)
        if s:
            audit.append(s)
    files, rep = {}, collections.Counter()
    files['split_train_think'] = []
    for s in audit:
        rows, why = split_by_rule(s)
        rep['A1_' + why] += 1
        files['split_train_think'] += rows
    files['locate_train_think'] = [x for s in audit if s['ans']['findings'] for x in locate(s)]
    files['perturb_train_think'], hows = [], collections.Counter()
    for s in audit:
        r = perturb(s)
        if r:
            files['perturb_train_think'].append(r[0])
            hows[r[1].split(' ')[0]] += 1
    files['fix_train_think'] = fix_rows(train_projects)
    domain = sum(len(J(os.path.join(base, f))) for f in os.listdir(base) if f.endswith('_train_think.json')) \
        + sum(len(v) for v in files.values())
    target = int(PUBLIC_RATIO / (1 - PUBLIC_RATIO) * domain)
    quota = target // len(PUBLIC_SOURCES)
    files['public_train_think'], pub = [], {}
    for src in PUBLIC_SOURCES:
        rows = load_public(src)
        rng.shuffle(rows)
        files['public_train_think'] += rows[:quota]
        pub[src] = (len(rows), min(len(rows), quota))
    info = J(os.path.join(base, 'dataset_info.json'))
    for k, v in files.items():
        json.dump(v, open(os.path.join(out, f'{k}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        info[k] = dict(file_name=f'{k}.json', formatting='sharegpt', columns={'messages': 'conversations', 'system': 'system'})
    json.dump(info, open(os.path.join(out, 'dataset_info.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    base_counts = {f[:-5]: len(J(os.path.join(base, f))) for f in sorted(os.listdir(base)) if f.endswith('_train_think.json')}
    total = sum(base_counts.values()) + sum(len(v) for v in files.values())
    lines = [f'基础目录 {BASE}：' + '，'.join(f'{k} {v}' for k, v in base_counts.items()),
             f'普通样本（去掉精标加权重复）{len(audit)} 条',
             f'A1 按规则拆分：新增 {len(files["split_train_think"])} 行；多规则样本中 可拆 {rep["A1_ok"]}、段落对应不上未拆 {rep["A1_unmapped"]}、'
             f'规则不在审核重点 {rep["A1_rule_not_in_focus"]}、条文对不上 {rep["A1_clause_missing"]}、引文核验不过 {rep["A1_quote"]}；单规则 {rep["A1_single"]}',
             f'A2 证据定位：{len(files["locate_train_think"])} 行',
             f'A3 输入扰动：{len(files["perturb_train_think"])} 行（{dict(hows)}）',
             f'A5 反事实无问题：{len(files["fix_train_think"])} 行',
             f'公开数据：目标 {target} 行（占总量 {PUBLIC_RATIO:.0%}，四类各 {quota} 行）；' +
             '；'.join(f'{k} 可用 {a} 取 {b}' + (f'（缺 {quota - b}）' if b < quota else '') for k, (a, b) in pub.items()),
             f'v3 训练总行数 {total}，其中公开数据 {len(files["public_train_think"])}（实际占比 {len(files["public_train_think"]) / total:.1%}）']
    open(os.path.join(out, 'v3_report.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
