"""反事实样本：改掉报告中的一处问题，答案相应变成“无问题”（findings 为空）。
Usage: python3 -I build_fix.py <data_dir>
读 data/fix/*.py 的 FIXES，每条：id、base（out/samples.jsonl 中只含 1 条意见的小节审核样本）、edits=[(原文, 改为)]（只改【报告段落】，原文须唯一出现）、think（用「…」逐字引用改后输入）。
检查：底稿存在且只含 1 条意见；改动锚点唯一；think 中的引文逐字出现在改后输入；改动新增的数字（≥2 位）必须已在输入的其他位置出现（不得凭空编造数据）；不引用输入之外的条文、表号、页码；think 不把“专家”当作来源。
输出 out_fix/samples_fix.jsonl、preview.md、report.txt。meta.source_kind = synthetic_fix（计入合成样本上限）。"""
import sys, os, re, json, glob, runpy
DATA = sys.argv[1]
OUT = os.path.join(DATA, 'out_fix'); os.makedirs(OUT, exist_ok=True)
HERE = os.path.dirname(os.path.abspath(__file__))
CHK = runpy.run_path(os.path.join(HERE, 'checks.py')); check_arith = CHK['check_arith']
squash = lambda s: re.sub(r'\s+', '', s)
QUOTE = re.compile(r'「([^」]+)」')
ID_RE = re.compile(r'\b(P\d+(?:-[A-Za-z0-9]+)+)\b')
ENT_REF = re.compile(r'(?<![代图])表\s?\d+(?:[-－—]\d+)*|附件\s?\d+|第\s?\d+\s?页')
SRC_EXPERT = re.compile(r'专家')
NUMRE = re.compile(r'\d[\d,\.]*\d|\d')
tr = lambda s: QUOTE.sub(lambda m: '“' + m.group(1) + '”', s).strip()
MIN_THINK = 300
base = {}
for l in open(os.path.join(DATA, 'out/samples.jsonl'), encoding='utf-8'):
    r = json.loads(l); base[r['id']] = r
ok, bad = [], []
for f in sorted(glob.glob(os.path.join(DATA, 'fix/*.py'))):
    for s in runpy.run_path(f)['FIXES']:
        errs, b = [], base.get(s['base'])
        if b is None: bad.append(dict(id=s['id'], errors=['base not found'])); continue
        ans = json.loads(b['messages'][1]['content'].split('</think>')[-1])
        if b['meta']['task_type'] != '小节审核' or len(ans['findings']) != 1: errs.append('base must be a 小节审核 sample with exactly 1 finding')
        user = b['messages'][0]['content']
        head, rest = user.split('\n\n【事实卡】', 1)
        new_head, added = head, []
        for old, new in s['edits']:
            if new_head.count(old) != 1: errs.append(f'edit anchor not unique/found: {old[:24]}'); continue
            new_head = new_head.replace(old, new, 1); added.append(new)
        new_user = new_head + '\n\n【事实卡】' + rest
        hay, old_hay = squash(new_user), squash(user)
        for q in QUOTE.findall(s['think']):
            if not all(squash(x) in hay for x in re.split(r'…+', q) if x.strip()): errs.append(f'quote not in input: 「{q[:30]}」')
        flat_old = re.sub(r'[\s,]', '', user)
        for n in NUMRE.findall(''.join(added)):
            q = n.replace(',', '')
            if len(q.replace('.', '')) >= 2 and q not in flat_old and not re.fullmatch(r'(19|20)\d\d', q): errs.append(f'edit adds number not in input: {n}')
        mapped = set(b['meta']['mapped_clause_ids'])
        for i in set(ID_RE.findall(s['think'])):
            if i not in mapped: errs.append(f'cited {i} not in input')
        for e_ in set(ENT_REF.findall(s['think'])):
            if squash(e_) not in hay: errs.append(f'think cites {e_} not in input')
        if SRC_EXPERT.search(s['think']): errs.append('think mentions 专家')
        if len(s['think']) < MIN_THINK: errs.append(f'think too short: {len(s["think"])}')
        e_ar, _ = check_arith(s['think'], new_user)
        errs += [f'think {e}' for e in e_ar]
        js = json.dumps(dict(task='小节审核', findings=[]), ensure_ascii=False)
        meta = dict(b['meta']); meta.update(sample_type='无问题', source_kind='synthetic_fix', synthetic=True, base_sample=b['id'], rule_ids=[], clause_ids=[], evidence=[],
                    evidence_count=0, unreachable_evidence=[], unreachable_count=0, expert_text=None, text_sources=[], opinion_text='', opinion_tags=[], basis=[], members=None, member_types=None,
                    member_source_kinds=None, target_type='none', reachability='无问题', reasoning_author='claude-sonnet-5-5', status='合成，待专家抽查', notes=s.get('note'), history=None, fix_edits=[list(e) for e in s['edits']])
        rec = dict(id=s['id'], meta=meta, system=b['system'], messages=[dict(role='user', content=new_user), dict(role='assistant', content=f"<think>\n{tr(s['think'])}\n</think>\n{js}")])
        if errs: rec['errors'] = errs; bad.append(rec)
        else: ok.append(rec)
with open(os.path.join(OUT, 'samples_fix.jsonl'), 'w', encoding='utf-8') as fo:
    for r in ok: fo.write(json.dumps(r, ensure_ascii=False) + '\n')
with open(os.path.join(OUT, 'preview.md'), 'w', encoding='utf-8') as fo:
    fo.write('# 反事实（改掉一处问题）样本预览\n\n')
    for r in ok:
        m = r['meta']
        fo.write(f"## {r['id']} ← {m['base_sample']} · {m['project_id']} · {m['input_scope']}\n\n**改动**\n\n" + '\n'.join(f"- 原：{o}\n  改：{n}" for o, n in m['fix_edits']) + f"\n\n**输出**\n\n```\n{r['messages'][1]['content']}\n```\n\n---\n\n")
rep = f"accepted {len(ok)} rejected {len(bad)}\n" + '\n'.join(f"REJ {r['id']}: {r.get('errors')}" for r in bad)
open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8').write(rep); print(rep)
