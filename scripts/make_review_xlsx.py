"""专家确认表。Usage: python3 -I make_review_xlsx.py <data_dir> [轮次名] [规则编号...]
读 data/out（普通样本）和 data/out_rules/<规则>（规则专项样本、规则卡待定口径），写 data/out/专家确认表_<轮次名>.xlsx。"""
import sys, os, json, re
import yaml
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
D = sys.argv[1]
PENDING = '--pending' in sys.argv                    # 只出待确认的要点（模型撰写、状态为待专家确认），不含已确认内容和规则表
if PENDING: sys.argv.remove('--pending')
rows = [json.loads(l) for l in open(os.path.join(D, 'out/samples.jsonl'), encoding='utf-8')]
rows += [json.loads(l) for l in open(os.path.join(D, 'out/candidates_no_issue.jsonl'), encoding='utf-8')]
CL = {c['clause_id']: c for c in json.load(open(os.path.join(D, 'clauses/clauses.json'), encoding='utf-8'))}
FOCUS_RE = re.compile(r'【审核重点】(.*)')
ID_RE = re.compile(r'\b(P\d+(?:-[A-Za-z0-9]+)+)\b')
cite = lambda i: f"{CL[i]['doc_no']} {CL[i]['location']}"
human = lambda t: ID_RE.sub(lambda m: cite(m.group(1)) if m.group(1) in CL else m.group(0), t)
body = lambda a: re.sub(r'<think>.*?</think>\s*', '', a, flags=re.S).strip()
if PENDING:
    from openpyxl import Workbook as _WB
    ROUND = sys.argv[2] if len(sys.argv) > 2 else '待确认'
    wb = _WB(); ws = wb.active; ws.title = '待确认要点'
    heads = ['序号', '要点编号', '项目', '所在小节', '待确认的意见', '依据（报告与事实卡原文，已核对）', '推理中对应的判断', '专家判断', '修改后的意见', '备注']
    widths = [6, 34, 14, 30, 60, 60, 70, 14, 50, 30]
    thin = Side(style='thin', color='BBBBBB'); yellow = PatternFill('solid', fgColor='FFF2CC')
    for j, (h, w) in enumerate(zip(heads, widths), 1):
        c = ws.cell(row=1, column=j, value=h); c.font = Font(bold=True, color='FFFFFF'); c.fill = PatternFill('solid', fgColor='1F4E78')
        c.alignment = Alignment(wrap_text=True, vertical='center', horizontal='center'); ws.column_dimensions[c.column_letter].width = w
    n = 0
    for r in rows:
        m = r['meta']
        if '待专家确认' not in str(m.get('status')): continue
        think, js = r['messages'][1]['content'].split('</think>\n', 1)
        fs = json.loads(js).get('findings', [])
        marked = any('待专家确认' in (ts.get('reason') or '') for ts in m['text_sources'])   # 要点级标记优先：只出标了待确认的要点
        for f, ts in zip(fs, m['text_sources']):
            if ts['source'] != '模型撰写': continue
            if marked and '待专家确认' not in (ts.get('reason') or ''): continue
            seg = next((ln for ln in think.split('\n') if f['rule_id'] and f['rule_id'] in ln), '')
            n += 1
            vals = [n, r['id'], m['project'][:14], m['input_scope'].replace('小节：', ''), f['problem'] + f['suggestion'],
                    '\n'.join(f"· [{e['source']}｜{e['loc']}] {e['quote']}" for e in f['evidence']), seg, None, None, ts.get('reason') or '']
            for j, v in enumerate(vals, 1):
                c = ws.cell(row=n + 1, column=j, value=v); c.alignment = Alignment(wrap_text=True, vertical='top'); c.border = Border(top=thin, bottom=thin, left=thin, right=thin)
                if j in (8, 9): c.fill = yellow
            ws.row_dimensions[n + 1].height = 150
    dv = DataValidation(type='list', formula1='"采纳,修改后采纳,驳回"', allow_blank=True); ws.add_data_validation(dv); dv.add(f'H2:H{n + 1}')
    ws.freeze_panes = 'C2'
    out = os.path.join(D, f'out/专家确认表_{ROUND}.xlsx'); wb.save(out); print(n, 'pending points ->', out); sys.exit(0)
