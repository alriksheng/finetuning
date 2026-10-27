"""思维链重构 v2：按“定位 → 摘录 → 冲突 → 规则 → 意见”重写推理，输入加【规则要点】（2026-10-27 起，用户决定）。

用法：python3 -I scripts/build_cot_v2.py data data/cot_v2/pilot01.py [更多批次文件…]
批次文件中每项：
  sid      样本编号（训练文件中该条输入的 md5 前 8 位；反事实无问题样本用 fix: 加 CF 编号）
  lead     定位（一句，≤60 字）
  points   与输出 findings 一一对应：{conflict, rule_quote, opinion}；无问题样本为 [{check_rule, conflict, rule_quote}]
           conflict    冲突分析：原文与标准（条文编号或规则要点）的差异，由人工逐条撰写
           rule_quote  从【规则要点】中该规则的文字里逐字摘出的一句（提出条件或不提条件）
           opinion     一句话概括拟提意见（不整句复制专家原话）
程序生成：摘录（取自输出 evidence，保证一致）、规则行的编号与标签、JSON 字段顺序、系统提示、【规则要点】。
核验：「」引文逐字在输入中；冲突行引用的条文编号在输入中、且覆盖该意见的 clause_ids；rule_quote 逐字出自该规则的 brief；
     规则在审核重点内；算式复算；定位不超过 60 字；整条不超过 10500 字。
输出：data/cot_v2/out/（samples.json、preview.md、report.txt）。
"""
import hashlib, json, os, re, runpy, sys
import yaml

DATA = sys.argv[1]
BATCHES = sys.argv[2:]
OUT = os.path.join(DATA, 'cot_v2', 'out')
LEAD_MAX, CHAR_MAX = 60, 10500
CN = '一二三四五六七八九十'
KEY_ORDER = ('evidence', 'problem', 'rule_id', 'issue_type', 'verdict', 'clause_ids', 'basis_type', 'suggestion', 'part')
squash = lambda s: re.sub(r'\s+', '', s)
CHK = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'checks.py'))
SYSTEM = ('你是成本预算绩效分析报告的评审专家。只能依据输入中给出的报告原文、事实卡、条文和规则要点作出判断。'
          '先在思考中按以下顺序进行：用一句话定位本小节；对每个问题，先逐字摘录报告或事实卡中的靶向原句，'
          '再对照条文（标注条文编号）或【规则要点】分析冲突点，再确定规则编号并引用对应的规则要点，最后概括拟提意见。'
          '【审核重点】列出本小节应检查的方面，只对发现问题的方面出具意见，rule_id 取审核重点中括注的规则编号；没有问题的方面不写。'
          '然后输出 JSON：findings 中每条依次包含 evidence（报告或事实卡的逐字摘录，与思考中的摘录一致）、problem、rule_id、issue_type、'
          'verdict（问题／证据不足／无问题）、clause_ids、basis_type（政策／评审经验／政策+评审经验）、suggestion、part。'
          'problem 和 suggestion 用书面语，先写问题再写建议，简明扼要，不整句摘抄报告原文，不写条文编号；意见使用建议性措辞。')


def load_sources():
    src = {}
    for x in json.load(open(os.path.join(DATA, 'train_v2', 'audit_train_think.json'), encoding='utf-8')):
        u = x['conversations'][0]['value']
        src.setdefault(hashlib.md5(u.encode()).hexdigest()[:8], dict(system=x['system'], prompt=u, answer=x['conversations'][1]['value']))
    for l in open(os.path.join(DATA, 'out_fix', 'samples_fix.jsonl'), encoding='utf-8'):
        r = json.loads(l)
        src['fix:' + r['id']] = dict(system=r['system'], prompt=r['messages'][0]['content'], answer=r['messages'][1]['content'])
    return src


def focus(prompt):
    m = re.search(r'【审核重点】(.*?)\n', prompt)
    return [i for _, i in re.findall(r'([^；（(]+)[（(]([A-Z][A-Z0-9\-]*|L\d-\d+)[）)]', m.group(1))] if m else []


def add_focus_items(prompt):
    """反事实样本早于 v2，审核重点补 R-COST-CHECK（与 build_v3 一致）。"""
    if '（R-COST-CHECK）' in prompt or '【审核重点】' not in prompt:
        return prompt
    return re.sub(r'(【审核重点】[^\n]*)', lambda m: m.group(1) + '；成本数据一致性（R-COST-CHECK）', prompt, count=1)


