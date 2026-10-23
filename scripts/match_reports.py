"""把 03-被审核报告 与 04-审核意见 按项目匹配。Usage: match_reports.py <训练集目录> <out_dir>
规则：同一处室内配对；以评审意见表内的“项目名称”（缺失时用文件名）与报告文件名的字符二元组重合度打分，
再用预算主管部门、第三方机构名在报告文件名中出现加分；按分数从高到低一对一分配，低分结果单列待人工确认。"""
import sys, os, re, glob, json, csv, openpyxl
ROOT, OUT = sys.argv[1], sys.argv[2]
_rt = lambda x: os.path.join(OUT, 'report_text', x['id'] + '.txt')
TXT = {x['path']: (open(_rt(x), encoding='utf-8', errors='ignore').read() if os.path.exists(_rt(x)) else '') for x in json.load(open(os.path.join(OUT, 'report_text', 'index.json'), encoding='utf-8'))}
sq = lambda s: re.sub(r'[\s,，]', '', s)
DEPTS = ['企业处', '农业处', '外经处', '教科文处', '社保处', '经建处', '资环处', '预算处']
STOP = r'成本预算绩效分析|成本绩效分析|成本分析|绩效评价|报告|项目|经费|初稿|定稿|终稿|修改|最终稿|简易|简要的|会审稿|交付审核稿|扫描件|盖章|敲章版|上海市|上海|市级|（.*?）|\(.*?\)|【.*?】|\d{3,8}|[\s\-—_.·：:“”"《》、，,]'
clean = lambda s: re.sub(STOP, '', re.sub(r'\.(docx?|pdf|xlsx)$', '', s))
bigr = lambda s: {s[i:i + 2] for i in range(len(s) - 1)} or {s}

def review_meta(path):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheets = [[str(c).strip() for row in ws.iter_rows(values_only=True) for c in row if c is not None] for ws in wb.worksheets]
    real = [c for c in sheets if not any('XXX' in x for x in c)]          # 跳过未替换的意见模板表
    cells = (real or sheets)[0]
    get = lambda key: next((cells[i + 1] for i, c in enumerate(cells[:-1]) if c.replace('\n', '') == key), '')
    return dict(name=get('项目名称'), agency=get('预算主管部门'), org=get('第三方机构'), amount=get('分析金额'),
                simple=get('是否采用简易报告'), kind='政策' if any('评审意见（政策）' in c for c in cells[:3]) else '项目')

reviews = []
for f in sorted(glob.glob(os.path.join(ROOT, '04-审核意见', '**', '*.xlsx'), recursive=True)):
    b = os.path.basename(f); dept = next((d for d in DEPTS if b.startswith(d)), None)
    m = review_meta(f); fname_proj = re.sub(r'^[^-]+-[^-]+-', '', b[:-5])
    reviews.append(dict(path=os.path.relpath(f, ROOT), dept=dept, fname_proj=fname_proj, **m))
reports = []
for f in sorted(glob.glob(os.path.join(ROOT, '03-被审核报告', '**', '*.*'), recursive=True)):
    if os.path.basename(f).startswith('.'): continue
    rel = os.path.relpath(f, os.path.join(ROOT, '03-被审核报告'))
    reports.append(dict(path=os.path.relpath(f, ROOT), dept=rel.split(os.sep)[0], key=clean(rel.split(os.sep, 1)[1].replace(os.sep, '')),
                        fname=rel, text=sq(TXT.get(os.path.relpath(f, ROOT), ''))))