KIND = {'synthetic_clause_rewrite': '合成（条文改写）', 'synthetic_clause_irrelevant': '合成（条文全不适用）', 'expert': '来自专家原意见', 'model_supplement': '模型补充发现（非专家原意见）', 'candidate_no_issue': '候选“无问题”（专家未评论）', 'checklist': '模板漏项清单', 'factcard': '事实卡抽取样本'}
wb = Workbook(); ws0 = wb.active; ws0.title = '说明'
guide = ['专家确认表使用说明', '',
 '一、这张表是干什么的', '每行是一条训练样本：输入为报告的一个小节（或两处需要比对的小节）、事实卡和政策条文，输出为推理过程和评审意见。请专家判断评审意见和推理是否准确、是否符合评审口径。', '',
 '二、意见从哪里来（见“意见来源及改动”列）',
 '· 专家原话：直接取自原评审意见，只按要点拆分；',
 '· 专家原话（最小改动）：拆分带出的序号、部分标题、笔误或无法核验的数字做了改动，逐处列出改动和原因；',
 '· 模型撰写：只用于提示核实、模型补充发现、证据不足和条文改写样本，请重点看这几条。', '推理过程均由模型撰写，请看它能否从输入推导出结论。', '',
 '三、各列怎么看',
 '· 输入范围：模型在这条样本里看到的内容，范围之外的报告原文模型看不到；',
 '· 可达性：意见所需的依据是否都在输入范围内（含事实卡）；不可达的要点输出为提示核实，请看核实位置是否正确；',
 '· 审核重点：本小节输入中带的检查方面，按章节类型自动生成，不代表每项都有问题；如认为某类章节应增减检查方面，请在备注中写明；',
 '· 证据摘录：意见对应的报告原文，已由程序核对；',
 '· 标签（所属部分）：每段意见所属的部分，作辅助展示，不写进意见正文。', '',
 '四、需要你做什么（只填最后三列，黄色）',
 '1. 在“专家判断”下拉框选：采纳 / 修改后采纳 / 驳回；', '2. 修改后采纳的，在“修改后的意见”里改写；', '3. “候选无问题”的行不确定请选驳回。', '',
 '五、确认后：采纳和修改后采纳的行进入训练集，驳回的行作为反例保存。', '',
 '六、规则专项（每条规则两张表，建议先填“口径确认”，再看“逐项判断”）',
 '· “<规则>口径确认”：规则卡中需要专家定的口径。每行列出草稿的处理方式和受影响的指标；请选“同意草稿”或“改为其他口径”，改的请写明口径。口径定了，受影响的逐项判断统一修改，不必逐条改；',
 '· “<规则>逐项判断”：模型按规则卡对每个绩效指标的判断（驱动成本 / 无对应成本项 / 不适用）及每个项目的汇总。请选“同意”或“改判”，改判的选改判结果并写理由；“涉及口径”列标明该行受哪条待定口径影响；',
 '· 标“合成”的行是把报告中某个指标改写后生成的对照样本，请看判断是否随改写正确变化；',
 '· 规则卡确认前，这些样本不进入训练。']
for i, t in enumerate(guide, 1):
    c = ws0.cell(row=i, column=1, value=t); c.alignment = Alignment(wrap_text=True, vertical='top')
ws0['A1'].font = Font(bold=True, size=14); ws0.column_dimensions['A'].width = 110
ws = wb.create_sheet('逐条确认')
heads = ['序号', '样本编号', '项目', '样本类型', '来源', '专家原意见', '输入范围', '审核重点', '可达性', '证据摘录（已核对原文）', '评审意见（组装后）', '标签（所属部分）', '意见来源及改动', '引用的政策条文（原文）', '专家判断', '修改后的意见', '备注']
widths = [6, 30, 20, 11, 16, 44, 34, 40, 22, 52, 70, 18, 60, 50, 14, 50, 28]
thin = Side(style='thin', color='BBBBBB')
for j, (h, w) in enumerate(zip(heads, widths), 1):
    c = ws.cell(row=1, column=j, value=h); c.font = Font(bold=True, color='FFFFFF'); c.fill = PatternFill('solid', fgColor='1F4E78')
    c.alignment = Alignment(wrap_text=True, vertical='center', horizontal='center'); ws.column_dimensions[c.column_letter].width = w
