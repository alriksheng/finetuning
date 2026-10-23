"""专家规则预制（方案 v4 2.12）：按规则卡生成专项样本，并输出上下文蒸馏与内化验证所需的三种输入。

Usage: python3 -I build_rule_samples.py <data_dir> <rule_id>
输入：data/rules/cards/<rule_id>.yaml（规则卡）；data/rules/<rule_id>/P*.py（逐项判断规格，由“带规则卡的老师”生成）
输出：data/out_rules/<rule_id>/
  train_tag.jsonl         训练用：输入只带规则标签，目标为带规则卡生成并核验过的判断（上下文蒸馏，第 4 步）
  eval_card.jsonl / eval_tag.jsonl / eval_none.jsonl   内化验证三组（第 5 步）：带规则卡 / 只带标签 / 两者都不带
  preview.md, report.txt
"""
import sys, os, re, json, glob, runpy, collections
import yaml

DATA, RULE = sys.argv[1], sys.argv[2]
CHK = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'checks.py'))
norm, squash, span, quotes_ok, check_arith = CHK['norm'], CHK['squash'], CHK['span'], CHK['quotes_ok'], CHK['check_arith']
OUT = os.path.join(DATA, 'out_rules', RULE); os.makedirs(OUT, exist_ok=True)
CARD = yaml.safe_load(open(os.path.join(DATA, f'rules/cards/{RULE}.yaml'), encoding='utf-8'))
JUDGMENTS = ('驱动成本', '无对应成本项', '需人工核对', '不适用')        # 需人工核对：无量化表述（专家第六轮口径 Q1）
_R = {r['rule_id']: r for r in yaml.safe_load(open(os.path.join(DATA, 'rules/rules.yaml'), encoding='utf-8'))}
STATUS = '规则卡已确认（' + CARD['status'] + '）' if str(CARD['status']).startswith('专家') else '候选-规则卡待专家确认'
FOCUS = f"【审核重点】{_R[RULE]['tag']}（{RULE}）"                    # 规则标签：取 rules.yaml 的 tag
if CARD['tag'] != _R[RULE]['tag']: sys.exit(f"规则卡 tag 与 rules.yaml 不一致：{CARD['tag']} / {_R[RULE]['tag']}")
SYSTEM = ("你是成本预算绩效分析报告的评审专家。只能依据输入中给出的报告原文作出事实判断，原文摘录必须逐字。"
          "规则的判断步骤可以写在思考中，标注“依据：评审经验（规则编号）”。先思考，再按要求输出 JSON。\n【任务类型】规则专项")


def table_text(pid, spec):
    if 'lines' in spec:
        lines = open(os.path.join(DATA, 'raw/reports/P002.md' if pid == 'P002' else f'raw/reports/{pid}.md'), encoding='utf-8').read().split('\n')
        a, b = spec['lines']; return '\n'.join(lines[a - 1:b])
    pages = {p['pdf_page']: p for p in json.load(open(os.path.join(DATA, f'raw/reports/{pid}_pages.json'), encoding='utf-8'))}
    return span(' '.join(norm(pages[p]['text']) for p in spec['pages']), spec['a'], spec['b'])


def render_card(exclude_project):
    """完整规则卡文字。正反例中排除当前项目的例子，避免把答案放进输入。"""
    c = CARD
    ex = [e for e in c.get('examples', []) if e.get('project') != exclude_project]
    lines = [f"规则 {c['rule_id']} {c['title']}", f"判定口径：{c['caliber']}",
             f"适用范围：{c['scope']['applies']}", f"不适用：{c['scope']['not_applicable']}", '判断步骤：'] + [f"  {s}" for s in c['steps']]
    lines.append('判断结果取：' + c['output']['judgment'])
    if ex:
        lines.append('示例：')
        for e in ex:
            lines.append(f"  - {e['indicator']}（{e['category']}）→ {e['judgment']}：{e['why']}")
    return '\n'.join(lines)


def card_numbers():
    return re.findall(CHK['NUM'], json.dumps(CARD, ensure_ascii=False))