def main():
    rules = {r['rule_id']: r for r in yaml.safe_load(open(os.path.join(DATA, 'rules', 'rules_v2.yaml'), encoding='utf-8'))}
    src = load_sources()
    ok, bad, stats = [], [], []
    for bf in BATCHES:
        for a in runpy.run_path(bf)['PILOT']:
            errs, s = [], src.get(a['sid'])
            if not s:
                bad.append((a['sid'], ['找不到样本'])); continue
            prompt = add_focus_items(s['prompt'])
            fids = focus(prompt)
            block = '【规则要点】\n' + '\n'.join(f"{rules[r]['tag']}（{r}）：{rules[r]['brief']}" for r in fids)
            prompt = prompt.replace('\n\n【任务】', '\n\n' + block + '\n\n【任务】', 1)
            ans = json.loads(re.search(r'</think>\s*(.*)$', s['answer'], re.S).group(1))
            F = ans['findings']
            if len(a['lead']) > LEAD_MAX: errs.append(f"定位 {len(a['lead'])} 字，超过 {LEAD_MAX}")
            parts = [f"定位：{a['lead']}"]
            if not F:                                                  # 无问题样本
                for i, p in enumerate(a['points']):
                    r = p['check_rule']
                    if r not in fids: errs.append(f'{r} 不在审核重点')
                    if p['rule_quote'] not in rules[r]['brief']: errs.append(f'{r} 规则引用不在规则要点中')
                    parts.append(f"核对{CN[i]}（{r}）\n冲突：{p['conflict']}\n规则：{r}（{rules[r]['tag']}）——「{p['rule_quote']}」\n结论：不提出意见。")
                parts.append('结论：本小节未发现需要提出意见的问题。')
            else:
                if len(a['points']) != len(F): errs.append(f"points {len(a['points'])} 条，findings {len(F)} 条")
                for i, (f, p) in enumerate(zip(F, a['points'])):
                    r = f['rule_id']
                    if r not in fids: errs.append(f'要点{CN[i]} {r} 不在审核重点')
                    if p['rule_quote'] not in rules[r]['brief']: errs.append(f'要点{CN[i]} 规则引用不在 {r} 的规则要点中')
                    for c in f.get('clause_ids') or []:
                        if c not in p['conflict']: errs.append(f'要点{CN[i]} 冲突行未引用条文 {c}')
                    qs = [e['quote'] for e in f.get('evidence') or [] if isinstance(e, dict) and e.get('quote')]
                    parts.append(f"要点{CN[i]}（{f.get('issue_type', '')}）\n摘录：" + '；'.join(f'「{q}」' for q in qs)
                                 + f"\n冲突：{p['conflict']}\n规则：{r}（{rules[r]['tag']}）——「{p['rule_quote']}」\n意见：{p['opinion']}")
            think = '\n\n'.join(parts)
            hay = squash(prompt)
            for q in re.findall(r'「(.*?)」', think, re.S):
                if not all(squash(seg) in hay for seg in q.split('…') if squash(seg)): errs.append(f'引文不在输入中：「{q[:24]}」')
            for c in set(re.findall(r'\bP\d+(?:-[A-Za-z0-9]+)+', think)):
                if f'[{c}｜' not in prompt: errs.append(f'条文 {c} 不在输入中')
            e2, _ = CHK['check_arith'](think, prompt)
            errs += [e for e in e2 if e.startswith('arith')]
            new_ans = dict(ans, findings=[{k: f[k] for k in KEY_ORDER if k in f} | {k: v for k, v in f.items() if k not in KEY_ORDER} for f in F])
            system = SYSTEM + '\n' + s['system'].split('\n')[-1]
            answer = f'<think>\n{think}\n</think>\n\n' + json.dumps(new_ans, ensure_ascii=False)
            total = len(system) + len(prompt) + len(answer)
            if total > CHAR_MAX: errs.append(f'整条 {total} 字，超过 {CHAR_MAX}')
            rec = dict(sid=a['sid'], system=system, prompt=prompt, answer=answer, think_chars=len(think), old_think_chars=len(re.search(r'<think>(.*?)</think>', s['answer'], re.S).group(1).strip()), total=total)
            (bad.append((a['sid'], errs)) if errs else ok.append(rec))
    os.makedirs(OUT, exist_ok=True)
    json.dump([dict(system=r['system'], conversations=[{'from': 'human', 'value': r['prompt']}, {'from': 'gpt', 'value': r['answer']}]) for r in ok],
              open(os.path.join(OUT, 'samples.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, 'preview.md'), 'w', encoding='utf-8') as fo:
        fo.write('# 思维链重构 v2 试写预览\n\n')
        for r in ok:
            fo.write(f"## {r['sid']} · 推理 {r['old_think_chars']} → {r['think_chars']} 字 · 整条 {r['total']} 字\n\n```\n{r['prompt'][-1800:]}\n```\n\n```\n{r['answer']}\n```\n\n---\n\n")
    n = len(ok)
    rep = (f'通过 {n}，拒收 {len(bad)}；推理平均 {sum(r["old_think_chars"] for r in ok) / max(1, n):.0f} → {sum(r["think_chars"] for r in ok) / max(1, n):.0f} 字；'
           f'整条最长 {max([r["total"] for r in ok] or [0])} 字\n' + '\n'.join(f'拒收 {i}：{e}' for i, e in bad))
    open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8').write(rep + '\n')
    print(rep)


if __name__ == '__main__':
    main()
