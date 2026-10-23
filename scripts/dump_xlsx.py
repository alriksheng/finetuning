import sys, openpyxl
wb = openpyxl.load_workbook(sys.argv[1], data_only=True)
for ws in wb:
    print(f"=== SHEET {ws.title} {ws.dimensions}")
    for r, row in enumerate(ws.iter_rows(values_only=True), 1):
        if any(c is not None for c in row):
            print(f"[R{r}] " + " | ".join("" if c is None else str(c).replace("\n", " ⏎ ") for c in row))
