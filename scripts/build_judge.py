"""意见复核样本（反面 + 正面）构建与核验。
输入：data/judge/neg*.py 里的 NEG（候选意见 + 为什么不采纳）；正面样本由仿写样本（data/out_imit_v2/samples.jsonl）的意见自动生成，取与反面样本同一小节的意见，形成同节对照。
任务：给定小节 + 候选意见 → <think> 核对 + JSON {task:意见复核, verdict:采纳/不采纳/次要不写, reason_type, reason, evidence}。
Usage: python3 -I build_judge.py <data_dir> <neg文件.py ...>   输出 <data_dir>/out_judge/{samples.jsonl,rejected.jsonl,preview.md}
"""
import sys, os, re, json, runpy, collections, yaml
D = sys.argv[1]; FILES = sys.argv[2:]
OUT = os.path.join(D, os.environ.get('JUDGE_OUT', 'out_judge')); os.makedirs(OUT, exist_ok=True)
IMIT = os.path.join(D, os.environ.get('IMIT_SAMPLES', 'out_imit_v2/samples.jsonl'))
squash = lambda s: re.sub(r'\s+', '', s)
RULES = {r['rule_id']: r for r in yaml.safe_load(open(f'{D}/rules/rules.yaml', encoding='utf-8'))}
INP = {r['id']: r for r in map(json.loads, open(f'{D}/cand/cand_inputs.jsonl', encoding='utf-8'))}
IMS = {r['id']: r for r in map(json.loads, open(IMIT, encoding='utf-8'))}
TYPES = {'泛': ('不采纳', '泛泛无针对'), '误': ('不采纳', '理解有误'), '无': ('不采纳', '本小节不需要'), '次': ('次要不写', '成立但次要')}
TASK = ('【任务】判断候选意见是否应采纳。输出 JSON：task（意见复核）、verdict（采纳／不采纳／次要不写）、reason_type（成立／泛泛无针对／理解有误／本小节不需要／成立但次要）、'
        'reason（一句话）、evidence（报告的逐字摘录）。判断标准：意见须指向本小节的具体内容并能据此修改；报告已经写明的内容不得要求补充；与本小节分析对象无关或影响很小的细节不写。')
LAST = {'泛': '候选意见换到其他项目的同类小节也同样适用，没有对应本小节的数字、条款或表格行，修改人无法据此定位应改哪里。',
        '误': '候选意见要求的内容报告里已经有，照此修改只会重复报告已写明的内容。',
        '无': '候选意见所涉信息与本小节要回答的问题没有关系，补充后不影响本小节的判断。',
        '次': '该点即便属实，对成本核定结论、降本判断或预算安排的影响也很小，不值得单列为评审意见。'}
first_sent = lambda s: re.split(r'[。；]', s.strip())[0] + '。'
qshort = lambda rid: first_sent(RULES[rid]['question'].replace('\n', '')) if RULES.get(rid, {}).get('question') else ''
def body_of(prompt): return prompt.split('【报告段落】')[-1].split('【事实卡】')[0]
def mk(src, sid, prompt, system, rid, text, verdict, rtype, think, reason, evq, kind):
    user = prompt.split('【任务】')[0] + f'【候选意见】\n规则：{rid}\n意见：{text}\n\n' + TASK
    label = re.match(r'\s*\[([^\]]+)\]', body_of(prompt)).group(1)
    obj = dict(task='意见复核', verdict=verdict, reason_type=rtype, reason=reason, evidence=[dict(source='报告', loc=label, quote=q) for q in evq])
    asst = f"<think>\n{think}\n</think>\n" + json.dumps(obj, ensure_ascii=False)
    return dict(id=sid, meta=dict(project_id=INP[src]['project'], source_cand=src, rule_id=rid, verdict=verdict, reason_type=rtype, candidate=text, source_kind=kind, task_type='意见复核', synthetic=True, reasoning_author='claude-sonnet-5-5'),
                system=system.replace('【任务类型】小节审核', '【任务类型】意见复核'), messages=[dict(role='user', content=user), dict(role='assistant', content=asst)])
