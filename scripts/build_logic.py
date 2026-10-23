"""Build Long-CoT logic-reasoning samples from LogiQA 2.0 (zh).
Usage: python3 -I build_logic.py <data_dir>
Checks: example_id exists; my chosen answer == gold answer (rejection sampling); quotes verbatim from the item; reasoning length >= MIN_THINK."""
import sys, os, re, json, glob, runpy
DATA = sys.argv[1]
OUT = os.path.join(DATA, 'out_logic'); os.makedirs(OUT, exist_ok=True)
MIN_THINK = 500
SYSTEM = ("你是一名擅长公务员考试行政职业能力测验（判断推理·逻辑判断）的解题专家。请先充分、逐步地推理——"
          "拆解论证结构、明确题目要求、逐项分析选项、比较相近选项并自我检验——再给出答案。")
rows = {}
for f in ('train_zh.txt', 'dev_zh.txt', 'test_zh.txt'):
    for l in open(os.path.join(DATA, 'ext/logiqa', f), encoding='utf-8'):
        r = json.loads(l); rows[r['example_id']] = (r, f)
QUOTE = re.compile(r'「([^」]+)」')
squash = lambda s: re.sub(r'\s+', '', s)
L = 'ABCD'
def opts(r): return [re.sub(r'^[A-D][\.．、]\s*', '', o).strip() for o in r['options']]
ok, bad = [], []
for f in sorted(glob.glob(os.path.join(DATA, 'annotations_logic/*.py'))):
    for s in runpy.run_path(f)['ANNOTATIONS']:
        errs = []
        if s['example_id'] not in rows: bad.append(dict(id=s['id'], errors=['example_id not found'])); continue
        r, split = rows[s['example_id']]
        gold = L[r['answer']]
        if s['answer'] != gold: errs.append(f'answer mismatch: mine {s["answer"]} gold {gold}')
        o = opts(r)
        user = f"【材料】\n{r['text'].strip()}\n\n【问题】{r['question'].strip()}\n" + '\n'.join(f'{L[i]}. {t}' for i, t in enumerate(o)) + '\n\n请作答。'
        hay = squash(user)
        for q in QUOTE.findall(s['think'] + s['summary']):
            if not all(squash(p) in hay for p in re.split(r'…+', q) if p.strip()): errs.append(f'quote not in item: 「{q[:30]}」')
        if len(s['think']) < MIN_THINK: errs.append(f'think too short: {len(s["think"])}')
        tr = lambda t: QUOTE.sub(lambda m: '“' + m.group(1) + '”', t).strip()
        assistant = f"<think>\n{tr(s['think'])}\n</think>\n答案：{s['answer']}。{tr(s['summary'])}"
        rec = dict(id=s['id'], meta=dict(bucket='general_logic_longcot', topic='国考行测·逻辑判断（反驳/削弱）', source='LogiQA 2.0 (zh)', source_split=split,
                   example_id=s['example_id'], gold_answer=gold, question_type=s['qtype'], think_chars=len(s['think']),
                   verified='模型答案与标准答案一致（拒绝采样）', generator='claude-sonnet-5-5 (Claude Code) — 推理为初稿，须经专家确认', status='待专家确认'),
                   system=SYSTEM, messages=[dict(role='user', content=user), dict(role='assistant', content=assistant)])
        if errs: rec['errors'] = errs; bad.append(rec)
        else: ok.append(rec)
with open(os.path.join(OUT, 'samples_logic.jsonl'), 'w', encoding='utf-8') as fo:
    for r in ok: fo.write(json.dumps(r, ensure_ascii=False) + '\n')
json.dump([dict(system=r['system'], conversations=[{'from': 'human', 'value': r['messages'][0]['content']}, {'from': 'gpt', 'value': r['messages'][1]['content']}]) for r in ok],
          open(os.path.join(OUT, 'train_logic_sharegpt.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
with open(os.path.join(OUT, 'preview.md'), 'w', encoding='utf-8') as fo:
    fo.write('# 逻辑判断 Long-CoT 样本预览\n\n')
    for r in ok:
        m = r['meta']
        fo.write(f"## {r['id']} · LogiQA2.0 id={m['example_id']} · {m['question_type']} · 标准答案 {m['gold_answer']} · 推理 {m['think_chars']} 字\n\n**输入**\n\n```\n{r['messages'][0]['content']}\n```\n\n**输出**\n\n```\n{r['messages'][1]['content']}\n```\n\n---\n\n")
lens = sorted(r['meta']['think_chars'] for r in ok)
rep = f"accepted {len(ok)} rejected {len(bad)}\nthink chars: {lens}\n" + '\n'.join(f"REJ {r['id']}: {r.get('errors')}" for r in bad)
open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8').write(rep); print(rep)
