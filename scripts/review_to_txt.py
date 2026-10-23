import sys, openpyxl
wb = openpyxl.load_workbook(sys.argv[1], data_only=True)
out = []
for ws in wb:
    for row in ws.iter_rows(values_only=True):
        for c in row:
            if c is not None:
                out.append(str(c))
open(sys.argv[2], 'w', encoding='utf-8').write('\n'.join(out))
