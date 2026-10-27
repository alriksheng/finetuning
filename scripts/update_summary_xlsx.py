"""把 2026-10-26 下午的新结果追加到 微调实验汇总_2026-10-26.xlsx：分层 SFT 与 DPO 冒烟、学习曲线、诊断与判定、事实卡第 1 步；并更新「概览」和「6 实验进度」。
Usage: python3 -I update_summary_xlsx.py <汇总.xlsx> <eval_out_all 目录> <额外意见_待判定.xlsx>"""
import sys, json, collections, copy
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
X, EV, EXTRA = sys.argv[1:4]
wb = openpyxl.load_workbook(X)
HDR = wb['1 开发集·训练与检查点']['A2']; BODY = wb['1 开发集·训练与检查点']['F3']
thin = Side(style='thin', color='BBBBBB'); BORDER = Border(top=thin, bottom=thin, left=thin, right=thin)
def hdr(ws, row, vals):
    for j, v in enumerate(vals, 1):
        c = ws.cell(row, j, v); c.font = copy.copy(HDR.font); c.fill = copy.copy(HDR.fill); c.alignment = Alignment(wrap_text=True, vertical='center'); c.border = BORDER
    ws.row_dimensions[row].height = 34
def put(ws, row, vals, fmts=None, bold=False):
    for j, v in enumerate(vals, 1):
        c = ws.cell(row, j, v); c.font = Font(name='Arial', size=10, bold=bold); c.border = BORDER; c.alignment = Alignment(wrap_text=isinstance(v, str) and len(v) > 14, vertical='top')
        if fmts and j - 1 < len(fmts) and fmts[j - 1]: c.number_format = fmts[j - 1]
