"""样本构建与核验（唯一的构建脚本）。标准见 data/样本生成标准.md。

Usage: python3 -I scripts/build.py data
输入：data/specs/<项目>.py（统一规格）、data/specs/projects.json、data/raw/reports、data/raw/reviews、data/clauses、data/rules
输出：data/out/（samples.jsonl、samples_answer_only.jsonl、candidates_no_issue.jsonl、rejected.jsonl、train_sharegpt.json、preview.md、report.txt）
"""
import sys, os, re, json, glob, runpy, collections, difflib
import yaml

DATA = sys.argv[1]
OUT = os.path.join(DATA, os.environ.get('BUILD_OUT', 'out')); os.makedirs(OUT, exist_ok=True)
RULE_OVERRIDES = json.load(open(os.path.join(DATA, 'label_review/rule_overrides.json'), encoding='utf-8')) if os.environ.get('RULE_OVERRIDES') == '1' else []
HERE = os.path.dirname(os.path.abspath(__file__))
CHK = runpy.run_path(os.path.join(HERE, 'checks.py'))
RENDER = runpy.run_path(os.path.join(HERE, 'render_opinion.py'))
NUM, check_arith, squash_find, span = CHK['NUM'], CHK['check_arith'], CHK['squash_find'], CHK['span']
norm = lambda s: re.sub(r'\s+', ' ', s).strip()
squash = lambda s: re.sub(r'\s+', '', s)
QUOTE = re.compile(r'「([^」]+)」')
ID_RE = re.compile(r'\b(P\d+(?:-[A-Za-z0-9]+)+)\b')
tr = lambda s: QUOTE.sub(lambda m: '“' + m.group(1) + '”', s).strip()
cline = lambda c: f"[{c['clause_id']}｜{c['effective_from']}] {c['text']}"

THINK_MIN = 450                      # 每条样本推理不少于 450 字（事实卡抽取、漏项清单除外）
MAX_CHARS = 8600                     # 字符数上限（代理指标；2026-10-27 因审核重点统一加入 R-COST-CHECK，由 8500 放宽到 8600）；cutoff_len 按实测 token 长度的 P95 设定
STYLE = dict(max_chars=260, max_quotes=2, max_quote_len=12, max_copy=24,
             banned=('本小节', '请到', '看不到', '没有', '只', '却', '这些', '我们', '完全', '毫无', '根本', '绝对', '不了'))   # 只约束模型撰写的意见
SRC_EXPERT = re.compile(r'专家(?:们)?(?:另|也|还)?(?:要求|所提|提到|引用|称|指出|质疑|认为|意见|表述|所指|所述|按原|所引|提出|建议|关于|明确|在意见|的意见|原话|所称|所说|指定|要点|已提出|已采纳|曾提)')   # 推理和模型撰写的意见都以评审人口吻写，不得把“专家”当作意见来源
ENT_REF = re.compile(r'(?<![代图])表\s?\d+(?:[-－—]\d+)*|附件\s?\d+|第\s?\d+\s?页')
REF_IN_EXPERT = re.compile(r'〔\d{4}〕\d+号|GB\s*\d+[—\-]\d+|(?<!\d)(19|20)\d{2}(?=年|预算|度)')   # 专家原话中的文号、标准编号、年份属于引用
SYSTEM_BASE = ("你是成本预算绩效分析报告的评审专家。只能依据输入中给出的报告原文、事实卡和条文作出判断。"
               "先在思考中逐字摘录相关证据、核对条文并标注条文编号；规则的判断步骤也可以写在思考中，标注“依据：评审经验”。"
               "然后输出 JSON：findings 中每条包含 issue_type、rule_id、verdict（问题／提示核实／证据不足／无问题）、evidence（报告或事实卡的逐字摘录）、"
               "clause_ids、basis_type（政策／评审经验／政策+评审经验）、problem、suggestion。"
               "problem 和 suggestion 用书面语，先写问题再写建议，简明扼要，不整句摘抄报告原文，不写条文编号；"
               "输入中无法确认的问题，verdict 写“提示核实”，说明应核对哪一章的什么内容，不下结论；证据不足时写明需要核实什么。意见使用建议性措辞。"
               "【审核重点】列出本小节应检查的方面，逐项检查，只对发现问题的方面出具意见，rule_id 取审核重点中括注的规则编号；没有问题的方面不写。"
               "事实卡抽取、漏项逐项判断按【任务】要求的字段输出。")
