"""Auto-split each decision into (case facts | reasoning | conclusion) and report sizes. Usage: split_decisions.py <txt_dir> <ids...>"""
import sys, re, os
D = sys.argv[1]
SKIP = re.compile(r'^\s*(地址|通讯地址|法定代表人|授权代表|委托代理人|邮政编码)[：:]')
def load(i):
    if i in ('pinghu', 'changshan'):
        t = open(os.path.join(D, '../raw', i + '.txt'), encoding='utf-8').read()
        # reflow pdf: join hard-wrapped lines
        t = re.sub(r'\n\s*-\s*\d+\s*-\s*\n', '\n', t)
        t = re.sub(r'\s*\n\s*', '', t)
        t = re.sub(r'(一|二|三|四|五|六|七)、', r'\n\1、', t)
        return t
    t = open(os.path.join(D, i + '.txt'), encoding='utf-8').read()
    lines = [l for l in t.splitlines() if not SKIP.match(l)]
    return '\n'.join(lines)
def split(t):
    m = re.search(r'(经审查，?\s*本机关认为|本机关经审查|经审查[：:，]|本机关认为)', t[300:])
    k = m.start() + 300 if m else -1
    tail = re.search(r'(如不服|如对本|当事人如|相关当事人如|如对上述)', t[k:] if k > 0 else t)
    e = (k + tail.start()) if (tail and k > 0) else len(t)
    return k, e
for i in sys.argv[2:]:
    t = load(i)
    k, e = split(t)
    concl = [m.start() for m in re.finditer(r'(决定如下|处理决定如下|本机关决定|作出处理决定)', t[k:e])] if k > 0 else []
    c = (k + concl[-1]) if concl else -1
    print(f'{i:12s} total={len(t):6d} facts={k:6d} reasoning={max(c-k,0):6d} concl={e-c if c>0 else 0:5d}')
