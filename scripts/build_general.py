"""Build the 'general' (政府采购投诉处理) QA samples from public decisions.
Usage: python3 -I build_general.py <data_dir>
Input : data/annotations_general/*.py  (ANNOTATIONS), data/ext/procurement/{txt,raw}, data/clauses/clauses_general.json
Output: data/out_general/{samples_general.jsonl, train_general_sharegpt.json, preview.md, report.txt}
All verbatim anchors are whitespace-insensitive."""
import sys, os, re, json, glob, runpy, hashlib, random
DATA = sys.argv[1]
OUT = os.path.join(DATA, 'out_general'); os.makedirs(OUT, exist_ok=True)
SYSTEM = ("你是财政部门负责政府采购投诉处理的审理人员。只能依据输入中给出的案情材料和条文作出判断；"
          "先逐项核对事实与规则，再给出处理结论；引用条文必须逐字摘录并标注条文编号；案情不足以下结论时写明需要补充什么。")
GEN = 'claude-sonnet-5-5 (Claude Code) — 推理与措辞为初稿，须经专家确认'
def norm(s): return re.sub(r'\s+', ' ', s).strip()
def squash(s): return re.sub(r'\s+', '', s)

def load_src(key):
    if key in ('pinghu', 'changshan'):
        t = open(os.path.join(DATA, 'ext/procurement/raw', key + '.txt'), encoding='utf-8').read()
        t = re.sub(r'\n\s*-\s*\d+\s*-\s*\n', '\n', t); return re.sub(r'\s*\n\s*', '', t)
    return open(os.path.join(DATA, 'ext/procurement/txt', key + '.txt'), encoding='utf-8').read()

class Src:
    def __init__(self, text):
        self.orig = text
        idx, chars = [], []
        for i, ch in enumerate(text):
            if not ch.isspace():
                idx.append(i); chars.append(ch)
        self.sq = ''.join(chars); self.idx = idx
    def span(self, a, b=None):
        qa = squash(a); i = self.sq.find(qa)
        if i < 0: raise KeyError('start not found: ' + a[:40])
        if b is None: j = i + len(qa)
        else:
            qb = squash(b); k = self.sq.find(qb, i)
            if k < 0: raise KeyError('end not found: ' + b[:40])
            j = k + len(qb)
        return norm(self.orig[self.idx[i]: self.idx[j - 1] + 1])
    def has(self, snippet): return squash(snippet) in self.sq

CL = {c['clause_id']: c for c in json.load(open(os.path.join(DATA, 'clauses/clauses_general.json'), encoding='utf-8'))}
QUOTE = re.compile(r'「([^」]+)」')
ID_RE = re.compile(r'\b(G\d+-\d+)\b')
def cline(c): return f"[{c['clause_id']}｜{c['doc_no']}《{c['title']}》{c['location']}｜{c['effective_from']}] {c['text']}"

