"""共用的文本切片与核验函数（build.py 与 build_rule_samples.py 共用；以 runpy.run_path 加载，兼容 python3 -I）。"""
import re

norm = lambda s: re.sub(r'\s+', ' ', s).strip()
squash = lambda s: re.sub(r'\s+', '', s)
QUOTE = re.compile(r'「([^」]+)」')
ID_RE = re.compile(r'\b(P\d+(?:-[A-Za-z0-9]+)+)\b')
NUM = r'\d[\d,]*(?:\.\d+)?'
EXPR = re.compile(rf'({NUM}(?:\s*[+\-−×÷*/]\s*{NUM})+)\s*(=|≈)\s*({NUM})(%?)')


def squash_find(text, anchor, end=False):
    """Index in `text` of anchor (whitespace-insensitive). end=True returns end index."""
    sq, idx = [], []
    for i, ch in enumerate(text):
        if not ch.isspace(): sq.append(ch); idx.append(i)
    sq = ''.join(sq); q = squash(anchor); k = sq.find(q)
    if k < 0: return None
    return (idx[k + len(q) - 1] + 1) if end else idx[k]


def span(text, a, b=None):
    i = squash_find(text, a)
    if i is None: raise KeyError('anchor not found: ' + a[:40])
    if b is None: return norm(text[i:squash_find(text[i:], a, end=True) + i])
    jj = squash_find(text[i:], b, end=True)
    if jj is None: raise KeyError('end anchor not found: ' + b[:40])
    return norm(text[i:i + jj])


def quotes_ok(text, hay):
    """「」引文须逐字（忽略空白）出现在 hay 中；返回不通过的引文。"""
    h = squash(hay)
    return [q for q in QUOTE.findall(text) if not all(squash(p) in h for p in re.split(r'…+', q) if p.strip())]


def check_arith(text, inp, extra_allowed=()):
    """算式逐个复算；不在输入里的数字必须是已验证算式的结果（或操作数），或在 extra_allowed（如规则卡中的阈值）中。"""
    errs, derived = [], set()
    plain = lambda n: n.replace(',', '')
    for m in EXPR.finditer(text):
        lhs, rhs, pct = m.group(1), m.group(3), m.group(4)
        try: val = eval(re.sub(NUM, lambda k: plain(k.group(0)), lhs).replace('−', '-').replace('×', '*').replace('÷', '/'))
        except Exception: errs.append(f'arith: cannot evaluate {m.group(0)}'); continue
        if pct: val *= 100
        d = len(plain(rhs).split('.')[1]) if '.' in rhs else 0
        if abs(val - float(plain(rhs))) > 0.5 * 10 ** -d + 1e-9: errs.append(f'arith: {m.group(0)} (实际 {val:.4f})')
        derived.update(plain(x) for x in re.findall(NUM, m.group(0)))
    hay = re.sub(r'[\s,]', '', inp) + ' ' + ' '.join(plain(x) for x in extra_allowed)
    for n in re.findall(NUM, text):
        q = plain(n)
        if len(q.replace('.', '')) >= 2 and q not in hay and q not in derived:
            errs.append(f'number {n} not in input and not a verified result')
    return errs, derived