def score(rv, rp):
    best = 0
    for nm in {rv['name'], rv['fname_proj']}:
        a, b = bigr(clean(nm)), bigr(rp['key'])
        if a and b: best = max(best, len(a & b) / min(len(a), len(b)))
    bonus = 0.1 * sum(1 for x in (rv['agency'], rv['org']) if x and len(x) >= 2 and clean(x)[:4] and clean(x)[:4] in rp['key'])
    # 正文证据：分析金额、第三方机构、文件名括号中的单位
    amt = re.search(r'\d[\d,.]*', rv['amount'] or '')
    if amt and len(amt.group().replace(',', '')) >= 3 and amt.group().replace(',', '') in rp['text']: bonus += 0.5
    if rv['org'] and len(rv['org']) >= 6 and rv['org'] != '自行开展' and sq(rv['org'])[:8] in rp['text']: bonus += 0.3
    for u in re.findall(r'（([^）]+)）', rv['fname_proj']) + re.findall(r'-([^-（）]+)$', rv['fname_proj']):
        for w in re.split(r'[、，]', u):
            w = w.replace('训练基地管理中心', '基地中心').replace('设施管理中心', '场馆设施管理中心').replace('体校', '市体校').strip()
            if len(w) >= 2 and w in rp['fname']: bonus += 0.4
    return round(best + bonus, 3)

pairs = sorted(((score(rv, rp), i, j) for i, rv in enumerate(reviews) for j, rp in enumerate(reports) if rv['dept'] == rp['dept']), reverse=True)
used_r, used_p, match = set(), set(), {}
for s, i, j in pairs:
    if i in used_r or j in used_p or s < 0.25: continue
    used_r.add(i); used_p.add(j); match[i] = (j, s)
import yaml                                                          # 人工判定的配对（overrides.yaml）
OV = yaml.safe_load(open(os.path.join(OUT, 'overrides.yaml'), encoding='utf-8')) if os.path.exists(os.path.join(OUT, 'overrides.yaml')) else []
ri = {rv['path']: i for i, rv in enumerate(reviews)}; pj = {rp['path']: j for j, rp in enumerate(reports)}
for o in OV:
    i, j = ri[o['review']], pj[o['report']]
    if o.get('check_amount') and o['check_amount'] not in (reviews[i]['amount'] or ''): raise SystemExit(f"override amount mismatch: {o['review']}")
    for k in [k for k, v in match.items() if v[0] == j or k == i]: match.pop(k)
    match[i] = (j, 'override'); reviews[i]['override'] = o
for i, rv in enumerate(reviews):                                     # 同一项目两版意见：关联到同一份报告，以较新的一版为准
    if i in match: continue
    for k, (j, s) in list(match.items()):
        if clean(reviews[k]['name'] or reviews[k]['fname_proj']) == clean(rv['name'] or rv['fname_proj']) and reviews[k]['dept'] == rv['dept']:
            newer = k if re.search(r'-2025\d{4}\.xlsx$', reviews[k]['path']) else i
            match[i] = (j, s); rv['dup_of'] = reviews[k]['path']; rv['use'] = newer == i; reviews[k]['use'] = newer == k
rows = []
for i, rv in enumerate(reviews):
    j, s = match.get(i, (None, 0))
    second = max((p[0] for p in pairs if p[1] == i and p[2] != j), default=0)
    o = rv.get('override')
    rows.append(dict(dept=rv['dept'], review=rv['path'], project=rv['name'] or rv['fname_proj'], agency=rv['agency'], org=rv['org'], kind=rv['kind'],
                     report=reports[j]['path'] if j is not None else '', score=s, runner_up=second,
                     confidence=(o.get('confidence', '人工判定') if o else ('高' if s >= 0.6 and s - second >= 0.15 else ('待确认' if j is not None else '未匹配'))),
                     note=(o['reason'] if o else '') + (('同一项目两版意见，' + ('采用本版' if rv.get('use') else '以另一版为准')) if 'use' in rv else '')))

unmatched_reports = [rp['path'] for j, rp in enumerate(reports) if j not in {v[0] for v in match.values()}]
with open(os.path.join(OUT, 'matches.csv'), 'w', encoding='utf-8-sig', newline='') as fo:
    w = csv.DictWriter(fo, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
json.dump(dict(matches=rows, unmatched_reports=unmatched_reports), open(os.path.join(OUT, 'matches.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
from collections import Counter
print('评审意见', len(reviews), '报告', len(reports), '| 置信度', dict(Counter(r['confidence'] for r in rows)), '| 未匹配报告', len(unmatched_reports))
