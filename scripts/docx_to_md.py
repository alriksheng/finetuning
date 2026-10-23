"""Convert .docx to markdown-ish text keeping paragraph/table order. Usage: docx_to_md.py in.docx out.md"""
import sys, docx
from docx.table import Table
from docx.text.paragraph import Paragraph

def iter_block(doc):
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit('}', 1)[-1]
        if tag == 'p':
            yield Paragraph(child, doc)
        elif tag == 'tbl':
            yield Table(child, doc)

def cell_text(c):
    return c.text.replace('\n', ' ⏎ ').replace('|', '¦').strip()

d = docx.Document(sys.argv[1])
out = []
for b in iter_block(d):
    if isinstance(b, Paragraph):
        t = b.text.strip()
        if not t:
            continue
        st = (b.style.name or '') if b.style is not None else ''
        if st.startswith('Heading') or st.startswith('标题'):
            lvl = ''.join(ch for ch in st if ch.isdigit()) or '1'
            out.append('#' * min(int(lvl), 6) + ' ' + t)
        else:
            out.append(t)
    else:
        rows = []
        for r in b.rows:
            seen, cells = set(), []
            for c in r.cells:
                if id(c._tc) in seen:
                    continue
                seen.add(id(c._tc)); cells.append(cell_text(c))
            rows.append('| ' + ' | '.join(cells) + ' |')
        if rows:
            out.append('[表格]\n' + '\n'.join(rows) + '\n[/表格]')
open(sys.argv[2], 'w').write('\n'.join(out))
print(len(out), 'blocks')
