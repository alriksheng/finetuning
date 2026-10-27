"""项目级事实卡（设计见 项目级事实卡设计.md）：L0 报告结构索引 + L1 摘要节选。纯程序、逐字摘录，不看专家意见。
库用法：  from fact_card import FactCards;  fc = FactCards(data_dir);  text, info = fc.card(pid, secs)   # secs=[(lines列表, kind), ...]，比对包传两项
命令行：  python3 -I fact_card.py <data_dir> stats      统计已标注小节和候选小节的卡长度、L1 为空比例、预计 token 增量
         python3 -I fact_card.py <data_dir> show P003 S025   打印某项目某小节的卡"""
import sys, os, re, json, glob, runpy, collections, statistics
CAP_UNIT, CAP_L1, CAP_L0 = 450, 900, 320             # 单个摘要小节字数上限、L1 总上限、L0 上限（字）；整张卡平均约 1000 字（约 650 token）
# 当前小节类型 → 取哪些摘要小节：按路径关键词的优先级各取一个（依据：各类小节对应的规则需要的跨小节信息，设计文档第 4 节）；与当前小节同路径的摘要不取（内容重复）
L1_PICK = {
    'basic': ['降本情况', '资金安排', '成本核算'], 'work': ['实施内容', '资金安排', '成本核算'], 'perf': ['实施内容', '资金安排', '成本核算'],
    'proc': ['实施内容', '业务管理', '成本核算'], 'cost': ['实施内容', '资金安排', '降本情况'], 'ana': ['实施内容', '资金安排', '降本情况'],
    'concl': ['资金安排', '实施内容', '成本核算'], 'issue': ['业务流程', '降本情况', '实施内容'], 'other': ['实施内容', '资金安排'],
}
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fact_card_exist import detect
norm = lambda s: re.sub(r'\s+', ' ', s).strip()
# 存在性标志（L2 初版，设计文档 12.6）：只保留检验可靠的 E1、E2、E7，按当前小节类型决定放哪些
FLAGS = {'concl': ['E1', 'E2'], 'issue': ['E1', 'E2'], 'basic': ['E7']}
FLAG_NAME = {'E1': '后续年度预算安排（具体年度和金额）', 'E2': '分析结果应用于预算调整或绩效目标申报', 'E7': '近年预决算表'}


def cut(t, cap):
    """截到 cap 字以内，尽量在句号处断开，不拆数字。"""
    if len(t) <= cap: return t
    k = t.rfind('。', 0, cap)
    return t[:k + 1] if k > cap * 0.5 else t[:cap].rstrip('，；、 ') + '…'


class FactCards:
    def __init__(self, data_dir):
        self.D = data_dir; self._c = {}

    def project(self, pid):
        if pid not in self._c:
            sj = f'{self.D}/specs/sections/{pid}.json'; md = f'{self.D}/raw/reports/{pid}.md'
            if not (os.path.exists(sj) and os.path.exists(md)): self._c[pid] = None
            else: self._c[pid] = (json.load(open(sj, encoding='utf-8'))['units'], open(md, encoding='utf-8').read().split('\n'))
        return self._c[pid]

    @staticmethod
    def _base(kind):
        return kind[4:] if kind.startswith('abs_') else kind

    def _l0(self, units, cur):
        """结构索引：摘要只列一级标题；正文列到二级，只在最深一层标“◀当前”。超长时正文降为一级。"""
        def paths(us):
            for u in us:
                yield [re.sub(r'（第\d+段）$', '', x.strip()).strip('（）') for x in u['path'].split('>')][:2], u['id'] in cur
        def render(us, depth):
            t = collections.OrderedDict()
            for p, is_cur in paths(us):
                p = [x for x in p if x and len(x) <= 24 and not re.search(r'[。”“]', x)] or p[:1]                      # 过滤切分时误当标题的整句
                node = t.setdefault(p[0], collections.OrderedDict())
                if depth == 2 and len(p) > 1: node.setdefault(p[1], False); node[p[1]] = node[p[1]] or is_cur
                if is_cur and (depth == 1 or len(p) == 1): node['◀'] = True
            out = []
            for k, v in t.items():
                kids = [x + ('◀当前' if c else '') for x, c in v.items() if x != '◀']
                out.append(k + ('◀当前' if v.get('◀') else '') + (f"（{'、'.join(kids)}）" if kids else ''))
            return '、'.join(out)
        ab = [u for u in units if u.get('abstract')]; bd = [u for u in units if not u.get('abstract') and u['kind'] != 'annex']
        for depth in (2, 1):
            s = ('摘要：' + render(ab, 1) + '；' if ab else '') + '正文：' + render(bd, depth)
            if len(s) <= CAP_L0: return s
        return s[:CAP_L0]

    def card(self, pid, secs):
        """secs=[(lines, kind), ...]：当前小节（一个或两个）的行范围（[(a,b),...]）和 kind。返回 (文本, 信息)。"""
        pr = self.project(pid)
        if pr is None: return None, dict(skip='无切分或非 md')
        units, lines = pr
        cur_lines = set(); kinds = []
        for ls, kind in secs:
            for a, b in ls: cur_lines.update(range(a, b + 1))
            kinds.append(self._base(kind))
        cur = {u['id'] for u in units if set(range(u['lines'][0], u['lines'][1] + 1)) & cur_lines}
        cur_paths = {re.sub(r'（第\d+段）$', '', u['path']) for u in units if u['id'] in cur}
        has_abs = any(u.get('abstract') for u in units)
        pats = []
        for k in kinds:
            for w in L1_PICK.get(k, ['实施内容']):
                if w not in pats: pats.append(w)
        picked, used, seen = [], 0, set()
        for w in pats:
            for u in units:
                if not u.get('abstract') or u['id'] in cur or u['id'] in seen or w not in u['path']: continue
                if re.sub(r'（第\d+段）$', '', u['path']) in cur_paths: continue
                t = cut(norm('\n'.join(lines[u['lines'][0] - 1:u['lines'][1]])), CAP_UNIT)
                if used + len(t) > CAP_L1: continue
                picked.append((u, t)); used += len(t); seen.add(u['id']); break
        out = ['[报告结构] ' + self._l0(units, cur)]
        if not has_abs: out.append('[摘要] 本报告没有摘要。')
        else:
            for u, t in picked: out.append(f"[摘要·{'·'.join(x.strip() for x in u['path'].split('>'))}] {t}")
        want_flags = []
        for k in kinds:
            for e in FLAGS.get(k, []):
                if e not in want_flags: want_flags.append(e)
        if want_flags:
            det = detect(units, lines, cur_lines)
            for e in want_flags:
                hits = det[e]; strong = [h for h in hits if h[1].startswith('S|')]
                if strong: res = f"其他小节已给出（{strong[0][0].replace(' > ', '·')[:36]}）"
                elif hits: res = f"其他小节仅有泛指（{hits[0][0].replace(' > ', '·')[:36]}）"
                else: res = '其他小节未检索到'
                out.append(f'[存在性] {FLAG_NAME[e]}：{res}')
        info = dict(l1_units=len(picked), l1_chars=used, has_abs=has_abs, chars=sum(len(x) for x in out), flags=len(want_flags))
        return '\n'.join(out), info


