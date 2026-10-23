"""pdftotext -layout output -> per-page reflowed text json. Usage: pdf_reflow.py in.txt out.json"""
import sys, json, re
CJK = re.compile(r'[　-〿一-鿿＀-￯“”‘’（）、，。；：！？]')
pages = open(sys.argv[1]).read().split('\f')
out = []
for i, p in enumerate(pages, 1):
    lines = [l.strip() for l in p.splitlines()]
    lines = [l for l in lines if l and l != '上海伟申工程造价咨询有限公司']
    # drop trailing printed page number line
    printed = None
    if lines and re.fullmatch(r'\d{1,3}', lines[-1]):
        printed = int(lines[-1]); lines = lines[:-1]
    buf = ''
    for l in lines:
        if not buf: buf = l; continue
        if CJK.search(buf[-1]) or CJK.search(l[0]): buf += l
        else: buf += ' ' + l
    out.append({'pdf_page': i, 'printed': printed, 'text': buf})
json.dump(out, open(sys.argv[2], 'w'), ensure_ascii=False)
print(len(out), 'pages;', sum(1 for o in out if o['printed']), 'with printed numbers')