yellow = PatternFill('solid', fgColor='FFF2CC')
for i, r in enumerate(rows, 1):
    m = r['meta']
    ev = '\n'.join(f'· {e}' for e in m.get('evidence', [])) or '（无）'
    clauses = '\n\n'.join(f"【{cite(c)}】\n{CL[c]['text']}" for c in m['clause_ids']) or '（本条未引用政策条文）'
    vals = [i, r['id'], m['project'][:14], m['sample_type'], KIND.get(m['source_kind'], m['source_kind']), m['expert_text'] or '（原评审意见未提及）',
            m['input_scope'], (FOCUS_RE.search(r['messages'][0]['content']).group(1).replace('；', '\n') if FOCUS_RE.search(r['messages'][0]['content']) else ''), m['reachability'], ev, (m.get('opinion_text') or human(body(r['messages'][1]['content']))), '\n'.join(m.get('opinion_tags') or []), '\n'.join(f"要点{k+1}：{ts['source']}" + ('；' + '；'.join(f"“{e['old']}”→“{e['new']}”（{e['reason']}）" for e in ts.get('edits', [])) if ts.get('edits') else '') + (f"（{ts['reason']}）" if ts.get('reason') else '') + (f"；注：{ts['note']}" if ts.get('note') else '') for k, ts in enumerate(m.get('text_sources') or []) if ts) or '—', clauses, None, None, m.get('notes') or '']
    for j, v in enumerate(vals, 1):
        c = ws.cell(row=i + 1, column=j, value=v); c.alignment = Alignment(wrap_text=True, vertical='top'); c.border = Border(top=thin, bottom=thin, left=thin, right=thin)
        if j >= 15: c.fill = yellow
    ws.row_dimensions[i + 1].height = 240
dv = DataValidation(type='list', formula1='"采纳,修改后采纳,驳回"', allow_blank=True); ws.add_data_validation(dv); dv.add(f'O2:O{len(rows) + 1}')
ws.freeze_panes = 'C2'
ROUND = sys.argv[2] if len(sys.argv) > 2 else '待确认'


def header(ws, heads, widths):
    for j, (h, w) in enumerate(zip(heads, widths), 1):
        c = ws.cell(row=1, column=j, value=h); c.font = Font(bold=True, color='FFFFFF'); c.fill = PatternFill('solid', fgColor='1F4E78')
        c.alignment = Alignment(wrap_text=True, vertical='center', horizontal='center'); ws.column_dimensions[c.column_letter].width = w


def put(ws, i, vals, fill_from, height):
    for j, v in enumerate(vals, 1):
        c = ws.cell(row=i + 1, column=j, value=v); c.alignment = Alignment(wrap_text=True, vertical='top'); c.border = Border(top=thin, bottom=thin, left=thin, right=thin)
        if j >= fill_from: c.fill = yellow
    ws.row_dimensions[i + 1].height = height


def hits(q, meta):
    """该口径是否涉及这条逐项判断：match 中列出的条件须全部满足。"""
    m = q.get('match', {})
    if 'category' in m and meta.get('category') not in m['category']: return False
    if 'project' in m and meta['project_id'] not in m['project']: return False
    if 'judgment' in m and meta.get('judgment') not in m['judgment']: return False
    if 'indicator_contains' in m and not any(k in (meta.get('indicator') or '') for k in m['indicator_contains']): return False
    return True


