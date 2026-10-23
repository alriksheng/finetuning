"""报告切分（方案 v4 第四章“0. 解析与切分”）：识别目录、摘要、正文，按“一、/（一）/1.”切成小节，超长的继续往下切。
Usage: section_report.py <report.md> <out.json> [limit_chars]
输出每个小节：id、标题路径、行号范围（1 起、含两端）、字数、类型 kind、是否摘要。
kind 用于“章节 / 比对包 → 条文”对应表（data/specs/clause_map.yaml）。"""
import sys, re, json

SRC, OUT = sys.argv[1], sys.argv[2]
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 3500
lines = open(SRC, encoding='utf-8').read().split('\n')
CN = '一二三四五六七八九十'
H1 = re.compile(r'^\s*([一二三四五六七八九十]{1,2})、\s*(\S.{0,40})$')
H2 = re.compile(r'^\s*[（(]([一二三四五六七八九十]{1,2})[）)]\s*(\S.{0,40})$')
H3 = re.compile(r'^\s*(\d{1,2})[\.．、]\s*(\S.{0,40})$')
TOC = re.compile(r'(\t\s*\d+\s*-?\s*$)|(\.{4,})|(…{2,})')


def level(s):
    if TOC.search(s) or s.startswith('|') or s.endswith('。') or s.endswith('；'): return None
    for lv, pat in ((1, H1), (2, H2), (3, H3)):
        m = pat.match(s)
        if m: return lv, m.group(1), m.group(2).strip()
    return None


heads = [(i, *lv) for i, s in enumerate(lines) if (lv := level(re.sub(r'^#+\s*', '', s.strip())))]   # Word 标题样式转换后带“#”前缀
MDH = re.compile(r'^(#{1,3})\s+(\S.{0,40})$')
MD_MODE = not any(h[1] == 1 for h in heads)          # 无“一、”编号时（如简易报告），按 Word 标题样式“#”的级数切分
HEAD_MODE = '编号'
if MD_MODE and any(h[1] == 2 for h in heads):        # 只有“（一）”二级编号（如部分简易报告）：升为一级
    heads = [(i, lv - 1, c, t) for i, lv, c, t in heads if lv >= 2]; MD_MODE = False; HEAD_MODE = '二级编号升级'
if MD_MODE:
    heads = [(i, len(m.group(1)), str(k), m.group(2).strip()) for k, (i, m) in enumerate((i, MDH.match(s.strip())) for i, s in enumerate(lines)) if m]
    HEAD_MODE = '标题样式'
MAJOR = re.compile(r'^(报告摘要|基本情况|政策基本情况|绩效分析工作情况|成本预算绩效分析|公共服务标准绩效分析|政策成本预算绩效分析|分析结论|存在问题及建议|存在的问题及建议|其他需要说明的情况|附件)')
MINOR = re.compile(r'实施背景|实施内容|资金|预算|业务管理|绩效基线|绩效目标|业务流程|流程|成本核算|成本标准|降本|增效|问题|建议|三个标准|支出标准|分析思路|分析方法|分析过程|投入方向|投入方式|支持标准|管理机制|分担')
if MD_MODE and not heads:                            # 标题无编号、无样式：短行且命中模板章节名
    for i, raw in enumerate(lines):
        t = raw.strip()
        if not t or len(t) > 24 or t.startswith('|') or re.search(r'[。；，：:、\t]|\d{1,3}$', t): continue
        if MAJOR.match(t): heads.append((i, 1, str(i), t))
        elif MINOR.search(t) and heads: heads.append((i, 2, str(i), t))
    HEAD_MODE = '无编号短行'
# 一级标题编号回退（如“五、”之后又出现“一、”或“二、”）即视为新的一块；按模板章节命中数打分：
# 得分最高（并列取篇幅最长）的是正文，正文前一块是摘要，正文之后的是附件（如政策原文）
num = lambda c: (CN.index(c[0]) + 1) * (10 if len(c) == 2 and c[1] == '十' else 1) if c[0] in CN else 99
TPL = re.compile(r'基本情况|工作开展|工作情况|成本预算绩效分析|分析结论|存在问题|其他需要说明')
blocks, prev = [], 99
for h in ([] if MD_MODE else heads):
    if h[1] == 1 and num(h[2]) <= prev: blocks.append([])
    if blocks: blocks[-1].append(h)
    if h[1] == 1: prev = num(h[2])
score = lambda b: sum(1 for h in b if h[1] == 1 and TPL.search(h[3]))
bi = max(range(len(blocks)), key=lambda k: (score(blocks[k]), blocks[k][-1][0] - blocks[k][0][0])) if blocks else 0
body = blocks[bi] if blocks else heads                            # 标题样式模式下全部作为正文
summary = blocks[bi - 1] if bi >= 1 and score(blocks[bi - 1]) >= 2 else []
annex = [h for b in blocks[bi + 1:] for h in b]
end_of = lambda hs, k, lv, last: next((hs[j][0] for j in range(k + 1, len(hs)) if hs[j][1] <= lv), last)


