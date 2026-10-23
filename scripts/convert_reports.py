"""把 03-被审核报告 中的 doc/docx/pdf 转成文本，供匹配和生成样本使用。Usage: convert_reports.py <训练集目录> <out_dir>
doc/docx 用 macOS textutil；pdf 用 pdftotext -layout（按页保留换页符 \\f，用于定位页码）。扫描件 PDF 无文字层，会标注出来。"""
import sys, os, glob, subprocess, json, hashlib
ROOT, OUT = sys.argv[1], sys.argv[2]; os.makedirs(OUT, exist_ok=True)
index = []
for f in sorted(glob.glob(os.path.join(ROOT, '03-被审核报告', '**', '*.*'), recursive=True)):
    if os.path.basename(f).startswith('.'): continue
    rel = os.path.relpath(f, ROOT); rid = 'R' + hashlib.md5(rel.encode()).hexdigest()[:8]
    dst = os.path.join(OUT, rid + '.txt')
    if f.lower().endswith('.pdf'):
        subprocess.run(['pdftotext', '-layout', f, dst], capture_output=True)
    else:
        subprocess.run(['textutil', '-convert', 'txt', '-encoding', 'UTF-8', '-output', dst, f], capture_output=True)
    txt = open(dst, encoding='utf-8', errors='ignore').read() if os.path.exists(dst) else ''
    if not f.lower().endswith('.pdf') and len(''.join(txt.split())) < 1000:          # textutil 读不出的 WPS 文档改用 LibreOffice
        tmpd = os.path.join(OUT, '_soffice'); os.makedirs(tmpd, exist_ok=True)
        subprocess.run(['soffice', '--headless', '--convert-to', 'txt:Text (encoded):UTF8', '--outdir', tmpd, f], capture_output=True, timeout=300)
        cand = os.path.join(tmpd, os.path.splitext(os.path.basename(f))[0] + '.txt')
        if os.path.exists(cand): os.replace(cand, dst); txt = open(dst, encoding='utf-8', errors='ignore').read()
    chars = len(''.join(txt.split()))
    pages = txt.count('\f') + 1 if f.lower().endswith('.pdf') else None
    index.append(dict(id=rid, path=rel, fmt=os.path.splitext(f)[1].lower(), chars=chars, pages=pages,
                      text_layer=(chars / pages > 200) if pages else chars > 1000))
json.dump(index, open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
bad = [x for x in index if not x['text_layer']]
print(len(index), '份报告已转换；文字层不足（可能是扫描件）:', len(bad)); [print('  ', x['path'], x['chars'], '字', x['pages'], '页') for x in bad]