def note(ws, row, text, width_cols):
    c = ws.cell(row, 1, text); c.font = Font(name='Arial', size=9, color='595959'); c.alignment = Alignment(wrap_text=True, vertical='top')
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=width_cols); ws.row_dimensions[row].height = 15 * (1 + len(text) // 70)
def sc(name):
    try: return json.load(open(f'{EV}/score_{name}.json'))
    except Exception: return None
P, F1, F2 = '0.0%', '0.00', '0.0'
# ---------------- 8 分层 SFT 与 DPO 冒烟 ----------------
ws = wb.create_sheet('8 分层SFT与DPO冒烟（开发集）')
note(ws, 1, '开发集 8 个项目、46 条样本、106 条标准意见；L3-07 开发集 73 条（逐项 64、汇总 8）。分层 SFT = 难例放两份 + 66 条模型采样目标 + 步数略增（训练行数 +16%、步数 +10%），与训练 A（e1~e3）同配置从基座重训；DPO 冒烟 = 在 e3 上用 50 对偏好对续训 1 轮（lr 2e-5）。单样本差异 1~3 个百分点按噪声处理（开发集 106 条意见，标准误约 4.6 个百分点）。', 14)
cols = ['模型', '训练', '可解析率', '引文逐字率', '规则命中', '证据命中', '综合命中', '宽松综合命中', '意见数/样本', '额外意见/样本', 'L3-07 逐项准确率', 'L3-07 汇总F1', '综合命中相对 e3（百分点）', '结论']
hdr(ws, 2, cols)
rows = [('e1', '训练 A 第 1 轮'), ('e2', '训练 A 第 2 轮'), ('e3', '训练 A 第 3 轮（基准）'), ('t1', '分层 SFT 第 1 轮'), ('t2', '分层 SFT 第 2 轮'), ('t3', '分层 SFT 第 3 轮'), ('sm', 'DPO 冒烟（e3 + 50 对 × 1 轮）')]
concl = {'t3': '与 e3 差 -0.9 个百分点，按噪声处理；难例放两份加 66 条采样样本无可见提升', 'sm': '不通过：意见数 2.31→1.34，综合命中 -14 个点，模型变得少说话', 't1': '额外意见偏多（1.87）', 't2': '额外意见偏多（1.68），第 3 轮回落'}
r0 = 3
for i, (m, desc) in enumerate(rows):
    a = sc(f'{m}_audit_dev'); l = sc(f'{m}_rule_L3-07_dev_tag') or {}
    r = r0 + i
    put(ws, r, [m, desc, a['parse_rate'], a['quote_verbatim_rate'], a['rule_hit'], a['evidence_hit'], a['covered'], a.get('covered_loose'), a['pred_per_sample'], a['extra_per_sample'],
                l.get('judgment_accuracy', '—'), l.get('summary_f1', '—'), f'=(G{r}-$G$5)*100', concl.get(m, '')],
        [None, None, P, P, P, P, P, P, F2, F2, P, P, F2, None])
note(ws, r0 + len(rows) + 1, 'DPO 冒烟（sm）没有评测 L3-07。e1、e2、e3 没有“宽松综合命中”（该指标在之后加入）。', 14)
r = r0 + len(rows) + 3
hdr(ws, r, ['DPO 冒烟·无问题集', '样本数', '可解析率', '沉默率 silence_rate', '意见数/样本', '', '', '', '', '', '', '', '', '说明'])
n1 = json.load(open(f'{EV}/neg_sm_audit_dev_neg.json')); n2 = json.load(open(f'{EV}/neg_sm_audit_dev_negp.json'))
put(ws, r + 1, ['反事实无问题集（neg）', n1['samples'], n1['parse_rate'], n1['silence_rate'], n1['findings_per_sample']] + [''] * 8 + ['沉默率 0：没有一条无问题样本被判为无问题；e3 没有这项基线'], [None, None, P, P, F2])
hdr(ws, r + 3, ['DPO 冒烟·局部修正集', '样本数', '可解析率', '固定意见重复率', '', '', '', '', '', '', '', '', '', '说明'])
put(ws, r + 4, ['局部修正集（negp）', n2['samples'], n2['parse_rate'], n2['repeat_fixed_finding_rate']] + [''] * 9 + ['已被修正的意见不再重复；e3 没有这项基线'], [None, None, P, P])
for j, w in enumerate([22, 26, 10, 10, 10, 10, 10, 11, 10, 11, 12, 11, 14, 54], 1): ws.column_dimensions[openpyxl.utils.get_column_letter(j)].width = w
ws.freeze_panes = 'C3'
# ---------------- 9 学习曲线 ----------------
ws = wb.create_sheet('9 学习曲线（开发集）')
note(ws, 1, '同配置（lr 1e-4、3 轮、种子 42）只改训练项目数：25 个 / 50 个 / 99 个。开发集 46 条样本。c50e3 开思考时有 35% 的样本思考不收敛、没有写出 JSON（可解析率 65%），不能直接和其他行比较。', 10)
hdr(ws, 2, ['模型', '训练项目数', '轮数', '可解析率', '引文逐字率', '规则命中', '证据命中', '综合命中', '意见数/样本', '额外意见/样本'])
for i, (m, np_, ep) in enumerate([('c25e2', 25, 2), ('c25e3', 25, 3), ('c50e2', 50, 2), ('c50e3', 50, 3), ('e2', 99, 2), ('e3', 99, 3)]):
    a = sc(f'{m}_audit_dev'); put(ws, 3 + i, [m, np_, ep, a['parse_rate'], a['quote_verbatim_rate'], a['rule_hit'], a['evidence_hit'], a['covered'], a['pred_per_sample'], a['extra_per_sample']], [None, None, None, P, P, P, P, P, F2, F2])
note(ws, 10, '在 30 条所有模型都能解析的子集上，50 个项目到 99 个项目综合命中提高 10~15 个百分点（此前汇报）；本表为全开发集结果，c50e3 不可解析的样本按未命中计。', 10)
for j, w in enumerate([12, 12, 8, 10, 10, 10, 10, 10, 12, 12], 1): ws.column_dimensions[openpyxl.utils.get_column_letter(j)].width = w
# ---------------- 10 诊断与判定 ----------------
ws = wb.create_sheet('10 诊断与判定')
note(ws, 1, '专家对模型输出的人工判定，以及用盲审试点检验“老师能不能推出专家意见”。判定来源：额外意见_待判定.xlsx（开发集 e3 单次采样，没有对上专家意见的 68 条，已判 67 条）、诊断1_规则对引文不对_待判定.xlsx（36 条，已判 8 条）。', 8)
hdr(ws, 2, ['额外意见判定（总计）', '条数', '占比'])
ex = openpyxl.load_workbook(EXTRA, data_only=True).active; rows_ = [[c.value for c in r] for r in ex.iter_rows(min_row=3)]
J = [r for r in rows_ if r[8]]; cnt = collections.Counter(r[8] for r in J)
for i, k in enumerate(['成立', '成立但次要', '不成立']):
    put(ws, 3 + i, [k, cnt[k], f'=B{3 + i}/$B$6'], [None, None, P])
put(ws, 6, ['合计（已判）', f'=SUM(B3:B5)', ''], bold=True)
hdr(ws, 8, ['按规则（模型提出的规则）', '成立', '成立但次要', '不成立', '合计', '成立占比'])
byr = collections.defaultdict(collections.Counter)
for r in J: byr[r[4]][r[8]] += 1
rr = 9
for k, v in sorted(byr.items(), key=lambda x: -sum(x[1].values())):
    put(ws, rr, [k, v['成立'], v['成立但次要'], v['不成立'], f'=SUM(B{rr}:D{rr})', f'=B{rr}/E{rr}'], [None, None, None, None, None, P]); rr += 1
put(ws, rr, ['合计', f'=SUM(B9:B{rr - 1})', f'=SUM(C9:C{rr - 1})', f'=SUM(D9:D{rr - 1})', f'=SUM(E9:E{rr - 1})', f'=B{rr}/E{rr}'], [None, None, None, None, None, P], bold=True)
rr += 2
hdr(ws, rr, ['专家意见 vs 额外意见的写法', '专家意见', '额外意见', '说明']); 
for i, (k, a, b, d) in enumerate([('平均字数（问题+建议）', 77.5, 37.5, '开发集专家意见 vs e3 额外意见；训练集专家意见平均 67.9 字'),
                                  ('problem 字段为空的比例', 0.755, 1.0, '额外意见全部只写建议，专家意见约 1/4 有问题描述'), ('平均引文条数', 2.33, 2.5, '')]):
    put(ws, rr + 1 + i, [k, a, b, d], [None, F2 if i != 1 else P, F2 if i != 1 else P, None])
rr += 6
hdr(ws, rr, ['诊断 1（规则对但综合命中没中）', '条数', '说明'])
put(ws, rr + 1, ['已判定', 8, '36 条中已判 8 条'])
put(ws, rr + 2, ['C 问题点本身不同', 8, '8 条全部是 C；A 引错位置、B 另一处能支撑、D 其他均为 0'])
put(ws, rr + 3, ['含义', '', '放宽引文匹配救不回这部分，差异在“选哪个问题点”，不是评测口径'])
rr += 5
hdr(ws, rr, ['T2 盲审试点（40 条训练样本，只读输入不看答案）', '数值', '说明'])
for i, (k, v, f_, d) in enumerate([('样本 / 专家意见 / 盲审意见', '40 / 90 / 113', None, '34 个项目；盲审 2.8 条每样本，专家 2.25 条'), ('综合命中（原口径）', 24 / 90, P, '未达试点线 40%'), ('宽松口径命中', 0.40, P, '刚好达线'),
                                   ('引文对上、规则不同', 20 / 90, P, '“绩效指标聚焦”与“基线值来源”互判最多'), ('仅规则相同（位置不同）', 20 / 90, P, ''), ('规则相同、引文部分重合', 12 / 90, P, ''), ('完全漏报', 14 / 90, P, ''),
                                   ('盲审多出（未对上专家意见）', '90 条（2.25 条每样本）', None, '')]):
    put(ws, rr + 1 + i, [k, v, d], [None, f_, None])
for j, w in enumerate([40, 14, 14, 14, 10, 12], 1): ws.column_dimensions[openpyxl.utils.get_column_letter(j)].width = w
ws.column_dimensions['C'].width = 40
# ---------------- 11 事实卡第1步 ----------------
ws = wb.create_sheet('11 事实卡第1步')
note(ws, 1, '项目级事实卡 L0（报告结构索引）+ L1（相关摘要原文节选），纯程序生成，见 项目级事实卡设计.md 第 11 节、scripts/fact_card.py。', 5)
hdr(ws, 2, ['指标', '已标注小节（643）', '候选小节（1153）', '说明'])
for i, (k, a, b, f_, d) in enumerate([('卡字数 均值', 423, 666, '0', ''), ('卡字数 中位数', 223, 683, '0', ''), ('卡字数 P95', 1063, 1096, '0', ''), ('卡字数 最大', 1236, 1175, '0', ''),
                                      ('报告没有摘要（只有结构索引）的比例', 0.44, 0.15, P, '这部分必须靠关键字段（L2）补'), ('预计 token 增量（均值）', 275, 434, '0', '按 0.65 token/字；现有训练输入平均约 2070 token'),
                                      ('L1 与当前小节重叠的卡数', 0, 0, '0', '1796 张卡检查')]):
    put(ws, 3 + i, [k, a, b, d], [None, f_, f_, None])
for j, w in enumerate([36, 18, 18, 46], 1): ws.column_dimensions[openpyxl.utils.get_column_letter(j)].width = w
# ---------------- 概览 / 实验进度 ----------------
ov = wb['概览']
ov['A2'] = '生成日期：2026-10-26（更新：加入分层 SFT、DPO 冒烟、学习曲线、额外意见判定、T2 盲审试点、事实卡第 1 步）。数据来自云上评测结果（eval_out）。'
ov['A20'] = '6. 学习曲线：25 / 50 / 99 个训练项目，综合命中随项目数上升（见「9 学习曲线」）；数据量仍是最有效的变量。'
base = 21
for i, t in enumerate(['7. 分层 SFT（难例放两份 + 66 条采样样本）：t3 综合命中 34.9%，e3 35.8%，差异在噪声内；L3-07 逐项 78.1% 对 73.4%（训练数据相同，视为波动）。不采用。（见「8」）',
                       '8. DPO 冒烟（50 对）：综合命中 21.7%，意见数 2.31→1.34，模型变得少说话；不通过，暂不做正式 DPO。',
                       '9. 额外意见判定（开发集 67 条）：成立 13（19%）、成立但次要 21（31%）、不成立 33（49%）；R-BASIC-CONTENT 12 条全不成立。模型额外意见平均 37 字，专家意见 78 字，且 problem 字段 100% 为空。（见「10」）',
                       '10. 诊断 1：已判 8 条全是“问题点本身不同”；T2 盲审试点综合命中 26.7%，未达 40% 线，T 组构建暂停。',
                       '11. 根因判断：训练样本 90% 没有事实卡、全部为“全部可达”、无“依据在别处”机制；开始做项目级事实卡（第 1 步已完成，见「11」）。']):
    c = ov.cell(base + i, 1, t); c.font = copy.copy(ov['A19'].font); c.alignment = copy.copy(ov['A19'].alignment)
pg = wb['6 实验进度']
for r in range(2, pg.max_row + 1):
    k = pg.cell(r, 1).value or ''
    if k.startswith('学习曲线'): pg.cell(r, 2, '完成'); pg.cell(r, 3, '综合命中 c25e3 17.0%、c50e3 18.9%（可解析 65%）、e3(99 个项目) 35.8%'); pg.cell(r, 4, '见「9 学习曲线」；项目数是最有效的变量')
    if k.startswith('候选池'): pg.cell(r, 2, '完成'); pg.cell(r, 3, '已采样 pool_a/pool_b；用于 DPO 偏好对与拒绝采样'); pg.cell(r, 4, '5 次采样并集覆盖约 66% 标准意见；49% 的标准意见一次也没命中')
new = [('DPO 冒烟（50 对）', '完成·不通过', '开发集综合命中 21.7%（e3 35.8%），意见数 1.34', '见「8」；暂不做正式 DPO'),
       ('分层 SFT（含 66 条拒绝采样样本）', '完成', 't3 综合命中 34.9%，与 e3 持平', '见「8」；不采用'),
       ('额外意见判定（开发集）', '完成', '已判 67 条：成立 19%、次要 31%、不成立 49%', '见「10」'),
       ('T 组：盲审重建样本（T1 格式整理已生成未训练；T2 试点 40 条）', '暂停', '盲审试点综合命中 26.7%', '用户 2026-10-26 决定暂停；方案见 新实验组方案_盲审重建.md'),
       ('项目级事实卡（L0 结构索引 + L1 摘要节选）', '进行中', '第 1 步完成：卡平均 423 字，44% 的已标注小节无摘要', '见「11」；下一步确定关键字段（L2）')]
for i, row in enumerate(new):
    r = pg.max_row + 1
    for j, v in enumerate(row, 1):
        c = pg.cell(r, j, v); c.font = copy.copy(pg.cell(3, j).font); c.alignment = copy.copy(pg.cell(3, j).alignment); c.border = copy.copy(pg.cell(3, j).border)
wb.save(X); print('已保存', X)
