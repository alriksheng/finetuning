"""L3-07 专项样本规格的公共函数：从原文取指标表行（保证证据逐字），生成各类逐项判断的固定句式。
每个项目的规格文件只写“判断了什么”（指标、成本项、公式），不再重复写模板代码。用法见 P008.py。
"""
import os
TAIL = '依据：评审经验（规则 L3-07；指标到成本计算规则）。'
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Spec:
    def __init__(self, pid, ind, cost, ind_label, cost_label, name_col=2, cat_col=1, val_col=3, src_col=4, level_col=0):
        """ind、cost 为原文行区间（1 起，含两端）；各 *_col 为指标表中对应列的序号（0 起）。"""
        self.pid, self.ind, self.cost, self.ind_label, self.cost_label = pid, ind, cost, ind_label, cost_label
        self.L = open(os.path.join(_ROOT, f'raw/reports/{pid}.md'), encoding='utf-8').read().split('\n')
        self.nc, self.cc, self.vc, self.sc, self.lc = name_col, cat_col, val_col, src_col, level_col
        self.by = {}
        for r in [l for l in self.L[ind[0] - 1:ind[1]] if l.startswith('| ')][1:]:
            c = [x.strip() for x in r.strip('|').split('|')]
            if len(c) <= max(name_col, cat_col, val_col):
                continue   # “以下为频次类指标”等分隔行
            self.by[c[name_col]] = (r, c)

    def tables(self):
        return {'ind': {'lines': self.ind, 'label': self.ind_label}, 'cost': {'lines': self.cost, 'label': self.cost_label}}

    def cost_row(self, key):
        """成本表范围内含 key 的第一行（证据用）。"""
        return next(l for l in self.L[self.cost[0] - 1:self.cost[1]] if key in l)

    def _g(self, ind):
        r, c = self.by[ind]
        return r, c[self.cc], c[self.vc], (c[self.sc] if self.sc is not None and self.sc < len(c) else '')

    def drv(self, ind, costs, factor, formula, ev_extra=(), gap='', category=None):
        """驱动成本：formula 写计算关系；ev_extra 为成本表中的证据行（用 cost_row 取）；gap 写指标表缺什么。"""
        r, cat, val, _ = self._g(ind); cat = category or cat
        return dict(indicator=ind, category=cat, judgment='驱动成本', cost_items=list(costs), direction='同向', evidence=[r] + list(ev_extra), reason=formula + gap,
                    think=f'步骤1（类别）：「{ind}」属于{cat}，指标值为「{val}」，在适用范围内。\n步骤2（成本公式）：{formula}{gap}{TAIL}\n结论：驱动成本（{factor}），影响{"、".join(costs)}，方向同向。')

    def mgmt(self, ind, why, repl='岗位人员数量、会场面积等数量指标', category=None):
        """常规性项目管理要求类 → 无对应成本项。why 以“，”结尾说明该指标反映什么。"""
        r, cat, val, src = self._g(ind); cat = category or cat
        return dict(indicator=ind, category=cat, judgment='无对应成本项', cost_items=[], direction=None, evidence=[r],
                    reason=f'{why}属于常规性项目管理要求，不改变任何成本项的数量或单价；按市级指标设置指引不宜设置，建议替换为{repl}。',
                    think=f'步骤1（类别）：「{ind}」属于{cat}，指标值为「{val}」' + (f'，来源为「{src}」' if src else '') + f'，先按常规性项目管理要求判断。\n步骤2（成本公式）：{why}属于常规性项目管理要求，成本构成表中没有随它变化的数量或单价。市级指标设置指引要求不设置“与产出、效益和成本明显无关联”的管理要求类指标。{TAIL}\n结论：无对应成本项（常规性管理要求类指标），建议替换为{repl}。')

    def manual(self, ind, how, link, category=None):
        """需人工核对：指标值只写“及时”“完成”等，缺少量化表述。how 为量化方向，link 为量化后对应的投入。"""
        r, cat, val, _ = self._g(ind); cat = category or cat
        return dict(indicator=ind, category=cat, judgment='需人工核对', cost_items=[], direction=None, evidence=[r],
                    reason=f'指标值只写“{val}”，缺少量化表述，无法判断与成本的对应关系，需人工核对。量化方向：{how}；{link}',
                    think=f'步骤1（类别）：「{ind}」属于{cat}，在适用范围内。\n步骤2（量化）：指标值为「{val}」，没有量化表述，无法据此判断对应哪种资源投入。量化方向：{how}；{link}具体数值取合同约定、行业标准或历史实际。{TAIL}\n结论：需人工核对（无量化表述），建议{how}。')

    def na(self, ind, why, category=None):
        """不适用（最多写 2 条）。"""
        r, cat, val, _ = self._g(ind); cat = category or cat
        return dict(indicator=ind, category=cat, judgment='不适用', cost_items=[], direction=None, evidence=[r], reason=why,
                    think=f'步骤1（类别）：「{ind}」属于{cat}，按规则卡不在适用范围内。{TAIL}\n结论：不适用，不判为问题。')
