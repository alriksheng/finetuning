"""从评审意见 xlsx 中抽取意见文字，作为语言风格语料。Usage: extract_style_corpus.py <评审意见目录> <模板xlsx> <out_dir>"""
import sys, os, glob, re, json, openpyxl
src, tpl, out = sys.argv[1:4]
recs = []
for f in sorted(glob.glob(os.path.join(src, '**', '*.xlsx'), recursive=True)) + [tpl]:
    try: wb = openpyxl.load_workbook(f, data_only=True, read_only=True)
    except Exception as e: print('skip', f, e); continue
    name = os.path.basename(f)
    for ws in wb:
        vals = [c for row in ws.iter_rows(values_only=True) for c in row if isinstance(c, str)]
        if f != tpl and any('XXX' in c for c in vals): continue          # 跳过评审意见文件中夹带的模板表
        for row in ws.iter_rows(values_only=True):
            for c in row:
                if isinstance(c, str) and len(c.strip()) >= 20:
                    recs.append(dict(file=name, sheet=ws.title, text=re.sub(r'[ \t]+', ' ', c.strip())))
seen, uniq = set(), []
for r in recs:
    if r['text'] not in seen: seen.add(r['text']); uniq.append(r)
with open(os.path.join(out, 'corpus.jsonl'), 'w', encoding='utf-8') as fo:
    for r in uniq: fo.write(json.dumps(r, ensure_ascii=False) + '\n')
print(len(uniq), 'cells from', len({r['file'] for r in uniq}), 'files;', sum(len(r['text']) for r in uniq), 'chars')