def iter_targets(D):
    """已标注小节（specs 里的 SAMPLES）和候选小节（data/cand/cand_inputs.jsonl）。"""
    import yaml
    split = {p: v['split'] for g in [yaml.safe_load(open(f'{D}/splits.yaml', encoding='utf-8'))['groups']] for k, v in g.items() for p in v['projects']}
    for f in sorted(glob.glob(f'{D}/specs/P*.py')):
        sp = runpy.run_path(f); pid = sp['SOURCE']; S, PK = sp['SECTIONS'], sp['PACKS']
        for s in sp['SAMPLES']:
            u = s['unit']; ids = [PK[u]['a'], PK[u]['b']] if u in PK else [u]
            if any('lines' not in S[i] for i in ids): continue
            yield 'labeled', pid, split.get(pid), s.get('id') or u, [(S[i]['lines'], S[i]['kind']) for i in ids]
    cf = f'{D}/cand/cand_inputs.jsonl'
    if os.path.exists(cf):
        for l in open(cf, encoding='utf-8'):
            r = json.loads(l); yield 'cand', r['project'], 'train', r['id'], [([tuple(r['meta']['lines'])], r['meta']['kind'])]


if __name__ == '__main__':
    D, cmd = sys.argv[1], sys.argv[2]; fc = FactCards(D)
    if cmd == 'show':
        pid, uid = sys.argv[3], sys.argv[4]; units, lines = fc.project(pid)
        u = next(x for x in units if x['id'] == uid); t, info = fc.card(pid, [([tuple(u['lines'])], u['kind'])]); print(t); print(info); sys.exit()
    rows = collections.defaultdict(list); skip = collections.Counter(); noabs = collections.Counter(); tot = collections.Counter()
    for src, pid, sp, sid, secs in iter_targets(D):
        t, info = fc.card(pid, secs)
        if t is None: skip[src] += 1; continue
        k = fc._base(secs[0][1]); rows[(src, k)].append(info); tot[src] += 1
        if not info['has_abs']: noabs[src] += 1
    for src in ('labeled', 'cand'):
        print(f'\n== {src}：{tot[src]} 个小节（跳过 {skip[src]}），无摘要 {noabs[src]}（{noabs[src] / max(1, tot[src]):.0%}）')
        allc = [i['chars'] for (s, k), v in rows.items() if s == src for i in v]
        if allc: print('卡字数 均值/P50/P95/最大：', round(statistics.mean(allc)), sorted(allc)[len(allc) // 2], sorted(allc)[int(len(allc) * .95)], max(allc))
        for (s, k), v in sorted(rows.items()):
            if s != src: continue
            print(f'  {k:8s} n={len(v):4d} 卡字数均值 {statistics.mean(i["chars"] for i in v):6.0f}  含摘要节选的比例 {sum(1 for i in v if i["l1_units"]) / len(v):.0%}')
