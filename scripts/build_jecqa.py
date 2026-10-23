"""Build Long-CoT civil-law (contract) samples from JEC-QA items (AGIEval public subsets).
Usage: python3 -I build_jecqa.py <data_dir>
Checks: item exists; my answer == gold label (rejection sampling); quotes verbatim; reasoning length >= MIN_THINK."""
import sys, os, re, json, glob, runpy
DATA = sys.argv[1]
OUT = os.path.join(DATA, 'out_jecqa'); os.makedirs(OUT, exist_ok=True)
MIN_THINK = 450
SYSTEM = ("你是一名擅长国家统一法律职业资格考试（民法·合同法）的解题专家。请先充分、逐步地推理——"
          "梳理案情事实、归纳争点、说明适用规则、逐项分析选项并自我检验——再给出答案。")
rows = {}
for f, t in (('jec-qa-kd.jsonl', 'KD'), ('jec-qa-ca.jsonl', 'CA')):
    for i, l in enumerate(open(os.path.join(DATA, 'ext/jecqa', f), encoding='utf-8')):
        rows[f'{t}#{i}'] = json.loads(l)
QUOTE = re.compile(r'「([^」]+)」')
squash = lambda s: re.sub(r'\s+', '', s)
ok, bad = [], []
for f in sorted(glob.glob(os.path.join(DATA, 'annotations_jecqa/*.py'))):
    for s in runpy.run_path(f)['ANNOTATIONS']:
        errs = []
        r = rows.get(s['item'])
        if r is None: bad.append(dict(id=s['id'], errors=['item not found'])); continue
        gold = r['label'][0] if len(r['label']) == 1 else None
        if gold != s['answer']: errs.append(f'answer mismatch: mine {s["answer"]} gold {r["label"]}')
        opts = [re.sub(r'^\(([A-D])\)\s*', r'\1. ', o).strip() for o in r['options']]
        user = f"【题目】\n{r['question'].strip()}\n" + '\n'.join(opts) + '\n\n请作答。'
        hay = squash(user)
        for q in QUOTE.findall(s['think'] + s['summary']):
            if not all(squash(p) in hay for p in re.split(r'…+', q) if p.strip()): errs.append(f'quote not in item: 「{q[:30]}」')
        if len(s['think']) < MIN_THINK: errs.append(f'think too short: {len(s["think"])}')
        tr = lambda t: QUOTE.sub(lambda m: '“' + m.group(1) + '”', t).strip()
        assistant = f"<think>\n{tr(s['think'])}\n</think>\n答案：{s['answer']}。{tr(s['summary'])}"
        rec = dict(id=s['id'], meta=dict(bucket='general_civil_longcot', topic='民法·合同（违约/合同效力/责任承担）', source='JEC-QA（AGIEval 公开子集）', item=s['item'],
                   gold_answer=gold, topic_tag=s['tag'], think_chars=len(s['think']),
                   verified='模型独立作答，与标准答案一致（拒绝采样）', law_note='题目取自旧司法考试；推理按合同法/民法典中结论一致的规则表述，由模型核对，未经律师审阅',
                   generator='claude-sonnet-5-5 (Claude Code) — 推理为初稿，须经专家确认', status='待专家确认'),
                   system=SYSTEM, messages=[dict(role='user', content=user), dict(role='assistant', content=assistant)])
        if errs: rec['errors'] = errs; bad.append(rec)
        else: ok.append(rec)
with open(os.path.join(OUT, 'samples_jecqa.jsonl'), 'w', encoding='utf-8') as fo:
    for r in ok: fo.write(json.dumps(r, ensure_ascii=False) + '\n')
json.dump([dict(system=r['system'], conversations=[{'from': 'human', 'value': r['messages'][0]['content']}, {'from': 'gpt', 'value': r['messages'][1]['content']}]) for r in ok],
          open(os.path.join(OUT, 'train_jecqa_sharegpt.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
with open(os.path.join(OUT, 'preview.md'), 'w', encoding='utf-8') as fo:
    fo.write('# 民法·合同 Long-CoT 样本预览\n\n')
    for r in ok:
        m = r['meta']
        fo.write(f"## {r['id']} · JEC-QA {m['item']} · {m['topic_tag']} · 标准答案 {m['gold_answer']} · 推理 {m['think_chars']} 字\n\n**输入**\n\n```\n{r['messages'][0]['content']}\n```\n\n**输出**\n\n```\n{r['messages'][1]['content']}\n```\n\n---\n\n")
rep = f"accepted {len(ok)} rejected {len(bad)}\nthink chars: {sorted(r['meta']['think_chars'] for r in ok)}\n" + '\n'.join(f"REJ {r['id']}: {r.get('errors')}" for r in bad)
open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8').write(rep); print(rep)
