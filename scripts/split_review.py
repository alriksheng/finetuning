"""评审意见拆分（方案 v4 2.9 第 2 步）：把评审意见拆成独立要点，标注所属部分。
Usage: split_review.py <review.xlsx> <out.json>
- 跳过夹带的意见模板表（含“XXX”）。
- “××部分，……一是……二是……”按“一是/二是……”拆；“一是”之前的引语单独记为 preamble。
- “降本增效情况”“‘三个标准’建立/设置情况”下按“1./2.”编号拆。
- 每个要点保留原文（text），拆分只切开、不改字。"""
import sys, re, json, openpyxl

SRC, OUT = sys.argv[1], sys.argv[2]
wb = openpyxl.load_workbook(SRC, data_only=True, read_only=True)
sheets = [[str(c).strip() for row in ws.iter_rows(values_only=True) for c in row if c is not None] for ws in wb.worksheets]
cells = next((c for c in sheets if not any('XXX' in x for x in c)), sheets[0])
meta_keys = ['项目名称', '牵头处室', '第三方机构', '预算主管部门', '是否采用简易报告', '分析金额']
meta = {k: next((cells[i + 1] for i, c in enumerate(cells[:-1]) if c.replace('\n', '') == k), '') for k in meta_keys}
kind = '政策' if any('（政策）' in c for c in cells[:3]) or any(re.match(r'^(政策基本情况|投入方向分析|投入方式分析)部分', p) for c in cells for p in c.split('\n')) else '项目'

PART = re.compile(r'^([^，。]{2,24}?部分)，')
HEADER = re.compile(r'^(降本增效情况|“三个标准”(建立|设置)情况|分析结果|总体意见)$')
ORD = re.compile(r'(?<![一二三四五六七八九十])([一二三四五六七八九十])是')
NUM = re.compile(r'(?:^|(?<=[。；\n]))\s*(\d{1,2})[\.．、]')
skip = set(v for v in meta.values() if v) | {'成本预算绩效', '分析情况', '成本预算绩效分析情况', '绩效分析情况', '政策成本预算绩效分析情况'} | set(meta_keys)

points, header = [], '总体意见'
paras = []
for c in cells:                                                       # 单元格内的续行接到上一段：只有“××部分，”、编号或标题才另起一段
    for ln in [x.strip() for x in c.split('\n') if x.strip()]:
        if paras and paras[-1][1] == id(c) and not (PART.match(ln) or NUM.match(ln) or HEADER.match(ln)):
            paras[-1][0] += ln
        else: paras.append([ln, id(c)])
paras = [x[0] for x in paras]
for p in paras:
    if p in skip or p.startswith('评审意见（') or len(p) < 6: continue
    if HEADER.match(p): header = p; continue
    m = PART.match(p)
    if m:
        part, body = m.group(1), p[m.end():]
        cuts = [x for x in ORD.finditer(body)]
        # 只认按顺序出现的“一是、二是、三是……”
        seq, want = [], 0
        for x in cuts:
            if x.group(1) == '一二三四五六七八九十'[want]: seq.append(x); want += 1
        if not seq:
            points.append(dict(part=part, preamble='', text=body)); continue
        pre = body[:seq[0].start()].rstrip('，,')
        for k, x in enumerate(seq):
            seg = body[x.end():seq[k + 1].start() if k + 1 < len(seq) else len(body)].strip().rstrip('；;')
            points.append(dict(part=part, preamble=pre, ordinal=x.group(1) + '是', text=seg))
        continue
    nums = list(NUM.finditer(p))
    if nums and nums[0].start() == 0:
        for k, x in enumerate(nums):
            seg = p[x.end():nums[k + 1].start() if k + 1 < len(nums) else len(p)].strip()
            points.append(dict(part=header, preamble='', ordinal=x.group(1) + '.', text=seg))
        continue
    points.append(dict(part=header if header != '总体意见' else '总体意见', preamble='', text=p))

for k, pt in enumerate(points, 1): pt['pid'] = f'E{k:02d}'
json.dump(dict(source=SRC, kind=kind, meta=meta, points=points), open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f"{SRC.split('/')[-1]}：{kind}，{len(points)} 个要点")
