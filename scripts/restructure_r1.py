"""样本结构重构 R1：由现有训练和评测文件派生实验组，现有文件不动，作对照组。

输入（报告段落、事实卡、条文、审核重点、任务）一字不改，只改两处：
1. 思考的结构：通读 → 逐项检查审核重点 → 逐条意见（证据甄别 → 引文 → 分析 → 规则 → 结论）。
   - 逐项检查：意见用到的规则写“提出意见（要点X）”，其余写“本次不提出意见”。不写“符合”，
     因为专家没提不等于没有问题。
   - 证据甄别：在引文所在段落中，列出引文所在句和前后各 2 句；非引文句写“不作本问题依据”，只摘前 15 字。
   - 分析：沿用原思考的内容。能按“要点N”对应到意见的放在该意见下；对应不上的放进“综合分析”。
2. JSON 字段顺序：evidence、problem、rule_id 在前，suggestion 在后。字段的值不变。
系统提示只改“输出顺序”的说明。事实卡抽取、漏项清单等没有 findings 的样本原样保留。

用法：python3 -I scripts/restructure_r1.py data
输出：data/train/audit_{train,dev,test}_r1_think.json、data/eval/audit_{dev,test}_r1.jsonl、
     data/train/dataset_info_r1.json（新增条目，云端合并进 dataset_info.json）、data/train/r1_report.txt。
"""
import json, re, sys, statistics
from pathlib import Path

CN = '一二三四五六七八九十'
KEY_ORDER = ('evidence', 'problem', 'rule_id', 'issue_type', 'verdict', 'clause_ids', 'basis_type', 'suggestion', 'part')
OLD_SYS = '先在思考中逐字摘录相关证据、核对条文并标注条文编号；'
NEW_SYS = ('先在思考中按以下顺序进行：通读本小节；对【审核重点】逐项写出是否提出意见；对每条意见，先在证据所在段落中甄别句子、'
           '逐字摘录引文，再分析问题、核对条文并标注条文编号，最后确定规则编号。')
OLD_FIELDS = 'findings 中每条包含 issue_type、rule_id、verdict'
NEW_FIELDS = 'findings 中每条按以下顺序包含 evidence、problem、rule_id、issue_type、verdict、clause_ids、basis_type、suggestion、part；其中 verdict'
SENT_RE = re.compile(r'[^。；！？]*[。；！？]?')
squash = lambda s: re.sub(r'\s+', '', s)


def cn(i):
    return CN[i] if i < 10 else str(i + 1)


def split_answer(a):
    m = re.match(r'\s*<think>(.*?)</think>\s*(.*)', a, re.S)
    return (m.group(1).strip(), m.group(2).strip()) if m else (None, a)


def focus_items(prompt):
    m = re.search(r'【审核重点】(.*?)\n', prompt)
    if not m:
        return []
    return [(t.strip(), i) for t, i in re.findall(r'([^；（(]+)[（(]([A-Z][A-Z0-9\-]*)[）)]', m.group(1))]


MAX_SCREEN = 3                                       # 每条意见最多列出的非引文句


def screen(quotes, prompt):
    """同一条意见的全部引文，按所在段落合并；每段列出紧邻引文的非引文句（前后各 1 句，表格行不列）。"""
    lines = prompt.split('\n')
    groups = {}
    for q in map(squash, quotes):
        for li, line in enumerate(lines):
            if q and q in squash(line):
                groups.setdefault(li, []).append(q)
                break
    out, listed = [], 0
    for li, qs in groups.items():
        sents = [s for s in SENT_RE.findall(lines[li]) if s.strip()]
        hit = sorted({i for i, s in enumerate(sents) for q in qs
                      if squash(s) and (squash(s) in q or q in squash(s) or (len(squash(s)) >= 8 and squash(s)[:8] in q))})
        if not hit or len(sents) < 3:
            continue
        near = [i for i in sorted({j for h in hit for j in (h - 1, h + 1)})
                if 0 <= i < len(sents) and i not in hit and '|' not in sents[i] and 10 <= len(squash(sents[i])) <= 150 and ']' not in sents[i] and '[' not in sents[i]]
        near = near[:MAX_SCREEN - listed]
        if not near:
            continue
        out.append(f'所在段落共 {len(sents)} 句，引文在第 {"、".join(str(i + 1) for i in hit)} 句。')
        for i in near:
            out.append(f'第 {i + 1} 句「{sents[i].strip()[:15]}」…：不作本问题依据。')
        listed += len(near)
        if listed >= MAX_SCREEN:
            break
    return out