system_for = lambda task_type: SYSTEM_BASE + f"\n【任务类型】{task_type}"
TASK_TYPE = {'事实卡抽取': '事实卡抽取', '漏项清单': '漏项逐项判断'}
TASK_FIXED = {'pack': '对比两侧小节，提出评审意见。', 'section': '对本小节提出评审意见。'}

CLAUSES = {c['clause_id']: c for c in json.load(open(os.path.join(DATA, 'clauses/clauses.json'), encoding='utf-8'))}
RULES = {r['rule_id']: r for r in yaml.safe_load(open(os.path.join(DATA, 'rules/rules.yaml'), encoding='utf-8'))}
PROJ = json.load(open(os.path.join(DATA, 'specs/projects.json'), encoding='utf-8'))
FOCUS = yaml.safe_load(open(os.path.join(DATA, 'specs/focus_map.yaml'), encoding='utf-8'))      # 章节 / 比对包 → 审核重点
FOCUS_MAX = 13


def focus_for(ptype, kinds, pack_label):
    """审核重点：比对包取 pack 条目，否则按小节 kind（摘要沿用正文）合并。"""
    fm = FOCUS[ptype]
    if pack_label and ('pack:' + pack_label) in fm: return list(fm['pack:' + pack_label])
    out = []
    for k in kinds:
        for r in fm[k[4:] if k.startswith('abs_') else k]:
            if r not in out: out.append(r)
    return out
focus_line = lambda rs: '【审核重点】' + '；'.join(f"{RULES[r]['tag']}（{r}）" for r in rs)


class Report:
    def __init__(self, pid):
        self.pid = pid
        if PROJ[pid].get('pdf_pages'):
            pages = json.load(open(os.path.join(DATA, 'raw/reports', PROJ[pid]['pdf_pages']), encoding='utf-8'))
            self.pages = {p['pdf_page']: dict(printed=p['printed'], text=norm(p['text'])) for p in pages}
        else:
            self.lines = open(os.path.join(DATA, f'raw/reports/{pid}.md'), encoding='utf-8').read().split('\n')
    def section_text(self, sec):
        if hasattr(self, 'pages'):
            if sec.get('chunks'):
                out = []
                for pg, st, en in sec['chunks']:
                    t = self.pages[pg]['text']
                    if st:
                        i = squash_find(t, st); t = t[i:] if i is not None else t
                    if en:
                        j = squash_find(t, en, end=True); t = t[:j] if j is not None else t
                    out.append(t)
                return norm(' '.join(out))
            t = ' '.join(self.pages[p]['text'] for p in sec['pages'])
            if sec.get('start'):
                i = squash_find(t, sec['start']); t = t[i:] if i is not None else t
            if sec.get('end'):
                j = squash_find(t, sec['end'], end=True); t = t[:j] if j is not None else t
            return norm(t)
        return '\n'.join('\n'.join(self.lines[a - 1:b]) for a, b in sec['lines'])
    def whole(self):
        return ' '.join(p['text'] for p in self.pages.values()) if hasattr(self, 'pages') else '\n'.join(self.lines)
    def label(self, sec):
        if not hasattr(self, 'pages'): return sec['loc']
        pp = [self.pages[p]['printed'] for p in ([c[0] for c in sec['chunks']] if sec.get('chunks') else sec['pages'])]
        return f"第{pp[0]}页" + (f"–{pp[-1]}页" if len(pp) > 1 else '') + ' ' + sec['loc']


def special_output(s, ttype):
    """事实卡抽取、漏项逐项判断：按任务要求的字段输出。"""
    errs, ans = [], s['answer_raw'].strip()
    if s['type'] == '事实卡抽取':
        fields, prev = [], None
        for ln in ans.split('\n'):
            m = re.match(r'^- (.+?)：(.+)（(第\d+页)）(?:“(.+)”|同上)$', ln)
            if not m: errs.append(f'factcard line unparsable: {ln[:20]}'); continue
            q = m.group(4) or prev; prev = q
            fields.append(dict(name=m.group(1), value=m.group(2), page=m.group(3), quote=q))
        return dict(task=ttype, fields=fields), errs
    first, rest = ans.split('\n', 1)
    item = re.sub(r'^【清单项】', '', s['task']).split('？')[0] + '？'
    return dict(task=ttype, item=item, answer=first.rstrip('。'), evidence=[], explanation=rest), errs


