"""批量预处理（样本生成标准第二节第 1–4 步）：为待标注项目分配编号，转换报告、拆分评审意见、切分小节，登记项目信息。

Usage: python3 -I scripts/prepare_batch.py <训练集目录> data
输入：data/match/projects_usable.json（匹配结果）、data/specs/projects.json（已有项目）
输出：
  data/raw/reports/<P>.md、data/raw/reviews/<P>.txt
  data/specs/sections/<P>.json、data/specs/review_points/<P>.json
  data/specs/projects.json（追加，标注方式为“自动标注”）
  data/batch/manifest.csv（每个项目一行：编号、名称、类型、格式、字数、小节数、要点数、需人工处理的情况）
已登记的项目不重复处理；弃用项目（overrides.yaml 中的排除项）不在 projects_usable.json 中。
"""
import sys, os, re, json, csv, glob, shutil, subprocess, tempfile
import openpyxl

ROOT, DATA = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
usable = json.load(open(os.path.join(DATA, 'match/projects_usable.json'), encoding='utf-8'))
pj_path = os.path.join(DATA, 'specs/projects.json')
PROJ = json.load(open(pj_path, encoding='utf-8'))
done = {v.get('report') for v in PROJ.values()} | {v.get('review') for v in PROJ.values()}
NAMES = [v['name'] for v in PROJ.values()]
known = lambda u: u['report'] in done or u['review'] in done or any(n[:8] in u['project'] or u['project'][:8] in n for n in NAMES)
NEW_KW = re.compile(r'新建|新增|改扩建|扩建|工程项目|建设工程项目|绿地工程|道路工程|大修工程')


def review_header(path):
    """评审意见表头：分析金额、预算主管部门、项目名称。"""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True); info = {}
    for ws in wb:
        rows = [[c for c in r] for r in ws.iter_rows(values_only=True)]
        for r in rows:
            for i, c in enumerate(r):
                if isinstance(c, str):
                    for k in ('分析金额', '预算主管部门', '项目名称'):
                        if k in c and k not in info:
                            rest = c.split(k, 1)[1].lstrip('：: ')
                            val = rest or next((str(x) for x in r[i + 1:] if x not in (None, '')), '')
                            if val: info[k] = val.strip()
        break
    return info


def to_md(src, dst):
    ext = os.path.splitext(src)[1].lower()
    if ext == '.docx':
        subprocess.run([PY, '-I', os.path.join(HERE, 'docx_to_md.py'), src, dst], check=True)
    elif ext == '.doc':
        tmp = tempfile.mkdtemp()
        subprocess.run(['soffice', '--headless', '--convert-to', 'docx', '--outdir', tmp, src], check=True, capture_output=True)
        out = glob.glob(os.path.join(tmp, '*.docx'))[0]
        subprocess.run([PY, '-I', os.path.join(HERE, 'docx_to_md.py'), out, dst], check=True); shutil.rmtree(tmp)
    elif ext == '.pdf':
        txt = subprocess.run(['pdftotext', '-layout', src, '-'], check=True, capture_output=True).stdout.decode('utf-8', 'ignore')
        lines = [re.sub(r'[ \t]{2,}', ' ', l).strip() for l in txt.replace('\f', '\n').split('\n')]
        open(dst, 'w', encoding='utf-8').write('\n'.join(l for l in lines if l))
    return sum(len(re.sub(r'\s', '', l)) for l in open(dst, encoding='utf-8'))


