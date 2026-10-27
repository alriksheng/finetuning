"""仿写样本构建与核验（样本生成标准第十四节）：输入取自 data/cand/cand_inputs.jsonl 里的真实小节（专家没有提过意见的小节），
思考和意见由标注者（Claude Code）按专家口径撰写，本脚本把标注拼成与 data/out/samples.jsonl 同格式的样本，并做与 build.py 同口径的核验。
Usage: python3 -I build_imit.py <data_dir> <标注文件.py ...>   （默认输出 data/out_imit/）
标注文件里定义 ITEMS = [dict(src='C_P009_S012', think='...', findings=[dict(rule=, label=, part=, clauses=[], evidence=[], problem=, suggestion=, reason=)] ), ...]
核验：引文逐字在输入中；条文编号在输入的条文中且在思考里引用；规则在输入的审核重点里；意见文字风格（禁用词、长度、不写条文编号、不整句照抄输入）；
      意见里的数字须在输入中或思考中验算过；思考不称“专家”为意见来源、不引用输入没有的表号页码；思考不少于 450 字；
      具体性：意见必须带数字、引文或输入中的具体词语，不能是“补充 XX”“加强合理性分析”式的泛泛要求（对应不成立意见里 61% 的泛泛无针对）。"""
import sys, os, re, json, runpy, difflib, collections, yaml
D = sys.argv[1]; FILES = sys.argv[2:]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(D, os.environ.get('IMIT_OUT', 'out_imit')); os.makedirs(OUT, exist_ok=True)
CHK = runpy.run_path(os.path.join(HERE, 'checks.py')); RENDER = runpy.run_path(os.path.join(HERE, 'render_opinion.py'))
NUM, check_arith = CHK['NUM'], CHK['check_arith']
squash = lambda s: re.sub(r'\s+', '', s)
QUOTE = re.compile(r'「([^」]+)」'); tr = lambda s: QUOTE.sub(lambda m: '“' + m.group(1) + '”', s).strip()
ID_RE = re.compile(r'\b(P\d+(?:-[A-Za-z0-9]+)+)\b')
THINK_MIN = 450
STYLE = dict(max_chars=260, max_quotes=2, max_quote_len=12, max_copy=24, banned=('本小节', '请到', '看不到', '没有', '只', '却', '这些', '我们', '完全', '毫无', '根本', '绝对', '不了'))
SRC_EXPERT = re.compile(r'专家(?:们)?(?:另|也|还)?(?:要求|所提|提到|引用|称|指出|质疑|认为|意见|表述|所指|所述|按原|所引|提出|建议|关于|明确|在意见|的意见|原话|所称|所说|指定|要点|已提出|已采纳|曾提)')
ENT_REF = re.compile(r'(?<![代图])表\s?\d+(?:[-－—]\d+)*|附件\s?\d+|第\s?\d+\s?页')
GENERIC = re.compile(r'^(?:建议)?(?:进一步)?(?:补充|完善|加强|说明|明确|细化)[^，。；]{0,14}(?:合理性|必要性|可行性|依据|情况|内容|信息)[^，。；]{0,6}[。]?$')
PART = {'basic': '基本情况部分', 'abs_basic': '基本情况部分', 'cost': '成本核算分析部分', 'abs_cost': '成本核算分析部分', 'perf': '绩效基线分析部分', 'abs_perf': '绩效基线分析部分',
        'proc': '业务流程分析部分', 'abs_proc': '业务流程分析部分', 'concl': '分析结论部分', 'abs_concl': '分析结论部分', 'issue': '存在问题及建议部分', 'abs_issue': '存在问题及建议部分', 'work': '工作开展情况部分'}