def build(s):
    errs, warns = [], []
    srcs = {}
    def S(k):
        if k not in srcs: srcs[k] = Src(load_src(k))
        return srcs[k]
    parts = []
    if s.get('manual_input'):
        parts.append('【案情】\n' + '\n'.join(s['manual_input']))
    else:
        src = S(s['src']); ex = []
        for p in s['parts']:
            try: ex.append(src.span(p[0], p[1] if len(p) > 1 else None))
            except KeyError as e: errs.append(f'input part: {e}')
        for e in s.get('extra_facts', []): ex.append('【补充查明】' + e)
        parts.append('【案情】\n' + '\n'.join(ex))
        for m in s.get('must_match', []):
            if not src.has(m): errs.append(f'must_match not in decision: {m}')
    app = s.get('clauses', [])
    for c in app:
        if c not in CL: errs.append(f'unknown clause {c}')
    pool = [c for c in CL if c not in app]
    random.Random(int(hashlib.md5(s['id'].encode()).hexdigest()[:8], 16)).shuffle(pool)
    shown = [c for c in app if c in CL] + pool[:2]
    random.Random(int(hashlib.md5((s['id'] + 'o').encode()).hexdigest()[:8], 16)).shuffle(shown)
    parts.append('【条文】\n' + '\n'.join(cline(CL[c]) for c in shown))
    parts.append('【任务】' + s['task'])
    user = '\n\n'.join(parts)
    hn, hs = norm(user), squash(user)
    for where in ('think', 'answer'):
        for q in QUOTE.findall(s[where]):
            pcs = [p for p in re.split(r'…+', q) if p.strip()]
            if not all(squash(p) in hs for p in pcs): errs.append(f'{where}: quote not in input: 「{q[:40]}」')
    for num in sorted(set(re.findall(r'\d[\d,\.]*\d|\d', s['think'] + s['answer']))):
        if len(num.replace(',', '').replace('.', '')) >= 2 and num not in user and num.replace(',', '') not in user:
            warns.append(f'number not in input: {num}')
    ids = set(ID_RE.findall(s['think'] + s['answer']))
    for i in ids:
        if i not in shown: errs.append(f'cited {i} not in input')
    for i in app:
        if i not in ids: warns.append(f'applicable {i} never cited')
    tr = lambda t: QUOTE.sub(lambda m: '“' + m.group(1) + '”', t).strip()
    assistant = f"<think>\n{tr(s['think'])}\n</think>\n{tr(s['answer'])}"
    n = len(SYSTEM) + len(user) + len(assistant)
    if n > 6500: errs.append(f'too long {n}')
    rec = dict(id=s['id'], meta=dict(
        bucket='general_policy_cot', topic='政府采购投诉处理', outcome_category=s['outcome'], province=s['province'], authority=s['authority'],
        decision_date=s['date'], decision_no=s.get('decision_no'), source_url=s['url'], verbatim_input=not s.get('manual_input'),
        clause_ids=app, distractor_clause_ids=shown and [c for c in shown if c not in app], generator=GEN,
        status='待专家确认', approx_chars=n, notes=s.get('notes')),
        system=SYSTEM, messages=[dict(role='user', content=user), dict(role='assistant', content=assistant)])
    return rec, errs, warns

ok, bad, wl = [], [], []
for f in sorted(glob.glob(os.path.join(DATA, 'annotations_general/*.py'))):
    for s in runpy.run_path(f)['ANNOTATIONS']:
        try: rec, errs, warns = build(s)
        except Exception as e: bad.append(dict(id=s['id'], errors=[repr(e)])); continue
        wl += [f"{s['id']}: {w}" for w in warns]
        if errs: rec['errors'] = errs; bad.append(rec)
        else: ok.append(rec)
with open(os.path.join(OUT, 'samples_general.jsonl'), 'w', encoding='utf-8') as fo:
    for r in ok: fo.write(json.dumps(r, ensure_ascii=False) + '\n')
json.dump([dict(system=r['system'], conversations=[{'from': 'human', 'value': r['messages'][0]['content']}, {'from': 'gpt', 'value': r['messages'][1]['content']}]) for r in ok],
          open(os.path.join(OUT, 'train_general_sharegpt.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
with open(os.path.join(OUT, 'preview.md'), 'w', encoding='utf-8') as fo:
    fo.write('# 通用数据（政府采购投诉处理）预览\n\n')
    for r in ok:
        m = r['meta']
        fo.write(f"## {r['id']} · {m['outcome_category']} · {m['province']}（{m['authority']}，{m['decision_date']}）\n- 来源：{m['source_url']}\n- 案情是否逐字摘自原文：{'是' if m['verbatim_input'] else '否（据网页摘要改写）'}\n\n**输入**\n\n```\n{r['messages'][0]['content']}\n```\n\n**输出**\n\n```\n{r['messages'][1]['content']}\n```\n\n---\n\n")
from collections import Counter
rep = f"accepted {len(ok)} rejected {len(bad)}\nby outcome: {dict(Counter(r['meta']['outcome_category'] for r in ok))}\nchars: {sorted(r['meta']['approx_chars'] for r in ok)}\n\nWARNINGS\n" + '\n'.join(wl) + '\n\nREJECTED\n' + '\n'.join(f"{r['id']}: {r.get('errors')}" for r in bad)
open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8').write(rep); print(rep)