def restructure(prompt, think, ans):
    findings = ans['findings']
    lines = [l.strip() for l in think.split('\n') if l.strip()]
    first = lines[0] if lines and re.match(r'(定位|比对)[:：]', lines[0]) else None
    body = lines[1:] if first else lines
    concl = [l for l in body if l.startswith('结论')]
    body = [l for l in body if not l.startswith('结论')]
    n = len(findings)
    per, shared = {i: [] for i in range(n)}, []
    for l in body:
        ks = sorted({CN.index(k) for k in re.findall(r'要点([一二三四五六七八九十])', l) if CN.index(k) < n})
        if n == 1:
            per[0].append(l)
        elif len(ks) == 1:
            per[ks[0]].append(l)
        else:
            shared.append(l)
    mapped = n == 1 or all(per[i] for i in range(n))
    if not mapped:                                    # 对应不上的，整体放进综合分析
        shared = body
        per = {i: [] for i in range(n)}

    out = []
    if first:
        out.append('一、通读\n' + re.sub(r'^(定位|比对)[:：]', '', first))
    rule_pts = {}
    for i, f in enumerate(findings):
        rule_pts.setdefault(f.get('rule_id'), []).append(i)
    chk = []
    for tag, rid in focus_items(prompt):
        pts = rule_pts.get(rid)
        chk.append(f'- {tag}（{rid}）：' + (f'提出意见（{"、".join("要点" + cn(i) for i in pts)}）' if pts else '本次不提出意见'))
    extra = [r for r in rule_pts if r not in {rid for _, rid in focus_items(prompt)}]
    for r in extra:
        chk.append(f'- {r}：提出意见（{"、".join("要点" + cn(i) for i in rule_pts[r])}）')
    if chk:
        out.append('二、逐项检查审核重点\n' + '\n'.join(chk))
    sec = '三' if chk else '二'
    blocks = []
    for i, f in enumerate(findings):
        qs = [e.get('quote', '') for e in f.get('evidence') or [] if isinstance(e, dict) and e.get('quote')]
        b = [f'要点{cn(i)}（{f.get("issue_type", "")}）']
        scr = screen(qs, prompt)
        if scr:
            b.append('证据甄别：' + '\n'.join(scr))
        if qs:
            b.append('引文：' + '；'.join(f'「{q}」' for q in qs))
        if per[i]:
            b.append('分析：' + '\n'.join(per[i]))
        elif not mapped:
            b.append('分析：见综合分析。')
        b.append(f'规则：{f.get("rule_id")}；判断：{f.get("verdict")}。')
        blocks.append('\n'.join(b))
    out.append(f'{sec}、逐条意见\n' + '\n\n'.join(blocks))
    if shared:
        out.append(('综合分析\n' if not mapped else '共同依据\n') + '\n'.join(shared))
    if concl:
        out.append('\n'.join(concl))
    new_ans = dict(ans)
    new_ans['findings'] = [{k: f[k] for k in KEY_ORDER if k in f} | {k: v for k, v in f.items() if k not in KEY_ORDER}
                           for f in findings]
    return '\n\n'.join(out), new_ans, mapped