negs = []
for f in FILES: negs += runpy.run_path(f)['NEG']
ok, bad = [], []; neg_src = set(); used_ids = set()
for n in negs:
    errs = []; src = n['src']; base = re.sub(r'_X\d+$', '', src); neg_src.add(src)
    if src != base:                                  # 人造错小节：取仿写样本里已改好的输入
        im = IMS.get('V7_' + src[2:]); prompt = im['messages'][0]['content'] if im else None; system = im['system'] if im else None
    else:
        r = INP.get(src); prompt = r['prompt'] if r else None; system = r['system'] if r else None
    if not prompt: bad.append(dict(id=src, errors=['输入不存在'])); continue
    INP.setdefault(src, INP[base]); body = squash(body_of(prompt)); focus = re.findall(r'（(R-[A-Z0-9-]+|L3-07)）', prompt.split('【审核重点】')[1].split('【任务】')[0])
    t = n['t']; verdict, rtype = TYPES[t]
    if n['rule'] not in focus: errs.append(f"规则 {n['rule']} 不在审核重点")
    for q in n['cq'] + n.get('evq', []):
        if squash(q) not in body: errs.append(f'引文不在小节正文: {q[:30]}')
    if t == '误' and not n.get('evq'): errs.append('理解有误须给出报告里已有内容的引文 evq')
    if '专家' in n['text'] + n['why']: errs.append('含“专家”')
    if len(n['why']) < 25: errs.append('why 过短')
    evq = list(dict.fromkeys(n.get('evq', []) + n['cq'])) if t == '误' else list(n['cq'])
    qs = '；'.join(f'“{q}”' for q in evq[:2])
    think = (f"逐项核对候选意见（{n['rule']}）：{n['text']}\n1. 候选意见涉及的内容：报告写有{qs}。\n2. 规则关注点：{qshort(n['rule'])}\n3. 核对：{n['why']}\n4. {LAST[t]}\n"
             f"结论：{verdict}（{rtype}）。")
    sid = 'J_' + src[2:] + '_N'
    if sid in used_ids: errs.append('id 重复')
    used_ids.add(sid)
    rec = mk(src, sid, prompt, system, n['rule'], n['text'], verdict, rtype, think, first_sent(n['why']), evq, 'judge_neg')
    if errs: rec['errors'] = errs; bad.append(rec)
    else: ok.append(rec)
# 正面：与反面同一小节的仿写意见
npos = 0
for src in sorted(neg_src):
    im = IMS.get('V7_' + src[2:])
    if not im: continue
    prompt, system = im['messages'][0]['content'], im['system']
    obj = json.loads(im['messages'][1]['content'].split('</think>')[1])
    negr = {n['rule'] for n in negs if n['src'] == src}
    fs = sorted(obj['findings'], key=lambda f: f['rule_id'] not in negr)[:1]          # 每节一条正面意见，优先与反面样本同规则（同规则对照）
    for k, f in enumerate(fs):
        text = f['problem'] + f['suggestion']; ev = [e['quote'] for e in f['evidence']][:2]
        if any(squash(q) not in squash(body_of(prompt)) for q in ev): continue
        qs = '；'.join(f'“{q}”' for q in ev)
        think = (f"逐项核对候选意见（{f['rule_id']}）：{text}\n1. 候选意见涉及的内容：报告写有{qs}。\n2. 规则关注点：{qshort(f['rule_id'])}\n"
                 f"3. 核对：候选意见指出的数字和事实可在上述原文中核实，指向具体的表格行或文字，并给出了可以照做的修改方向。\n4. 报告中没有已经回应该问题的说明，该点会影响成本核定结论的可靠性。\n结论：采纳（成立）。")
        rec = mk(src, f"J_{src[2:]}_P{k + 1}", prompt, system, f['rule_id'], text, '采纳', '成立', think, '意见指出的问题可在报告原文中核实，建议具体可行。', ev, 'judge_pos')
        ok.append(rec); npos += 1
with open(f'{OUT}/samples.jsonl', 'w', encoding='utf-8') as fo:
    for r in ok: fo.write(json.dumps(r, ensure_ascii=False) + '\n')
with open(f'{OUT}/rejected.jsonl', 'w', encoding='utf-8') as fo:
    for r in bad: fo.write(json.dumps(r, ensure_ascii=False) + '\n')
with open(f'{OUT}/preview.md', 'w', encoding='utf-8') as fo:
    for r in ok: fo.write(f"## {r['id']} · {r['meta']['verdict']}/{r['meta']['reason_type']}\n\n候选：{r['meta']['candidate']}\n\n```\n{r['messages'][1]['content']}\n```\n\n")
c = collections.Counter((r['meta']['verdict'], r['meta']['reason_type']) for r in ok)
print(f'通过 {len(ok)}（反面 {len(ok) - npos}，正面 {npos}），被拒 {len(bad)}；{dict(c)}')
for r in bad: print(' ✗', r.get('id'), r.get('errors'))