for RULE in sys.argv[3:]:
    card = yaml.safe_load(open(os.path.join(D, f'rules/cards/{RULE}.yaml'), encoding='utf-8'))
    qs = card['scope'].get('open_questions', [])
    recs = [json.loads(l) for l in open(os.path.join(D, f'out_rules/{RULE}/eval_tag.jsonl'), encoding='utf-8')]
    out_of = lambda r: json.loads(re.sub(r'(?s)^<think>.*?</think>\s*', '', r['messages'][1]['content']))
    items = [r for r in recs if r['meta']['step'] == '逐项判断']
    # 口径确认
    wq = wb.create_sheet(f'{RULE}口径确认')
    header(wq, ['编号', '待定口径', '草稿的处理方式', '受影响的逐项判断', '专家选择', '专家口径（改为其他口径时填写）'], [6, 50, 60, 70, 16, 50])
    put(wq, 1, ['规则', f"{RULE} {card['title']}：{card['caliber']}", f"适用：{card['scope']['applies']}\n不适用：{card['scope']['not_applicable']}", '（规则口径与适用范围，供参考）', None, None], 99, 110)
    for i, q in enumerate(qs, 1):
        hit = [r for r in items if hits(q, r['meta'])]
        lst = '\n'.join(f"· {r['meta']['project_id']} {r['meta']['indicator']}（{r['meta']['category']}）→ {r['meta']['judgment']}" + ('（合成）' if r['meta']['synthetic'] else '') for r in hit)
        put(wq, i + 1, [q['id'], q['question'], q['draft'], f"共 {len(hit)} 条\n{lst}" if hit else '（暂无）', q.get('decision'), None], 5, max(60, 16 * (len(hit) + 2)))   # 已确认的口径预填专家结论
    dq = DataValidation(type='list', formula1='"同意草稿,改为其他口径,需讨论"', allow_blank=True); wq.add_data_validation(dq); dq.add(f'E3:E{len(qs) + 2}')
    wq.freeze_panes = 'C2'
    # 逐项判断
    wi = wb.create_sheet(f'{RULE}逐项判断')
    header(wi, ['序号', '样本编号', '项目', '步骤', '指标', '类别', '模型判断', '影响的成本项及方向', '理由', '证据摘录（已核对原文）', '涉及口径', '来源', '专家判断', '改判为', '理由／备注'],
           [6, 26, 8, 10, 26, 12, 14, 30, 50, 50, 10, 14, 12, 16, 40])
    for i, r in enumerate(recs, 1):
        m, o = r['meta'], out_of(r)
        if m['step'] == '汇总':
            cov = '\n'.join(f"· {c['cost_item']} ← {'、'.join(c['indicators'])}" for c in o['covered']) or '（无）'
            vals = [i, r['id'], m['project_id'], '汇总', '（全部指标）', '', '汇总', f"已覆盖：\n{cov}\n未覆盖：{'；'.join(o['uncovered_cost_items']) or '（无）'}",
                    f"无对应成本项的关键指标：{'、'.join(o['unlinked_key_indicators']) or '（无）'}\n需人工核对：{'、'.join(o.get('need_manual_check', [])) or '（无）'}\n建议：{o['suggestion']}", '', '', '模型带规则卡汇总', None, None, None]
        else:
            ci = ('、'.join(o['cost_items']) + (f"（{o['direction']}）" if o.get('direction') else '')) if o['cost_items'] else '—'
            vals = [i, r['id'], m['project_id'], '逐项判断', m['indicator'], m['category'], m['judgment'], ci, o['reason'], '\n'.join(f"· {e['quote']}" for e in o['evidence']),
                    '、'.join(q['id'] for q in qs if hits(q, m)) or '—', '合成（改写成对）' if m['synthetic'] else '真实报告', None, None, None]
        put(wi, i, vals, 13, 90)
    d1 = DataValidation(type='list', formula1='"同意,改判,不确定"', allow_blank=True); wi.add_data_validation(d1); d1.add(f'M2:M{len(recs) + 1}')
    d2 = DataValidation(type='list', formula1='"驱动成本,无对应成本项,需人工核对,不适用"', allow_blank=True); wi.add_data_validation(d2); d2.add(f'N2:N{len(recs) + 1}')
    wi.freeze_panes = 'F2'
    print(RULE, f'口径 {len(qs)} 条，逐项判断与汇总 {len(recs)} 条')

out = os.path.join(D, f'out/专家确认表_{ROUND}.xlsx'); wb.save(out); print(len(rows), 'rows ->', out)