PART_OK = lambda s: s.endswith('部分') or s in ('总体', '总体意见', '降本增效情况', '“三个标准”建立情况', '“三个标准”设置情况')   # 部分名取自原评审意见


def point_text(p, errs):
    """要点的意见文字：专家原话（只做登记过的最小改动）或模型撰写。"""
    if not PART_OK(p['part']): errs.append(f"{p['id']}: unknown part {p['part']}")
    if p['text_source'] == '模型撰写':
        if not p.get('reason'): errs.append(f"{p['id']}: 模型撰写的要点须写明不用专家原话的原因")
        it = p['problem'] + p['suggestion']                          # 公文风格量化检查（style/公文风格指南.md）
        if len(it) > 200: errs.append(f"{p['id']}: style: item {len(it)} chars > 200")
        if max(len(c) for c in re.split(r'[。；]', it)) > 100: errs.append(f"{p['id']}: style: clause > 100 chars")
        if it.count('仅') > 1: errs.append(f"{p['id']}: style: “仅” used more than once")
        if it.count('（') > 2: errs.append(f"{p['id']}: style: more than 2 parentheses")
        if p['problem'] and p['problem'][-1] not in '，。': errs.append(f"{p['id']}: style: problem should end with “，”或“。”")
        if not p['suggestion'].endswith('。'): errs.append(f"{p['id']}: style: suggestion should end with “。”")
        return p['problem'], p['suggestion'], []
    tx, edits = p['expert_text'].strip(), []
    for old, new, why in p.get('edits', []):
        if old == '$END': tx = tx.rstrip('。') + '；' + new
        elif old in tx: tx = tx.replace(old, new, 1)
        else: errs.append(f"{p['id']}: edit anchor not found: {old}"); continue
        edits.append(dict(old=old, new=new, reason=why))
    if not tx.endswith('。'): tx += '。'
    m = re.search('，(?=建议)', tx)
    return (tx[:m.end()], tx[m.end():], edits) if m and m.start() > 0 else ('', tx, edits)