def kind_of(t1, t2, t3, policy):
    t = t1 + '|' + t2 + '|' + t3
    rules = [('其他需要说明|附件', 'other'), ('工作开展|工作情况|分析目的|分析思路|分析方法|分析过程', 'work'),
             ('存在问题|有关建议', 'issue'), ('分析结论|降本情况|增效情况|资金安排建议|政策制定的建议|政策投入的建议|实施管理的建议|预期效果', 'concl')]
    if policy:
        rules += [('投入方向', 'pol_dir'), ('投入方式', 'pol_method'), ('支持标准|投入规模|比较研究|支持力度|投入经济', 'pol_std'),
                  ('分担', 'pol_share'), ('管理机制', 'pol_mgmt'), ('绩效基线|绩效目标|绩效表现|基线对标|实施效果', 'pol_perf'), ('基本情况|政策背景|政策内容|组织实施|预算资金|实施和完成', 'pol_basic')]
    else:
        rules += [('业务流程|流程解析|流程改进|流程优化', 'proc'), ('成本核算|成本梳理|成本标准|成本要素', 'cost'),
                  ('绩效基线|关键绩效指标|绩效指标|绩效目标', 'perf'), ('基本情况|实施背景|实施内容|资金安排|业务管理', 'basic')]
    for pat, k in rules:
        if re.search(pat, t2 + '|' + t3) or (not t2 and not t3 and re.search(pat, t1)): return k
    for pat, k in rules:
        if re.search(pat, t1): return k
    return 'other'


policy = sum('政策' in h[3] for h in body if h[1] == 1) >= 2
units = []


def emit(a, b, path, kind, abstract):
    """a、b 为行下标（含 a，不含 b）。超长时先按下一级标题切，再按段落切。"""
    text = '\n'.join(lines[a:b]); n = len(''.join(text.split()))
    if n <= LIMIT or b - a <= 1:
        units.append(dict(id=f"{'A' if abstract else 'S'}{len(units) + 1:03d}", path=' > '.join(p for p in path if p),
                          lines=[a + 1, b], chars=n, kind=('abs_' if abstract else '') + kind, abstract=abstract)); return
    subs = [h for h in heads if a < h[0] < b and h[1] == 3]
    if subs:
        if subs[0][0] > a + 1: emit(a, subs[0][0], path + ['（引言）'], kind, abstract)
        for k, h in enumerate(subs):
            emit(h[0], subs[k + 1][0] if k + 1 < len(subs) else b, path + [h[3]], kind, abstract)
        return
    cur, size = a, 0                                                   # 按段落切，表格整体不拆开
    for i in range(a, b):
        size += len(''.join(lines[i].split()))
        nxt_tbl = i + 1 < b and lines[i + 1].startswith('|') and lines[i].startswith('|')
        if size > LIMIT and not nxt_tbl and i > cur:
            units.append(dict(id=f"{'A' if abstract else 'S'}{len(units) + 1:03d}", path=' > '.join(path) + f'（第{len([u for u in units if u["abstract"] == abstract and u["path"].startswith(" > ".join(path))]) + 1}段）',
                              lines=[cur + 1, i + 1], chars=size, kind=('abs_' if abstract else '') + kind, abstract=abstract, split='按段'))
            cur, size = i + 1, 0
    if cur < b: emit(cur, b, path + ['（续）'], kind, abstract)


annex_start = annex[0][0] if annex else len(lines)
for hs, abstract in ((summary, True), (body, False)):
    last = (body[0][0] if abstract and body else annex_start)
    for k, h in enumerate(hs):
        if h[1] != 1: continue
        e1 = end_of(hs, k, 1, last)
        l2 = [(j, x) for j, x in enumerate(hs) if h[0] < x[0] < e1 and x[1] == 2]
        if not l2:
            t3s = [x[3] for x in hs if h[0] < x[0] < e1 and x[1] == 3]
            emit(h[0], e1, [h[3]], kind_of(h[3], '', '|'.join(t3s), policy), abstract); continue
        if l2[0][1][0] > h[0] + 1: emit(h[0], l2[0][1][0], [h[3], '（引言）'], kind_of(h[3], '', '', policy), abstract)
        for n, (j, x) in enumerate(l2):
            e2 = l2[n + 1][1][0] if n + 1 < len(l2) else e1
            emit(x[0], e2, [h[3], x[3]], kind_of(h[3], x[3], '', policy), abstract)

if annex_start < len(lines): units.append(dict(id=f'X{len(units) + 1:03d}', path='附件（正文之后）', lines=[annex_start + 1, len(lines)], chars=len(''.join(''.join(lines[annex_start:]).split())), kind='annex', abstract=False))
json.dump(dict(source=SRC, heading_mode=HEAD_MODE, policy=policy, limit=LIMIT, units=units), open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
from collections import Counter
print(f"{SRC}: {'政策' if policy else '项目'}；小节 {len(units)}（摘要 {sum(u['abstract'] for u in units)}）；最长 {max([u['chars'] for u in units] or [0])} 字；类型 {dict(Counter(u['kind'] for u in units))}")