def build_input(variant, pid, ind_text, cost_text, labels, tail):
    head = '【规则卡】\n' + render_card(pid) if variant == 'card' else None
    focus = [FOCUS] if variant == 'tag' else []                      # 与领域样本同一写法，放在【任务】前
    lab = lambda l, t: '' if norm(t).startswith(norm(l).split('（')[0]) else l
    parts = ([head] if head else []) + [f"【绩效指标表】{lab(labels[0], ind_text)}\n{ind_text}", f"【成本构成表】{lab(labels[1], cost_text)}\n{cost_text}"] + tail[:-1] + focus + tail[-1:]
    return '\n\n'.join(parts)


def item_output(it):
    return dict(task='规则专项', rule_id=RULE, step='逐项判断', indicator=it['indicator'], category=it['category'], judgment=it['judgment'],
                cost_items=it['cost_items'], direction=it['direction'], evidence=[dict(quote=q) for q in it['evidence']], reason=it['reason'])


def main():
    recs, bad, stats = [], [], collections.Counter()
    for f in sorted(glob.glob(os.path.join(DATA, f'rules/{RULE}/P*.py'))):
        S = runpy.run_path(f); pid = S['SOURCE']
        ind, cost = table_text(pid, S['TABLES']['ind']), table_text(pid, S['TABLES']['cost'])
        labels = (S['TABLES']['ind']['label'], S['TABLES']['cost']['label'])
        jobs = [(f"{RULE}_{pid}_{i:02d}", it, ind, '真实报告；判断由老师带规则卡生成') for i, it in enumerate(S['ITEMS'], 1)]
        for syn in S.get('SYNTHETIC', []):
            old, new = syn['replace']
            if squash(old) not in squash(ind): bad.append(dict(id=syn['id'], errors=['synthetic: replace anchor not in table'])); continue
            k = norm(ind).find(norm(old)); ind2 = (norm(ind)[:k] + new + norm(ind)[k + len(norm(old)):]) if k >= 0 else ind.replace(old, new)
            jobs.append((f"{RULE}_{pid}_{syn['id']}", syn['item'], ind2, f"合成：由“{syn['base']}”改写成对"))
        # 逐项判断
        for sid, it, ind_used, src in jobs:
            tail = [f"【待判断指标】{it['indicator']}", '【任务】按规则逐项判断：该指标是否为成本动因。输出 JSON。']
            errs = []
            if it['judgment'] not in JUDGMENTS: errs.append(f"judgment {it['judgment']}")
            inp_tag = build_input('tag', pid, ind_used, cost, labels, tail)
            for q in it['evidence']:
                if squash(q) not in squash(inp_tag): errs.append(f'evidence not in input: {q[:30]}')
            errs += [f'think quote not in input: {q[:30]}' for q in quotes_ok(it['think'], inp_tag)]
            e2, _ = check_arith(it['think'], inp_tag, card_numbers()); errs += e2
            if it['judgment'] == '驱动成本' and not it['cost_items']: errs.append('驱动成本 but no cost_items')
            out = item_output(it)
            target = f"<think>\n{CHK['QUOTE'].sub(lambda m: '“' + m.group(1) + '”', it['think'])}\n</think>\n" + json.dumps(out, ensure_ascii=False)
            meta = dict(project_id=pid, rule_id=RULE, step='逐项判断', indicator=it['indicator'], judgment=it['judgment'], category=it['category'],
                        source=src, synthetic=src.startswith('合成'), status=STATUS, reasoning_author='claude-opus-5-5（带规则卡）')
            if errs: bad.append(dict(id=sid, errors=errs)); continue
            recs.append(dict(id=sid, meta=meta, target=target, inputs={v: build_input(v, pid, ind_used, cost, labels, tail) for v in ('card', 'tag', 'none')}))
            stats[(pid, it['judgment'], meta['synthetic'])] += 1
        # 汇总（子任务 3）：输入带逐项判断结果
        sm = S['SUMMARY']
        res = '\n'.join(f"- {it['indicator']}（{it['category']}）：{it['judgment']}" + (f"，{'、'.join(it['cost_items'])}，{it['direction']}" if it['cost_items'] else '') for it in S['ITEMS'])
        tail = ['【逐项判断结果】\n' + res, '【任务】按规则汇总：主要成本项是否都有指标覆盖，列出无对应成本项和需人工核对的关键指标。输出 JSON。']
        errs = []
        exp_unlinked = [it['indicator'] for it in S['ITEMS'] if it['judgment'] == '无对应成本项']
        if sorted(sm['unlinked']) != sorted(exp_unlinked): errs.append(f'summary unlinked mismatch: {sm["unlinked"]} vs {exp_unlinked}')
        exp_manual = [it['indicator'] for it in S['ITEMS'] if it['judgment'] == '需人工核对']
        if sorted(sm.get('manual', [])) != sorted(exp_manual): errs.append(f"summary manual mismatch: {sm.get('manual')} vs {exp_manual}")
        inp_tag = build_input('tag', pid, ind, cost, labels, tail)
        errs += [f'think quote not in input: {q[:30]}' for q in quotes_ok(sm['think'], inp_tag)]
        e2, _ = check_arith(sm['think'], inp_tag, card_numbers()); errs += e2
        out = dict(task='规则专项', rule_id=RULE, step='汇总', covered=sm['covered'], uncovered_cost_items=sm['uncovered'], unlinked_key_indicators=sm['unlinked'], need_manual_check=sm.get('manual', []), suggestion=sm['suggestion'])
        sid = f'{RULE}_{pid}_summary'
        if errs: bad.append(dict(id=sid, errors=errs))
        else:
            recs.append(dict(id=sid, meta=dict(project_id=pid, rule_id=RULE, step='汇总', source='真实报告；汇总由老师带规则卡生成', synthetic=False,
                                               status=STATUS, reasoning_author='claude-opus-5-5（带规则卡）'),
                             target=f"<think>\n{CHK['QUOTE'].sub(lambda m: '“' + m.group(1) + '”', sm['think'])}\n</think>\n" + json.dumps(out, ensure_ascii=False),
                             inputs={v: build_input(v, pid, ind, cost, labels, tail) for v in ('card', 'tag', 'none')}))
            stats[(pid, '汇总', False)] += 1
    def dump(name, variant):
        with open(os.path.join(OUT, name), 'w', encoding='utf-8') as fo:
            for r in recs:
                fo.write(json.dumps(dict(id=r['id'], meta=dict(r['meta'], input_variant=variant), system=SYSTEM,
                                         messages=[dict(role='user', content=r['inputs'][variant]), dict(role='assistant', content=r['target'])]), ensure_ascii=False) + '\n')
    dump('train_tag.jsonl', 'tag'); dump('eval_card.jsonl', 'card'); dump('eval_tag.jsonl', 'tag'); dump('eval_none.jsonl', 'none')
    with open(os.path.join(OUT, 'preview.md'), 'w', encoding='utf-8') as fo:
        fo.write(f"# {RULE} 专项样本预览\n\n规则卡：rules/cards/{RULE}.yaml（{CARD['status']}）\n\n")
        for r in recs:
            fo.write(f"## {r['id']} · {r['meta']['step']} · {r['meta'].get('judgment', '')} · {r['meta']['source']}\n\n**输入（只带标签）**\n\n```\n{r['inputs']['tag']}\n```\n\n**输出**\n\n```\n{r['target']}\n```\n\n")
    n_syn = sum(1 for r in recs if r['meta']['synthetic'])
    rep = [f'{RULE}: accepted {len(recs)} (synthetic {n_syn})  rejected {len(bad)}',
           '分布（项目, 判断, 是否合成）: ' + str(dict(sorted(stats.items()))),
           f"最长输入（带规则卡）: {max(len(SYSTEM) + len(r['inputs']['card']) + len(r['target']) for r in recs)} 字"] + [f"REJECTED {b['id']}: {b['errors']}" for b in bad]
    open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8').write('\n'.join(rep)); print('\n'.join(rep))

main()