def check(prompt, think):
    """思考中的「引文」都要逐字出现在输入中（与 build.py 的规则一致，“…”连接的分段分别核对）。"""
    hay = squash(prompt)
    bad = []
    for q in re.findall(r'「(.*?)」', think, re.S):
        for seg in q.split('…'):
            if squash(seg) and squash(seg) not in hay:
                bad.append(seg)
    return bad


def convert(system, prompt, answer, stats):
    think, rest = split_answer(answer)
    try:
        ans = json.loads(rest)
        assert think is not None and isinstance(ans.get('findings'), list) and ans['findings']
    except Exception:
        stats['kept'] += 1
        return system, answer
    new_think, new_ans, mapped = restructure(prompt, think, ans)
    bad_old = set(check(prompt, think))
    bad = [b for b in check(prompt, new_think) if b not in bad_old]
    if bad:
        raise SystemExit(f'新思考中的引文不在输入中：{bad[:3]}')
    stats['ok'] += 1
    stats['mapped'] += mapped
    stats['multi'] += len(ans['findings']) > 1
    stats['screened'] += '证据甄别' in new_think
    stats['len_old'].append(len(think))
    stats['len_new'].append(len(new_think))
    # 意见的值必须一字不变
    assert [sorted(f.items(), key=str) for f in ans['findings']] == [sorted(f.items(), key=str) for f in new_ans['findings']]
    new_sys = system.replace(OLD_SYS, NEW_SYS).replace(OLD_FIELDS, NEW_FIELDS)
    assert new_sys != system, '系统提示未替换'
    return new_sys, f'<think>\n{new_think}\n</think>\n\n' + json.dumps(new_ans, ensure_ascii=False)


def main(root):
    root = Path(root)
    tr, ev = root / 'train', root / 'eval'
    report = []
    base = json.loads((tr / 'dataset_info.json').read_text())
    info = {}                                         # 只写新增条目；云端合并，不覆盖云端的 dataset_info.json
    for split in ('train', 'dev', 'test'):
        src = tr / f'audit_{split}_think.json'
        rows = json.loads(src.read_text())
        st = dict(ok=0, kept=0, mapped=0, multi=0, screened=0, len_old=[], len_new=[])
        out = []
        for x in rows:
            c = x['conversations']
            s, a = convert(x['system'], c[0]['value'], c[1]['value'], st)
            out.append(dict(x, system=s, conversations=[c[0], dict(c[1], value=a)]))
        name = f'audit_{split}_r1_think'
        (tr / f'{name}.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
        info[name] = dict(base[f'audit_{split}_think'], file_name=f'{name}.json')
        report.append(f'{split}: 共 {len(rows)} 行，重构 {st["ok"]}，原样保留 {st["kept"]}；多要点 {st["multi"]}，'
                      f'分析能按要点对应 {st["mapped"]}（含单要点），带证据甄别 {st["screened"]}；'
                      f'思考字数 原 {statistics.mean(st["len_old"]):.0f} → 新 {statistics.mean(st["len_new"]):.0f}'
                      f'（新最大 {max(st["len_new"])}）')
    for split in ('dev', 'test'):
        st = dict(ok=0, kept=0, mapped=0, multi=0, screened=0, len_old=[], len_new=[])
        out = []
        for l in (ev / f'audit_{split}.jsonl').read_text().splitlines():
            r = json.loads(l)
            s, g = convert(r['system'], r['prompt'], r['gold'], st)
            out.append(json.dumps(dict(r, system=s, gold=g), ensure_ascii=False))
        (ev / f'audit_{split}_r1.jsonl').write_text('\n'.join(out) + '\n')
        report.append(f'eval {split}: 重构 {st["ok"]}，原样保留 {st["kept"]}（输入 prompt 与对照组相同，只换系统提示）')
    (tr / 'dataset_info_r1.json').write_text(json.dumps(info, ensure_ascii=False, indent=1))
    (tr / 'r1_report.txt').write_text('\n'.join(report) + '\n')
    print('\n'.join(report))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'data')
