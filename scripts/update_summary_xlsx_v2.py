"""微调实验汇总：补入 17:30 以后的结果（第二次更新）。幂等：重复运行会先删除并重建第 11、12 页，再更新概览、数据现状、实验进度。
Usage: python3 -I update_summary_xlsx_v2.py <汇总.xlsx> <data_dir> <dev_align.jsonl>"""
import sys, json, collections, copy, yaml
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
X, D, ALIGN = sys.argv[1:4]
wb = openpyxl.load_workbook(X)
HDR = wb['1 开发集·训练与检查点']['A2']
thin = Side(style='thin', color='BBBBBB'); BORDER = Border(top=thin, bottom=thin, left=thin, right=thin)
P, F1 = '0.0%', '0.00'
def hdr(ws, row, vals):
    for j, v in enumerate(vals, 1):
        c = ws.cell(row, j, v); c.font = copy.copy(HDR.font); c.fill = copy.copy(HDR.fill); c.alignment = Alignment(wrap_text=True, vertical='center'); c.border = BORDER
    ws.row_dimensions[row].height = 34
def put(ws, row, vals, fmts=None, bold=False):
    for j, v in enumerate(vals, 1):
        c = ws.cell(row, j, v); c.font = Font(name='Arial', size=10, bold=bold); c.border = BORDER
        c.alignment = Alignment(wrap_text=isinstance(v, str) and len(v) > 12, vertical='top')
        if fmts and j - 1 < len(fmts) and fmts[j - 1]: c.number_format = fmts[j - 1]
def title(ws, row, text, cols):
    c = ws.cell(row, 1, text); c.font = Font(name='Arial', size=11, bold=True, color='1F4E78'); ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=cols)