CLAUSES = {c['clause_id']: c for c in json.load(open(f'{D}/clauses/clauses.json', encoding='utf-8'))}
RULES = {r['rule_id']: r for r in yaml.safe_load(open(f'{D}/rules/rules.yaml', encoding='utf-8'))}
PROJ = json.load(open(f'{D}/specs/projects.json', encoding='utf-8'))
INP = {r['id']: r for r in map(json.loads, open(f'{D}/cand/cand_inputs.jsonl', encoding='utf-8'))}
items = []
for f in FILES: items += runpy.run_path(f)['ITEMS']
ok, bad = [], []
for it in items:
    errs = []; r = INP.get(it['src'])
    if not r: bad.append(dict(id=it['src'], errors=['输入不存在'])); continue
    prompt = r['prompt']
    for old, new in it.get('edits', []):          # 人造错：对真实小节做最小改动（登记在案，计入合成）；old 必须在小节正文中恰好出现一次
        head_, body_ = prompt.split('【报告段落】', 1); sec_, tail_ = body_.split('【事实卡】', 1)
        if sec_.count(old) != 1: errs.append(f'edit anchor 出现 {sec_.count(old)} 次: {old[:20]}'); continue
        prompt = head_ + '【报告段落】' + sec_.replace(old, new, 1) + '【事实卡】' + tail_
    hay = squash(prompt); pid = r['project']; P = PROJ[pid]
    body = prompt.split('【报告段落】')[-1].split('【事实卡】')[0]
    label = re.match(r'\s*\[([^\]]+)\]', body).group(1)
    mapped = ID_RE.findall(prompt.split('【条文】')[1].split('【审核重点】')[0]); focus = re.findall(r'（(R-[A-Z0-9-]+|L3-07)）', prompt.split('【审核重点】')[1])
    think = it['think'].strip(); model_items = []; F = []
    for k, fd in enumerate(it['findings']):
        if fd['rule'] not in focus: errs.append(f"rule {fd['rule']} 不在审核重点")
        if fd['rule'] not in RULES: errs.append(f"unknown rule {fd['rule']}")
        for c in fd['clauses']:
            if c not in mapped: errs.append(f'clause {c} 不在输入的条文中')
            if c not in think: errs.append(f'clause {c} 没有在思考中引用')
        evs = []
        for q in fd['evidence']:
            if squash(q) not in hay: errs.append(f'引文不在输入: {q[:30]}')
            evs.append(dict(source='报告', loc=label, quote=q))
        if not evs: errs.append('没有引文')
        txt = fd['problem'] + fd['suggestion']; model_items.append(txt)
        if len(txt) > STYLE['max_chars']: errs.append(f'意见 {len(txt)} 字 > {STYLE["max_chars"]}')
        if len(QUOTE.findall(txt)) > STYLE['max_quotes']: errs.append('意见引用原文次数过多')
        if any(len(q) > STYLE['max_quote_len'] for q in QUOTE.findall(txt)): errs.append('意见里引用的原文过长')
        if fd['problem'] and fd['problem'][-1] not in '，。': errs.append('problem 应以“，”或“。”结尾')
        if not fd['suggestion'].endswith('。'): errs.append('suggestion 应以“。”结尾')
        if not fd.get('reason'): errs.append('缺 reason（仿写依据）')
        if GENERIC.match(fd['suggestion'].strip()) and not fd['problem']: errs.append('意见过于泛泛')
        # 具体性：带数字，或带「引文」，或含输入小节中的具体词（4 字组），且这些词不来自条文/审核重点
        gen_text = prompt.split('【条文】')[1]
        grams = {txt[i:i + 4] for i in range(len(txt) - 3) if re.fullmatch(r'[一-龥]{4}', txt[i:i + 4])}
        spec = [g for g in grams if g in squash(body) and g not in gen_text]
        if not (re.search(r'\d', txt) or QUOTE.search(txt) or len(spec) >= 2): errs.append(f'意见缺少具体性（无数字/引文/输入中的具体词）: {txt[:30]}')
        F.append(dict(issue_type=fd['label'], rule_id=fd['rule'], verdict='问题', evidence=evs, clause_ids=fd['clauses'],
                      basis_type=('政策+评审经验' if '依据：评审经验' in think + txt and fd['clauses'] else ('评审经验' if not fd['clauses'] else '政策')),
                      problem=fd['problem'], suggestion=fd['suggestion'], part=fd.get('part') or PART.get(r['meta']['kind'], '成本核算分析部分')))
    if not F: errs.append('没有意见')
    ans = ''.join(model_items)
    for w_ in STYLE['banned']:
        if w_ in ans: errs.append(f'意见含禁用词 {w_}')
    if ID_RE.search(ans): errs.append('意见里写了条文编号')
    sm = difflib.SequenceMatcher(None, squash(ans), hay, autojunk=False).find_longest_match(0, len(squash(ans)), 0, len(hay))
    if sm.size > STYLE['max_copy']: errs.append(f'意见整句照抄输入 {sm.size} 字')
    if SRC_EXPERT.search(think + ans): errs.append('思考或意见把“专家”当作意见来源')
    for e_ in set(ENT_REF.findall(think)):
        if squash(e_) not in hay and squash(e_) not in squash(ans): errs.append(f'思考引用了输入中没有的 {e_}')
    for q in QUOTE.findall(think):
        if not all(squash(x) in hay for x in re.split(r'…+', q) if x.strip()): errs.append(f'思考引文不在输入: {q[:30]}')
    for i in set(ID_RE.findall(think)):
        if i not in mapped: errs.append(f'思考引用的条文 {i} 不在输入中')
    rules_text = ' '.join(json.dumps(RULES.get(fd['rule'], {}), ensure_ascii=False) for fd in it['findings'])
    e_ar, derived = check_arith(think, prompt + ' ' + rules_text); errs += [f'think {e}' for e in e_ar]
    flat = re.sub(r'[\s,]', '', prompt)
    for n in re.findall(NUM, ans):
        q = n.replace(',', '')
        if len(q.replace('.', '')) >= 2 and q not in flat and q not in derived: errs.append(f'意见数字 {n} 不在输入中也没有在思考里验算')
    if len(think) < THINK_MIN: errs.append(f'思考过短 {len(think)} 字')
    F.sort(key=lambda f: min([hay.find(squash(e['quote'])) for e in f['evidence'] if hay.find(squash(e['quote'])) >= 0] or [10 ** 9]))
    obj = dict(task='小节审核', findings=F); rendered = RENDER['render'](obj)
    sysmsg = r['system']; js = json.dumps(obj, ensure_ascii=False); asst = f"<think>\n{tr(think)}\n</think>\n{js}"
    n_chars = len(sysmsg) + len(prompt) + len(asst)
    if n_chars > 9500: errs.append(f'过长 {n_chars} 字')
    sid = 'V7_' + it['src'][2:] + it.get('suffix', '')
    rec = dict(id=sid, meta=dict(project=P['name'], project_id=pid, group=P.get('group'), report_version=P['report_version'], review_date='待填',
                                 sample_type='多问题' if len(F) > 1 else '缺失', task_type='小节审核', input_scope=f"小节：{label}", reachability='全部可达', target_type='full',
                                 evidence=[e['quote'] for f in F for e in f['evidence']], unreachable_evidence=[], rule_ids=[f['rule_id'] for f in F], focus_rule_ids=focus, clause_ids=sorted({c for f in F for c in f['clause_ids']}),
                                 mapped_clause_ids=mapped, expert_text=None, text_sources=[dict(source='仿写（模型撰写）', reason=fd['reason']) for fd in it['findings']],
                                 opinion_text=tr(rendered), opinion_tags=RENDER['render_tags'](obj), basis=RENDER['render_basis'](obj, CLAUSES), source_kind='imitation', members=None,
                                 synthetic=True, reasoning_author='claude-sonnet-5-5', status='仿写，待专家抽查', annotation=P.get('annotation'), approx_chars=n_chars, imit_batch=os.path.basename(FILES[0]) if FILES else None, edits=[dict(old=a, new=b) for a, b in it.get('edits', [])] or None),
               system=sysmsg, messages=[dict(role='user', content=prompt), dict(role='assistant', content=asst)])
    if errs: rec['errors'] = errs; bad.append(rec)
    else: ok.append(rec)
with open(f'{OUT}/samples.jsonl', 'w', encoding='utf-8') as fo:
    for r in ok: fo.write(json.dumps(r, ensure_ascii=False) + '\n')
with open(f'{OUT}/rejected.jsonl', 'w', encoding='utf-8') as fo:
    for r in bad: fo.write(json.dumps(r, ensure_ascii=False) + '\n')
with open(f'{OUT}/preview.md', 'w', encoding='utf-8') as fo:
    fo.write('# 仿写样本预览\n\n')
    for r in ok: fo.write(f"## {r['id']} · {r['meta']['rule_ids']}\n\n**输入（节选）**\n\n```\n{r['messages'][0]['content'].split('【事实卡】')[0][-1800:]}\n```\n\n**输出**\n\n```\n{r['messages'][1]['content']}\n```\n\n---\n\n")
c = collections.Counter(rid for r in ok for rid in r['meta']['rule_ids'])
print(f'通过 {len(ok)} 条，被拒 {len(bad)} 条；各规则意见数 {dict(c)}')
for r in bad: print(' ✗', r.get('id'), r.get('errors'))
