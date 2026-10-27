"""多次采样投票。Usage: python3 -I eval_vote.py --pred <含 outputs 列表的预测文件> --out <投票后的预测文件> [--min-votes K]
把同一输入的 n 次输出里的意见聚类（规则编号相同，且证据引文重合或问题+建议的二字组召回 ≥0.35），
只保留被至少 K 次采样都提出的意见（默认 K = ⌈n/2⌉；K=1 即并集）。输出格式同 eval_run.py 的预测文件，可直接给 eval_score.py 打分。"""
import argparse, json, re, difflib, math, collections
ap = argparse.ArgumentParser(); ap.add_argument('--pred', required=True); ap.add_argument('--out', required=True); ap.add_argument('--min-votes', type=int, default=0)
a = ap.parse_args()
squash = lambda s: re.sub(r'\s+', '', s or '')
bigrams = lambda s: collections.Counter(s[i:i + 2] for i in range(len(s) - 1))
def recall(g, p):
    g, p = bigrams(squash(g)), bigrams(squash(p)); return sum((g & p).values()) / max(1, sum(g.values()))
def quote_hit(x, y):
    x, y = squash(x), squash(y)
    if not x or not y: return False
    m = difflib.SequenceMatcher(None, x, y, autojunk=False).find_longest_match(0, len(x), 0, len(y))
    return m.size >= 10 and m.size >= 0.5 * min(len(x), len(y))
quotes = lambda f: [e.get('quote', '') for e in (f.get('evidence') or []) if isinstance(e, dict)]
text = lambda f: (f.get('problem') or '') + (f.get('suggestion') or '')
def same(f, g):
    if f.get('rule_id') != g.get('rule_id'): return False
    if any(quote_hit(x, y) for x in quotes(f) for y in quotes(g)): return True
    return max(recall(text(f), text(g)), recall(text(g), text(f))) >= 0.35
def parse(t):
    t = (t or '').split('</think>')[-1].strip(); i = t.find('{')
    if i < 0: return None
    try: return json.JSONDecoder().raw_decode(t[i:])[0]
    except Exception: return None
kept = total = 0
with open(a.out, 'w', encoding='utf-8') as fo:
    for line in open(a.pred, encoding='utf-8'):
        p = json.loads(line); outs = p.get('outputs') or [p.get('output')]; n = len(outs); k = a.min_votes or math.ceil(n / 2)
        clusters = []   # [代表意见, 票数集合]
        for si, o in enumerate(outs):
            obj = parse(o)
            for f in (obj or {}).get('findings', []) if isinstance(obj, dict) else []:
                if not isinstance(f, dict): continue
                for c in clusters:
                    if same(c[0], f): c[1].add(si); c.append(f); break
                else: clusters.append([f, {si}])
        total += len(clusters)
        keep = [max([c[0]] + [x for x in c[2:]], key=lambda f: len(quotes(f))) for c in sorted(clusters, key=lambda c: -len(c[1])) if len(c[1]) >= k]
        kept += len(keep)
        p = dict(p); p['output'] = '</think>\n\n' + json.dumps({'task': '小节审核', 'findings': keep}, ensure_ascii=False); p.pop('outputs', None)
        fo.write(json.dumps(p, ensure_ascii=False) + '\n')
print(f'聚类 {total} 类，保留 {kept} 类（{kept / max(1, total):.1%}）')