def main():
    ok, bad, stats = [], [], collections.Counter()
    for f in sorted(glob.glob(os.path.join(DATA, 'specs/P*.py'))):
        spec = runpy.run_path(f)
        for ov in RULE_OVERRIDES:                                      # 规则标签复核（data/label_review/rule_overrides.json，环境变量 RULE_OVERRIDES=1 启用）
            for s_ in spec['SAMPLES']:
                if s_.get('id') != ov['sample']: continue
                hit = [p_ for p_ in s_.get('points', []) if p_['label'] == ov['issue'] and (p_.get('rules') or [None])[0] == ov['old']]
                if len(hit) != 1: bad.append(dict(id=ov['sample'], errors=[f"rule override not applied: {ov['issue']} {ov['old']}→{ov['new']} (matches {len(hit)})"])); continue
                hit[0]['rules'] = [ov['new']] + list(hit[0]['rules'][1:])
                if ov['new'] not in s_['rules']: s_['rules'] = list(s_['rules']) + [ov['new']]
                if not any(ov['old'] in (q.get('rules') or []) for q in s_['points']): s_['rules'] = [r for r in s_['rules'] if r != ov['old']]
        pid = spec['SOURCE']; P = PROJ[pid]; rep = Report(pid)
        secs, packs, cmap = spec['SECTIONS'], spec['PACKS'], spec['CLAUSE_MAP']
        review = norm(open(os.path.join(DATA, f'raw/reviews/{pid}.txt'), encoding='utf-8').read())
        whole = rep.whole()
        sec_text = {k: rep.section_text(v) for k, v in secs.items()}
        # ---- 事实卡：摘录由锚点切片，数值须出现在摘录中 ----
        card_by = {}
        for fld in spec['CARD']:
            try:
                src = sec_text[fld['sec']] if fld.get('sec') else (rep.pages[fld['page']]['text'] if fld.get('page') else whole)
                q = span(src, fld['qa'], fld.get('qb'))
            except KeyError as e:
                bad.append(dict(id=f'{pid}_CARD', errors=[f"card {fld['name']}: {e}"])); continue
            for num in re.findall(r'\d[\d,\.]*\d|\d', fld['value']):
                if re.fullmatch(r'(19|20)\d\d', num): continue
                if len(num.replace(',', '').replace('.', '')) >= 2 and num.replace(',', '') not in q.replace(',', ''):
                    bad.append(dict(id=f'{pid}_CARD', errors=[f"card {fld['name']}: value number {num} not in quote"]))
            card_by[fld['name']] = dict(name=fld['name'], value=fld['value'], loc=fld['loc'], quote=q)
        for s in spec['SAMPLES']:
            errs = []
            unit = s['unit']
            if unit in packs:
                a, b = packs[unit]['a'], packs[unit]['b']
                blocks, kind_secs = [('比对包·甲侧', a), ('比对包·乙侧', b)], [a, b]
                scope = f"比对包「{packs[unit]['label']}」：{secs[a]['loc']} ↔ {secs[b]['loc']}"
            else:
                blocks, kind_secs, scope = [(None, unit)], [unit], f"小节：{secs[unit]['loc']}"
            special = s['type'] in TASK_TYPE
            task_text = s['task'] if special else TASK_FIXED['pack' if unit in packs else 'section']
            if not special and s['task'] != task_text: errs.append('task must use the fixed template wording')
            para = [f"[{(tag + '｜') if tag else ''}{rep.label(secs[sid])}] {norm(sec_text[sid])}" for tag, sid in blocks]
            # ---- 条文：按“章节 / 比对包 → 条文”对应表选取 ----
            mapped = []
            for sid in kind_secs:
                for c in cmap[secs[sid]['kind']]:
                    if c not in mapped: mapped.append(c)
            if unit in packs and ('pack:' + packs[unit]['label']) in cmap: mapped = list(cmap['pack:' + packs[unit]['label']])
            if s.get('mapped_override'): mapped = list(s['mapped_override'])                # 合成：条文全不适用
            ctext = lambda c: s.get('clause_override', {}).get(c, CLAUSES[c]['text'])      # 合成：条文改写
            if P.get('review_date'):
                mapped = [c for c in mapped if CLAUSES[c]['effective_from'] <= P['review_date'] and not CLAUSES[c].get('replaced_by')]
            for c in s.get('clauses', []):
                if c not in mapped: errs.append(f'clause {c} not in 对应表 for {unit}')
            if not (3 <= len(mapped) <= 8): errs.append(f'mapped clauses {len(mapped)} not in 3..8')
            # ---- 审核重点：按“章节 / 比对包 → 审核重点”对应表选取；要点用到的规则必须在其中 ----
            focus = focus_for(P['ptype'], [secs[x]['kind'] for x in kind_secs], packs[unit]['label'] if unit in packs else None)
            if not (1 <= len(focus) <= FOCUS_MAX): errs.append(f'focus rules {len(focus)} not in 1..{FOCUS_MAX}')
            for r in focus:
                if r not in RULES or not RULES[r].get('tag'): errs.append(f'focus rule {r} missing or has no tag')
            for p_ in s.get('points', []) or [s]:
                for r in p_.get('rules', []):
                    if r not in focus: errs.append(f"rule {r} not in 审核重点 for {unit}（{p_['id']}）")
            task_card = []
            for nm in s.get('card', []):
                if nm not in card_by: errs.append(f'unknown card field {nm}')
                else: task_card.append(card_by[nm])
            card_text = '\n'.join(f"- {c['name']}：{c['value']}（{c['loc']}）“{c['quote']}”" for c in task_card) or '（本任务无相关字段）'
            user = '\n\n'.join([f"【项目信息】\n项目：{P['name']}；报告类型：完整报告；分析金额：{P['amount']}；预算主管部门：{P['agency']}；评审时点：待填",
                                '【报告段落】\n' + '\n'.join(para), '【事实卡】\n' + card_text,
                                '【条文】\n' + '\n'.join(cline(dict(CLAUSES[c], text=ctext(c))) for c in mapped if c in CLAUSES),
                                focus_line(focus), '【任务】' + task_text])
            hay = squash(user)
            # ---- 可达性：证据须在 小节/比对包 + 事实卡 + 条文 中 ----
            universe = squash(' '.join(sec_text[x] for x in kind_secs) + ' ' + ' '.join(c['quote'] for c in task_card) + ' ' + ' '.join(ctext(c) for c in mapped if c in CLAUSES))
            reach, unreach = [], []
            for ev in s.get('evidence', []):
                (reach if squash(ev) in universe else unreach).append(ev)
                if squash(ev) not in squash(whole) and squash(ev) not in squash(' '.join(c['text'] for c in CLAUSES.values())):
                    errs.append(f'evidence not in report: {ev[:30]}')
            computed = ('full' if not unreach else ('partial' if reach else 'hint')) if s.get('evidence') else s.get('target', 'full')
            if s['target'] in ('full', 'partial', 'hint') and computed != s['target']:
                errs.append(f"reachability: declared {s['target']} but computed {computed}; unreachable={[u[:20] for u in unreach]}")
            # ---- 结构化输出 ----
            ttype = TASK_TYPE.get(s['type']) or ('比对包' if unit in packs else '小节审核')
            def ev_obj(q):
                sid = next((x for x in kind_secs if squash(q) in squash(sec_text[x])), None)
                if sid:
                    loc = rep.label(secs[sid])
                    if hasattr(rep, 'pages'):
                        pgs = [c_[0] for c_ in secs[sid]['chunks']] if secs[sid].get('chunks') else secs[sid]['pages']
                        hit = [p_ for p_ in pgs if squash(q) in squash(rep.pages[p_]['text'])]
                        if hit: loc = f"第{rep.pages[hit[0]]['printed']}页 {secs[sid]['loc']}"
                    return dict(source='报告', loc=loc, quote=q)
                c = next((c for c in task_card if squash(q) in squash(c['quote'])), None)
                return dict(source='事实卡', loc=c['loc'], quote=q) if c else None
            cited = set(ID_RE.findall(s['think']))
            text_sources, model_items, verbatim_items = [], [], []
            if special:
                obj, e2 = special_output(s, ttype); errs += e2
                if s['type'] == '漏项清单': model_items.append(s['answer_raw'])
            else:
                findings = []
                for p in s['points']:
                    problem, suggestion, edits = point_text(p, errs)
                    verdict = '提示核实' if p['target'] == 'hint' else ('证据不足' if p['type'] == '证据不足' else ('无问题' if p['type'] == '无问题' else '问题'))
                    cids = list(p['clause_ids']) if p.get('clause_ids') is not None else \
                        [c for c in (p.get('clauses') or ([] if s.get('merged') else sorted(cited))) if c in cited]
                    exp = '依据：评审经验' in problem + suggestion
                    findings.append(dict(issue_type=p['label'], rule_id=(p.get('rules') or [None])[0], verdict=verdict,
                                         evidence=[e for e in (ev_obj(q) for q in p.get('evidence', [])) if e], clause_ids=cids,
                                         basis_type=(('政策+评审经验' if cids else '评审经验') if exp else ('政策' if cids else '评审经验')),
                                         problem=problem, suggestion=suggestion, part=p['part']))
                    if p['text_source'] == '模型撰写':
                        text_sources.append(dict(source='模型撰写', reason=p['reason'])); model_items.append(problem + suggestion)
                    else:
                        text_sources.append(dict(source='专家原话（最小改动）' if edits else '专家原话', edits=edits, note=p.get('note')))
                        verbatim_items.append(problem + suggestion)
                    ref = p.get('expert_text') or p.get('expert_text_ref')
                    if ref and norm(ref) not in review: errs.append(f"{p['id']}: expert_text not verbatim in review")
                    if p.get('source_kind', 'expert') == 'expert' and not ref: errs.append(f"{p['id']}: missing expert_text")
                    for r in p.get('rules', []):
                        if r not in RULES: errs.append(f'unknown rule {r}')
                obj = dict(task=ttype, findings=findings)
            rendered = RENDER['render'](obj)
            # ---- 引文核验 ----
            for where, txt in (('think', s['think']), ('answer', rendered)):
                for q in QUOTE.findall(txt):
                    if not all(squash(x) in hay for x in re.split(r'…+', q) if x.strip()): errs.append(f'{where}: quote not in input: 「{q[:36]}」')
            # ---- 写作规范：只约束模型撰写的意见 ----
            if s['type'] != '事实卡抽取' and model_items:
                ans = ''.join(model_items)
                for it in model_items:
                    if len(it) > STYLE['max_chars']: errs.append(f"style: item {len(it)} chars > {STYLE['max_chars']}")
                    if len(QUOTE.findall(it)) > STYLE['max_quotes']: errs.append('style: item quotes report text too often')
                for w_ in STYLE['banned']:
                    if w_ in ans: errs.append(f'style: banned word {w_}')
                if ID_RE.search(ans): errs.append('style: clause id in opinion (条文编号只能出现在 think 中)')
                if any(len(q) > STYLE['max_quote_len'] for q in QUOTE.findall(ans)): errs.append('style: long quote of report text')
                sm = difflib.SequenceMatcher(None, squash(ans), hay, autojunk=False).find_longest_match(0, len(squash(ans)), 0, len(hay))
                if sm.size > STYLE['max_copy']: errs.append(f"style: copies {sm.size} chars verbatim from input")
            if SRC_EXPERT.search(s['think']): errs.append('style: think refers to 专家 as the source of the opinion')
            for e_ in set(ENT_REF.findall(s['think'])):   # 推理中引用的表号、附件号、页码必须出现在输入或意见中
                if squash(e_) not in hay and squash(e_) not in squash(rendered): errs.append(f'think cites {e_} not in input or opinion')
            if model_items and SRC_EXPERT.search(''.join(model_items)): errs.append('style: opinion refers to 专家')
            # ---- 数字与算式 ----
            rules_text = ' '.join(json.dumps(RULES.get(r, {}), ensure_ascii=False) for r in s.get('rules', []))
            e_ar, derived = check_arith(s['think'], user + ' ' + rules_text)
            errs += [f'think {e}' for e in e_ar]
            flat = re.sub(r'[\s,]', '', user)
            for n in re.findall(NUM, ''.join(model_items) + ''.join(REF_IN_EXPERT.sub('', x) for x in verbatim_items)):
                q = n.replace(',', '')
                if len(q.replace('.', '')) >= 2 and q not in flat and q not in derived:
                    errs.append(f'opinion number {n} not in input and not verified in think')
            for ph in s.get('must_quote', []):
                if not any(squash(ph) in squash(q) for q in QUOTE.findall(s['think'])): errs.append(f'synthetic: rewritten clause not quoted in think: {ph}')
            for i in set(ID_RE.findall(s['think'] + rendered)):
                if i not in mapped: errs.append(f'cited {i} not in input')
            for r in s.get('rules', []):
                if r not in RULES: errs.append(f'unknown rule {r}')
            js = json.dumps(obj, ensure_ascii=False)
            system = system_for(ttype)
            asst_think = f"<think>\n{tr(s['think'])}\n</think>\n{js}"
            if s['type'] not in ('事实卡抽取', '漏项清单') and len(s['think']) < THINK_MIN: errs.append(f"think too short: {len(s['think'])} chars (min {THINK_MIN})")
            n = len(system) + len(user) + len(asst_think)
            if n > MAX_CHARS: errs.append(f'too long: {n} chars (cap {MAX_CHARS})')
            pts = s.get('points', [])
            exp_texts = [x for x in ((p.get('expert_text') or p.get('expert_text_ref')) for p in pts) if x]
            rec = dict(id=s['id'], meta=dict(
                project=P['name'], project_id=pid, group=P.get('group'), report_version=P['report_version'], review_date=P.get('review_date') or '待填',
                sample_type=('多问题' if s.get('merged') else s['type']), task_type=ttype, input_scope=scope,
                reachability=('全部可达' if computed == 'full' else ('部分可达' if computed == 'partial' else '不可达')) + ('；不可达证据：' + '；'.join(u[:24] + '…' for u in unreach) if unreach else ''),
                target_type=computed, evidence=s.get('evidence', []), unreachable_evidence=unreach, evidence_count=len(s.get('evidence', [])), unreachable_count=len(unreach),
                rule_ids=s.get('rules', []), focus_rule_ids=focus, clause_ids=s.get('clauses', []), mapped_clause_ids=mapped,
                expert_text=('\n'.join(exp_texts) or None), text_sources=text_sources, opinion_text=tr(rendered), opinion_tags=RENDER['render_tags'](obj), basis=RENDER['render_basis'](obj, CLAUSES),
                source_kind=s.get('source_kind', 'expert'), members=[p['id'] for p in pts] if s.get('merged') else None,
                member_types=[p['type'] for p in pts] if s.get('merged') else None, member_source_kinds=[p.get('source_kind', 'expert') for p in pts] if s.get('merged') else None,
                synthetic=str(s.get('source_kind', '')).startswith('synthetic'), base_sample=s.get('base_sample'),
                reasoning_author=s.get('author'), status=s.get('status') or '待专家确认', notes=s.get('notes'), history=s.get('history'),
                annotation=P.get('annotation'), approx_chars=n),
                system=system, messages=[dict(role='user', content=user), dict(role='assistant', content=asst_think)],
                _answer_only=f"<think>\n\n</think>\n\n{js}")
            if errs: rec['errors'] = errs; bad.append(rec)
            else: ok.append(rec); stats[(rec['meta']['sample_type'], computed)] += 1
    cand = [r for r in ok if str(r['meta']['status']).startswith('候选')]
    ok = [r for r in ok if not str(r['meta']['status']).startswith('候选')]
    dump = lambda rs, plain=False: ''.join(json.dumps(dict({k: v for k, v in r.items() if not k.startswith('_')},
                                                           **({'messages': [r['messages'][0], dict(role='assistant', content=r['_answer_only'])]} if plain else {})), ensure_ascii=False) + '\n' for r in rs)
    for name, rs, plain in (('samples.jsonl', ok, False), ('samples_answer_only.jsonl', ok, True), ('candidates_no_issue.jsonl', cand, False), ('rejected.jsonl', bad, False)):
        open(os.path.join(OUT, name), 'w', encoding='utf-8').write(dump(rs, plain))
    json.dump([dict(system=r['system'], conversations=[{'from': 'human', 'value': r['messages'][0]['content']}, {'from': 'gpt', 'value': r['messages'][1]['content']}]) for r in ok],
              open(os.path.join(OUT, 'train_sharegpt.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, 'preview.md'), 'w', encoding='utf-8') as fo:
        fo.write('# 样本预览\n\n')
        for r in ok + cand:
            m = r['meta']
            fo.write(f"## {r['id']} · {m['sample_type']} · {m['target_type']}\n- 输入范围：{m['input_scope']}\n- 可达性：{m['reachability']}\n- 意见来源：{[t['source'] for t in m['text_sources']]}\n")
            if m['expert_text']: fo.write(f"- 专家原意见：{m['expert_text']}\n")
            fo.write('\n**输入**\n\n```\n' + r['messages'][0]['content'] + '\n```\n\n**输出**\n\n```\n' + r['messages'][1]['content'] + '\n```\n\n**组装后的意见**\n\n' + m['opinion_text'] + '\n\n---\n\n')
    ch = sorted(r['meta']['approx_chars'] for r in ok) or [0]
    per_p = collections.Counter(r['meta']['project_id'] for r in ok)
    src = collections.Counter(t['source'] for r in ok + cand for t in r['meta']['text_sources'])
    rep_txt = [f'accepted {len(ok)} (+{len(cand)} candidates)  rejected {len(bad)}',
               '类型×可达性: ' + str({f'{a}/{b}': n for (a, b), n in sorted(stats.items())}),
               '意见来源: ' + str(dict(src)),
               f'长度（字符）P50={ch[len(ch)//2]}  P95={ch[min(len(ch)-1, int(len(ch)*0.95))]}  最大={ch[-1]}',
               '每项目样本数（上限 30）: ' + str(dict(per_p)) + ('  超限!' if any(v > 30 for v in per_p.values()) else ''),
               '按任务类型: ' + str(dict(collections.Counter(r['meta']['task_type'] for r in ok)))]
    if not all(PROJ[p].get('review_date') for p in per_p): rep_txt.append('注意：评审时点未填，条文未按时点过滤')
    rep_txt += ['\nREJECTED'] + [f"{r['id']}: {r.get('errors')}" for r in bad]
    open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8').write('\n'.join(rep_txt)); print('\n'.join(rep_txt))


main()
