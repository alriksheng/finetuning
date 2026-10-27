"""候选意见流水线 第 3 步：多次采样 → 聚类投票 → 生成专家判定表。
Usage: python3 -I make_cand_xlsx.py <inputs.jsonl> <pred.jsonl(含 outputs)> <out.xlsx> [--min-votes 2] [--skip-rules R-BASIC-CONTENT] [--limit N] [--seed 1]
保留：引文逐字出现在输入中、被至少 min-votes 次采样提出的意见；默认排除 R-BASIC-CONTENT（开发集额外意见里该规则 7/7 不成立）。
判定表每行一条候选意见，附该小节原文节选；另写 <out>.json（候选意见完整内容，供判定后自动转样本）。"""
import sys, re, json, difflib, collections, random, argparse
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
ap = argparse.ArgumentParser(); ap.add_argument('inputs'); ap.add_argument('pred'); ap.add_argument('out')
ap.add_argument('--min-votes', type=int, default=2); ap.add_argument('--skip-rules', default='R-BASIC-CONTENT'); ap.add_argument('--limit', type=int, default=0); ap.add_argument('--seed', type=int, default=1)
a = ap.parse_args(); skip = set(filter(None, a.skip_rules.split(',')))
squash = lambda s: re.sub(r'\s+', '', s or '')
bigr = lambda s: collections.Counter(s[i:i + 2] for i in range(len(s) - 1))
def recall(g, p):
    g, p = bigr(squash(g)), bigr(squash(p)); return sum((g & p).values()) / max(1, sum(g.values()))
def qhit(x, y):
    x, y = squash(x), squash(y)
    if not x or not y: return False
    m = difflib.SequenceMatcher(None, x, y, autojunk=False).find_longest_match(0, len(x), 0, len(y)); return m.size >= 10 and m.size >= 0.5 * min(len(x), len(y))
qs = lambda f: [e.get('quote', '') for e in (f.get('evidence') or []) if isinstance(e, dict)]
ft = lambda f: (f.get('problem') or '') + (f.get('suggestion') or '')
def same(f, g):
    if f.get('rule_id') != g.get('rule_id'): return False
    if any(qhit(x, y) for x in qs(f) for y in qs(g)): return True
    return max(recall(ft(f), ft(g)), recall(ft(g), ft(f))) >= 0.35
def parse(t):
    t = (t or '').split('</think>')[-1].strip(); i = t.find('{')
    if i < 0: return None
    try: return json.JSONDecoder().raw_decode(t[i:])[0]
    except Exception: return None
I = {json.loads(l)['id']: json.loads(l) for l in open(a.inputs, encoding='utf-8')}
cands, stat = [], collections.Counter()
for line in open(a.pred, encoding='utf-8'):
    p = json.loads(line); r = I.get(p['id'])
    if not r: continue
    outs = p.get('outputs') or [p.get('output')]; hay = squash(r['prompt']); cl = []
    for si, o in enumerate(outs):
        obj = parse(o)
        for f in (obj or {}).get('findings', []) if isinstance(obj, dict) else []:
            if not isinstance(f, dict): continue
            for c in cl:
                if same(c[0], f): c[1].add(si); c.append(f); break
            else: cl.append([f, {si}])
    stat['小节'] += 1; stat['聚类'] += len(cl)
    if not cl: stat['全部采样无意见的小节'] += 1
    for c in cl:
        votes = len(c[1]); f = max([c[0]] + c[2:], key=lambda f: len(qs(f)))
        if votes < a.min_votes: stat['票数不足'] += 1; continue
        if f.get('rule_id') in skip: stat['规则被排除'] += 1; continue
        if not qs(f) or not all(squash(q) in hay for q in qs(f)): stat['引文非逐字'] += 1; continue
        if f.get('verdict') != '问题': stat['非问题'] += 1; continue
        cands.append(dict(id=p['id'], project=r['project'], path=r['meta']['path'], votes=votes, n=len(outs), finding=f))
stat['候选'] = len(cands)
if a.limit and len(cands) > a.limit:
    random.Random(a.seed).shuffle(cands); cands = cands[:a.limit]
cands.sort(key=lambda c: (c['project'], c['id']))
wb = openpyxl.Workbook(); ws = wb.active; ws.title = '待判定'
ws['A1'] = ('候选意见判定：模型对“专家没有提意见的小节”提出的意见（多次采样中至少 %d 次一致）。请对照右侧原文节选判断这条意见本身是否成立。'
            '成立=报告确有此问题，评审中应当提出；不成立=报告没有此问题或模型理解有误；成立但次要=属实但一般不会写进评审意见；说不清=需要更多材料。'
            '本小节全部候选都不成立时，我们会把这个小节作为“确认无问题”样本。') % a.min_votes
ws.merge_cells('A1:J1'); ws['A1'].alignment = Alignment(wrap_text=True, vertical='top'); ws.row_dimensions[1].height = 60
ws.append(['序号', '样本', '项目', '小节', '规则', '票数', '模型意见', '模型引文', '原文节选（引文前后）', '判定', '备注'])
thin = Side(style='thin', color='BBBBBB')
for c in ws[2]:
    c.font = Font(name='Arial', bold=True, color='FFFFFF'); c.fill = PatternFill('solid', fgColor='1F4E78'); c.alignment = Alignment(wrap_text=True, vertical='center')
for n, c in enumerate(cands, 1):
    f = c['finding']; prompt = I[c['id']]['prompt']; body = prompt.split('【报告段落】')[-1].split('【事实卡】')[0]
    q0 = qs(f)[0]; i = body.find(q0)
    if i < 0:                                   # 空白差异：按去空白位置回溯
        i = 0
    ex = body[max(0, i - 150): i + len(q0) + 250].strip()
    ws.append([n, c['id'], c['project'], c['path'][:40], f.get('rule_id'), f"{c['votes']}/{c['n']}", ft(f), '\n'.join(qs(f)), ex, None, None])
for i, w in enumerate([6, 18, 8, 24, 18, 7, 50, 46, 60, 14, 24]): ws.column_dimensions[openpyxl.utils.get_column_letter(i + 1)].width = w
for row in ws.iter_rows(min_row=3):
    for c_ in row:
        c_.font = Font(name='Arial', size=10); c_.alignment = Alignment(wrap_text=True, vertical='top'); c_.border = Border(top=thin, bottom=thin, left=thin, right=thin)
    row[9].fill = PatternFill('solid', fgColor='FFF2CC')
dv = DataValidation(type='list', formula1='"成立,不成立,成立但次要,说不清"', allow_blank=True); ws.add_data_validation(dv); dv.add(f'J3:J{ws.max_row}')
ws.freeze_panes = 'C3'; wb.save(a.out)
json.dump([dict(c, no=i) for i, c in enumerate(cands, 1)], open(a.out.rsplit('.', 1)[0] + '.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(dict(stat), '→', a.out)