def note(ws, row, text, cols):
    c = ws.cell(row, 1, text); c.font = Font(name='Arial', size=9, color='595959'); c.alignment = Alignment(wrap_text=True, vertical='top')
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=cols); ws.row_dimensions[row].height = 14 * (1 + len(text) // 60)
for n in [s for s in wb.sheetnames if s.startswith('11 ') or s.startswith('12 ')]: del wb[n]
# ======================= 11 项目级事实卡 =======================
ws = wb.create_sheet('11 项目级事实卡')
note(ws, 1, '项目级事实卡：统一函数按项目生成，所有样本一视同仁；L0 报告结构索引 + L1 摘要节选 + 存在性标志（E1、E2、E7）。设计与检验见 项目级事实卡设计.md 第 11、12 节；代码 scripts/fact_card.py、fact_card_exist.py。', 6)
r = 3; title(ws, r, 'A. 状态', 6); r += 1
hdr(ws, r, ['步骤', '状态', '结果', '', '', '']); r += 1
for a in [('第 1 步 L0 + L1 生成函数', '完成', '卡平均 444 字；1796 张卡 L1 与当前小节重叠 0 张'), ('第 2 步 字段依据统计', '完成', '74 条依据不在输入的专家意见中 66% 是后续年度预算安排；L2 主体改为存在性清单'),
          ('存在性检测检验', '完成', '仅 E1、E7 可靠；E3 到 E6 不可靠，暂缓'), ('事实卡版样本与训练配置', '已生成·未训练', 'data/out_card、data/train_card、train/sft_card.yaml、train/chain_card.sh'),
          ('事实卡版训练', '未做', '云端 SSH 连接被拒（connect.nma1.seetacloud.com:53501），待确认实例状态')]:
    put(ws, r, list(a)); r += 1
r += 1; title(ws, r, 'B. 卡长度（字）与 token 增量（按 0.65 token/字）', 6); r += 1
hdr(ws, r, ['指标', '已标注小节（643）', '候选小节（1153）', '说明', '', '']); r += 1
for k, a, b, f, d in [('卡字数 均值', 444, 698, '0', ''), ('卡字数 中位数', 231, 727, '0', ''), ('卡字数 P95', 1078, 1144, '0', ''), ('卡字数 最大', 1320, 1259, '0', ''),
                      ('报告没有摘要（只有结构索引）的比例', 0.44, 0.15, P, '这部分只能靠存在性标志'), ('预计 token 增量（均值）', 289, 454, '0', '现有训练输入平均约 2070 token，训练行最大约 6250 token，低于 cutoff 12288')]:
    put(ws, r, [k, a, b, d], [None, f, f, None]); r += 1
r += 1; title(ws, r, 'C. 依据不在输入里的专家意见（74 条）按类型', 6); r += 1
hdr(ws, r, ['类型', '条数', '占比', '举例', '', '']); r += 1
c0 = r
for k, n, d in [('后续年度预算安排、分析结果应用', 49, '“补充 2026 年预算测算”“与 2026 年度预算调整相挂钩”'), ('报告其他位置、页码、附件引用', 9, '“结合 15 页和 25 页两表说明资金规模不一致的原因”'),
                ('外部文件、标准、公开数据', 7, '通知文号、国标、外地同类定额'), ('其他（专家表述与报告不符等）', 9, '')]:
    put(ws, r, [k, n, f'=B{r}/SUM($B${c0}:$B${c0 + 3})', d], [None, None, P]); r += 1
r += 1; title(ws, r, 'D. 存在性检测检验：专家说“补充 X”，检测函数在当前小节以外的全报告能否找到 X', 6); r += 1
hdr(ws, r, ['编号', '含义', '归入条数', '其他小节有检测（含弱）', '其他小节有强检测', '判断']); r += 1
for a in [('E1', '后续年度预算安排（年度加金额）', 134, 0.32, 0.04, '可靠，已放入卡'), ('E7', '近年预决算表', 66, 0.20, 0.12, '基本可靠，已放入卡'), ('E3', '采购、合同、考核分析', 114, 0.61, 0.29, '不可靠，暂缓'),
          ('E4', '人员配置论证（带人数）', 98, 0.71, 0.41, '不可靠，暂缓'), ('E5', '实施体量数据', 33, 0.45, 0.45, '不可靠，暂缓'), ('E6', '成本明细表', 21, 0.43, 0.43, '不可靠，暂缓')]:
    put(ws, r, list(a), [None, None, None, P, P, None]); r += 1
note(ws, r, '强检测比例高说明“专家说缺”不等于“报告里没有”：专家要的是具体内容（如监测点位、频次），检测函数找到的是别的数量。放进卡里会压制专家想要的意见。', 6)
for j, w in enumerate([34, 26, 18, 38, 18, 24], 1): ws.column_dimensions[openpyxl.utils.get_column_letter(j)].width = w
# ======================= 12 样本构建复盘 =======================
ws = wb.create_sheet('12 样本构建复盘')
note(ws, 1, '对照 v4 对照组方案核查现有 682 条样本（训练 604 条不同样本，精标权重复制后 643 行）。详见 样本构建复盘_2026-10-26.md。', 6)
r = 3; title(ws, r, 'A. 设计与实际', 6); r += 1
hdr(ws, r, ['设计要素', '设计要求', '实际', '差距', '', '']); r += 1
for a in [('事实卡', '每个小节都带，模型抽取、程序核对', '10% 的小节样本带，人工为某条意见挑选；P003 到 P112 共 117 个字段', '大'),
          ('事实卡抽取 / 比对包 / 漏项清单样本', '各为一类样本', '1 / 15 / 1 条', '大'), ('提示核实 + 可达性', '依据不在输入时不下结论', '2026-10-23 移除；682 条全是“全部可达”', '大'),
          ('无问题样本', '15% 到 20%', '0 条（反事实无问题样本 73 条已备好：训练项目 57、开发集 8、测试集 8，未进训练）', '大'), ('证据不足样本', '约 5%', '1 条', '大'),
          ('条文改写样本', '10% 到 15%', '4 条', '中'), ('条文干扰', '每条 3 到 5 段，只有 1 到 2 段适用', '条文 3 到 8 段，多数 6 到 8 段；全不适用 2 条', '中'),
          ('人工造错、人造缺失、引文不支持结论反例', '补充真实意见较少的类型', '0 条', '中'), ('测试集标注', '只用专家精标', '开发集 46、测试集 32 条全部自动标注', '大'),
          ('精标项目数', '25 个', '2 个项目（P001、P002）39 条', '大'), ('自动标注一致性测试、专家抽查 15%', '放量前通过、放量后抽查', '未做', '大'),
          ('意见数量按规则均衡', '按规则补少削多', '31 条规则中 9 条训练意见少于 10 条', '中')]:
    put(ws, r, list(a)); r += 1
r += 1; title(ws, r, 'B. 训练意见统计（1432 条）', 6); r += 1
hdr(ws, r, ['指标', '数值', '说明', '', '', '']); r += 1
for a in [('verdict = 问题', 1431, ''), ('verdict = 证据不足', 1, ''), ('verdict = 无问题', 0, '模型从未见过“该小节无问题”的输出'),
          ('专家原话意见平均字数', 65, '中位 57；开发集专家意见平均 78'), ('模型撰写意见平均字数', 95, '占约 10%；比专家原话更长，不是模型输出变短的来源'), ('e3 额外意见平均字数', 37, '只有训练意见的约一半'),
          ('意见数字在输入中找不到的比例（专家原话）', 0.006, '训练目标基本有输入依据'), ('约一半正文小节没有进入任何样本', 0.52, '1207 个正文小节无样本，1121 个有；样本只覆盖专家提过意见的小节')]:
    put(ws, r, list(a), [None, P if isinstance(a[1], float) and a[1] < 1 else '0', None]); r += 1
r += 1; title(ws, r, 'C. 各规则的训练意见数与 e3 在开发集上的表现（106 条专家意见）', 6); r += 1
hdr(ws, r, ['规则', '训练意见数', '开发集专家意见数', '开发集命中', '命中率', '备注']); r += 1
rows = [json.loads(l) for l in open(f'{D}/out/samples.jsonl')]
cfg = yaml.safe_load(open(f'{D}/splits.yaml', encoding='utf-8')); split = {p: v['split'] for g, v in cfg['groups'].items() for p in v['projects']}
tr = collections.Counter()
for x in rows:
    if split[x['meta']['project_id']] != 'train' or x['meta'].get('task_type') not in ('小节审核', '比对包'): continue
    try:
        for f in json.loads(x['messages'][1]['content'].split('</think>')[1])['findings']: tr[f['rule_id']] += 1
    except Exception: pass
dv = collections.Counter(); hit = collections.Counter()
for l in open(ALIGN):
    a = json.loads(l)
    if a['status'] == '盲审多出': continue
    dv[a['gold_rule']] += 1; hit[a['gold_rule']] += a['status'] == '命中'
for k in sorted(set(tr) | set(dv), key=lambda k: -(tr[k] + dv[k]))[:14]:
    put(ws, r, [k, tr[k], dv[k], hit[k], f'=IF(C{r}=0,"—",D{r}/C{r})', ('额外意见 12 条全不成立' if k == 'R-BASIC-CONTENT' else '')], [None, '0', '0', '0', P]); r += 1
note(ws, r, 'e3 单次采样在开发集上：命中 35.8%、引文对上但规则不同 20.8%、规则相同引文部分重合 6.6%、仅规则相同 22.6%、漏报 14.2%。', 6)
for j, w in enumerate([36, 30, 40, 22, 12, 30], 1): ws.column_dimensions[openpyxl.utils.get_column_letter(j)].width = w
# ======================= 10 补不成立原因 =======================
ws = wb['10 诊断与判定']; r = ws.max_row + 2
hdr(ws, r, ['不成立额外意见的原因（33 条）', '条数', '占比'])
put(ws, r + 1, ['泛泛无针对', 20, f'=B{r + 1}/SUM($B${r + 1}:$B${r + 5})'], [None, None, P]); put(ws, r + 2, ['理解有误', 13, f'=B{r + 2}/SUM($B${r + 1}:$B${r + 5})'], [None, None, P])
for i, k in enumerate(['别处已写', '本小节不需要', '事实不存在']): put(ws, r + 3 + i if i < 2 else r + 5, [k, 0, f'=B{r + 3 + i if i < 2 else r + 5}/SUM($B${r + 1}:$B${r + 5})'], [None, None, P])
note(ws, r + 6, '“别处已写”为 0：额外意见差不是因为证据在报告其他位置，事实卡对此帮助有限；泛泛要求需要靠“具体性”和负样本训练，读错需要数字复算类校验。', 3)
# ======================= 5 数据现状 追加 =======================
ws = wb['5 数据现状']
for a in [('样本构建复盘', '训练意见 verdict 分布', '问题 1431 / 证据不足 1 / 无问题 0', '见「12 样本构建复盘」'), ('项目级事实卡', '事实卡版样本', '643 条小节样本加卡（43 条保留人工字段）', 'data/out_card；训练文件 data/train_card；未训练'),
          ('候选意见流水线', '专家沉默小节输入', '1153 个小节，81 个训练项目', 'data/cand/cand_inputs.jsonl；云端采样已取消，未运行'), ('T 组', 'T1 整理版样本 / 盲审试点', '680 条处理 / 40 条', 'data/out_t1；data/pilot；T2 暂停'),
          ('人工判定', '额外意见 / 不成立原因 / 诊断 1', '67 / 33 / 8 条', '额外意见_待判定.xlsx、不成立原因_待标注.xlsx、诊断1_规则对引文不对_待判定.xlsx')]:
    rr = ws.max_row + 1
    for j, v in enumerate(a, 1):
        c = ws.cell(rr, j, v); c.font = copy.copy(ws.cell(3, j).font); c.alignment = copy.copy(ws.cell(3, j).alignment); c.border = copy.copy(ws.cell(3, j).border)
# ======================= 概览 / 实验进度 =======================
ov = wb['概览']
ov['A2'] = '生成日期：2026-10-26（第二次更新：加入样本构建复盘、不成立原因、项目级事实卡第 2 步及存在性检测检验）。数据来自云上评测结果（eval_out）和人工判定表。'
ov['A25'] = '11. 根因判断：训练意见 1431/1432 条是“问题”、没有无问题样本；事实卡只有 10% 的小节样本带，事实卡抽取、比对包、漏项清单共 17 条；开发集和测试集全为自动标注（见「12」）。'
for i, t in enumerate(['12. 额外意见不成立的 33 条：泛泛无针对 20、理解有误 13、别处已写 0；因此事实卡对额外意见质量帮助有限，需要负样本与“具体性”训练、数字复算类校验。',
                       '13. 项目级事实卡（见「11」）：存在性检测里仅“后续年度预算安排”（强检测 4%）和“预决算表”（12%）可靠，采购合同、人员配置、实施体量、成本明细（29%–45%）不可靠暂缓；事实卡版样本已生成，未训练（云端 SSH 暂不可用）。']):
    c = ov.cell(26 + i, 1, t); c.font = copy.copy(ov['A24'].font); c.alignment = copy.copy(ov['A24'].alignment)
pg = wb['6 实验进度']
for rr in range(2, pg.max_row + 1):
    if str(pg.cell(rr, 1).value).startswith('项目级事实卡'):
        pg.cell(rr, 2, '样本已生成·未训练'); pg.cell(rr, 3, '卡平均 444 字；存在性检测仅 E1、E7 可靠；事实卡版样本 643 条已生成'); pg.cell(rr, 4, '见「11」；训练待云端恢复')
for a in [('候选意见流水线（专家沉默小节采样 + 判定）', '搭好·未执行', '1153 个小节输入与判定表脚本已完成并冒烟通过', '云端采样因“别处已写”为 0 的结论变化而取消；是否执行取决于“沉默小节”测量是否仍需要'),
          ('样本构建复盘', '完成', '14 项问题；设计与实际对照；补短板方案 11 项', '见「12」和 样本构建复盘_2026-10-26.md'),
          ('云端连接', '异常', 'SSH connect.nma1.seetacloud.com:53501 连接被拒', '重试 4 次间隔 20 秒无效，待确认实例状态')]:
    rr = pg.max_row + 1
    for j, v in enumerate(a, 1):
        c = pg.cell(rr, j, v); c.font = copy.copy(pg.cell(3, j).font); c.alignment = copy.copy(pg.cell(3, j).alignment); c.border = copy.copy(pg.cell(3, j).border)
wb.save(X); print('已保存', X, wb.sheetnames[-3:])