def main():
    os.makedirs(os.path.join(DATA, 'batch'), exist_ok=True)
    for d in ('raw/reports', 'raw/reviews', 'specs/sections', 'specs/review_points'): os.makedirs(os.path.join(DATA, d), exist_ok=True)
    nums = [int(k[1:]) for k in PROJ if re.fullmatch(r'P\d{3}', k)]
    nxt = max(nums) + 1
    todo = sorted([u for u in usable if not known(u)], key=lambda u: (u['dept'], u['project']))
    rows = []
    for u in todo:
        pid = f'P{nxt:03d}'; nxt += 1
        flags = []
        if u.get('confidence') not in ('高', '人工判定'): flags.append(f"匹配置信度{u.get('confidence')}，需人工确认配对")
        if not u.get('text_layer', True): flags.append('扫描件无文字层，需 OCR')
        rpt = os.path.join(DATA, 'raw/reports', pid + '.md'); chars = 0
        try: chars = to_md(os.path.join(ROOT, u['report']), rpt)
        except Exception as e: flags.append(f'报告转换失败：{type(e).__name__}')
        if 0 < chars < 6000: flags.append(f'报告仅 {chars} 字，需核对是否为简易版或转换不全')
        if u['fmt'] == '.pdf': flags.append('PDF 转换：表格可能错行，切分和摘录需核对')
        rv_src = os.path.join(ROOT, u['review'])
        subprocess.run([PY, '-I', os.path.join(HERE, 'review_to_txt.py'), rv_src, os.path.join(DATA, 'raw/reviews', pid + '.txt')], check=True)
        npts = nsec = 0
        try:
            subprocess.run([PY, '-I', os.path.join(HERE, 'split_review.py'), rv_src, os.path.join(DATA, 'specs/review_points', pid + '.json')], check=True, capture_output=True)
            npts = len(json.load(open(os.path.join(DATA, 'specs/review_points', pid + '.json'), encoding='utf-8'))['points'])
        except Exception as e: flags.append(f'意见拆分失败：{type(e).__name__}')
        if chars:
            try:
                subprocess.run([PY, '-I', os.path.join(HERE, 'section_report.py'), rpt, os.path.join(DATA, 'specs/sections', pid + '.json')], check=True, capture_output=True)
                nsec = len(json.load(open(os.path.join(DATA, 'specs/sections', pid + '.json'), encoding='utf-8'))['units'])
            except Exception as e: flags.append(f'报告切分失败：{type(e).__name__}')
        if nsec and nsec < 8: flags.append(f'仅切出 {nsec} 个小节，需核对标题识别')
        if npts == 0: flags.append('评审意见未拆出要点')
        hd = review_header(rv_src)
        md = open(rpt, encoding='utf-8').read() if chars else ''
        sec_policy = json.load(open(os.path.join(DATA, 'specs/sections', pid + '.json'), encoding='utf-8')).get('policy') if nsec else False
        # 项目类型：政策报告 → 政策；名称写明新建，或报告含投资估算、工程建设其他费用 → 新建工程；其余为经常性
        ptype = '政策' if (u['kind'] == '政策' or sec_policy or '政策基本情况' in md[:3000]) else \
                ('新建工程' if ('新建' in u['project'] or md.count('投资估算') >= 3 or '工程建设其他费用' in md) else '经常性')
        PROJ[pid] = dict(name=u['project'], agency=hd.get('预算主管部门') or u.get('agency') or '待填', amount=hd.get('分析金额') or '待填',
                         report_version='批量：' + os.path.basename(u['report']), review_date=None, group=f"{u['dept']}｜{u['project']}",
                         kind=u['kind'], dept=u['dept'], review=u['review'], report=u['report'], annotation='自动标注', ptype=ptype,
                         batch_flags=flags)
        rows.append(dict(编号=pid, 项目=u['project'], 处室=u['dept'], 类型=ptype, 格式=u['fmt'], 报告字数=chars, 小节数=nsec, 意见要点数=npts,
                         需人工处理='；'.join(flags), 状态='待标注'))
        print(pid, u['project'][:24], ptype, chars, nsec, npts, '；'.join(flags))
    json.dump(PROJ, open(pj_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    path = os.path.join(DATA, 'batch/manifest.csv')
    old = list(csv.DictReader(open(path, encoding='utf-8-sig'))) if os.path.exists(path) else []
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['编号', '项目', '处室', '类型', '格式', '报告字数', '小节数', '意见要点数', '需人工处理', '状态'])
        w.writeheader(); w.writerows(old + rows)
    print(f'新登记 {len(rows)} 个项目 -> {path}')


main()
