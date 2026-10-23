"""待确认汇总表（只出需要专家确认的内容）。Usage: python3 -I make_pending_round.py <data_dir> <轮次名>
一张表：待确认要点（模型撰写的其他要点）。L3-07 衔接、模型补充发现已采纳或由我方判断（用户 2026-10-19），不再列入；提示核实：第八轮前的已全部采纳，不再列入，PDF 转 Word 后新做的 21 个项目的提示核实第九轮表也已全部采纳，不再列入（用户 2026-10-22）；表可能为空。L3-07 衔接（规则预制）按沪财绩〔2024〕15号、〔2025〕8号和规则文件判断，不再送专家确认（用户 2026-10-19）；口径待确认已由政策原文统一（规则文件第五节），报告数据疑点不再关注。
读 data/out/samples.jsonl，写 data/out/专家确认表_<轮次名>.xlsx。"""
import sys, os, json, re, glob, csv
import yaml
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
D, ROUND = sys.argv[1], sys.argv[2]
thin = Side(style='thin', color='BBBBBB'); yellow = PatternFill('solid', fgColor='FFF2CC')


def header(ws, heads, widths):
    for j, (h, w) in enumerate(zip(heads, widths), 1):
        c = ws.cell(row=1, column=j, value=h); c.font = Font(bold=True, color='FFFFFF'); c.fill = PatternFill('solid', fgColor='1F4E78')
        c.alignment = Alignment(wrap_text=True, vertical='center', horizontal='center'); ws.column_dimensions[c.column_letter].width = w


def put(ws, i, vals, fill_from, height):
    for j, v in enumerate(vals, 1):
        c = ws.cell(row=i + 1, column=j, value=v); c.alignment = Alignment(wrap_text=True, vertical='top'); c.border = Border(top=thin, bottom=thin, left=thin, right=thin)
        if j >= fill_from: c.fill = yellow
    ws.row_dimensions[i + 1].height = height


wb = Workbook(); ws0 = wb.active; ws0.title = '说明'
for i, t in enumerate(['待确认汇总表使用说明', '',
                       '本表只列需要专家确认的内容，已确认的内容不再出现。黄色列为专家填写。', '',
                       '一、“待确认要点”：模型撰写的评审意见——',
                       '· 提示核实：专家原话所指的依据在报告中查不到，只提示核实位置，不下结论。',
                       '请选“采纳 / 修改后采纳 / 驳回”；修改后采纳的，在“修改后的意见”里改写。', ''
                       ], 1):
    c = ws0.cell(row=i, column=1, value=t); c.alignment = Alignment(wrap_text=True, vertical='top')
ws0['A1'].font = Font(bold=True, size=14); ws0.column_dimensions['A'].width = 110

# 一、待确认要点
HINT_PROJ = {r['编号'] for r in csv.DictReader(open(os.path.join(D, 'batch/manifest.csv'), encoding='utf-8-sig')) if 'PDF 转 Word' in r['需人工处理']}   # 这些项目的提示核实送专家确认
rows = [json.loads(l) for l in open(os.path.join(D, 'out/samples.jsonl'), encoding='utf-8')]
SENT = {'V3_P001_base_indicator_01', 'V3_P002_base_indicator_01', 'V4_P003_S022', 'V4_P005_S021'}   # 第八轮原有 4 条，仍待确认，保留在最前
ws = wb.create_sheet('待确认要点')
header(ws, ['序号', '要点编号', '项目', '类型', '所在小节', '待确认的意见', '依据（报告原文，已核对）', '推理中对应的判断', '专家判断', '修改后的意见', '备注'], [6, 30, 16, 16, 28, 60, 60, 60, 14, 50, 36])
kind = lambda reason, verdict: ('提示核实' if verdict == '提示核实' else 'L3-07 衔接' if '规则预制' in reason else '模型补充发现' if '模型补充发现' in reason else '其他模型撰写')
sel = []
for r in rows:
    m = r['meta']; st = m.get('status') or ''
    if r['id'] not in SENT and (st.startswith('专家') or not (r['id'].startswith('V6_') or r['id'].startswith('V4_P01'))): continue
    think, js = r['messages'][1]['content'].split('</think>\n', 1)
    fs = json.loads(js).get('findings', [])
    marked = any('待专家确认' in (t.get('reason') or '') for t in m['text_sources'])   # 要点级标记优先：第八轮原有样本只出标了待确认的要点
    for f, ts in zip(fs, m['text_sources']):
        if ts['source'] != '模型撰写': continue
        if r['id'] in SENT and '待专家确认' not in (ts.get('reason') or ''): continue
        k = kind(ts.get('reason') or '', f['verdict'])
        if k in ('L3-07 衔接', '模型补充发现'): continue   # L3-07 规则判断由我方按 8 号文、15 号文定；模型补充发现已全部采纳
        if k == '提示核实': continue   # 提示核实已全部采纳（第八轮前；PDF 转 Word 项目的第九轮表也已全部采纳，用户 2026-10-22）
        sel.append((0 if r['id'] in SENT else 1, r, think, f, ts))
sel.sort(key=lambda x: (x[0], x[1]['id']))
for n, (_, r, think, f, ts) in enumerate(sel, 1):
    m = r['meta']
    seg = next((ln for ln in think.split('\n') if f['rule_id'] and f['rule_id'] in ln), '')
    reason = ts.get('reason') or ''
    ev = '\n'.join(f"· [{e['source']}｜{e['loc']}] {e['quote']}" for e in f['evidence']) or '（依据不可达：见备注）'
    put(ws, n, [n, r['id'], m['project'][:14], kind(reason, f['verdict']), m['input_scope'].replace('小节：', ''), f['problem'] + f['suggestion'], ev, seg, None, None, reason], 9, 150)
dv = DataValidation(type='list', formula1='"采纳,修改后采纳,驳回"', allow_blank=True); ws.add_data_validation(dv); ws.freeze_panes = 'C2'
if sel: dv.add(f'I2:I{len(sel) + 1}')
print('待确认要点', len(sel))

out = os.path.join(D, f'out/专家确认表_{ROUND}.xlsx'); wb.save(out); print('->', out)
