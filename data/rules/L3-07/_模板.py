"""L3-07 专项样本规格模板：复制为 P<编号>.py 后，按项目改写。公共的句式和取证在 lib.py，这里只写“判断了什么”。
只写驱动成本、无对应成本项、需人工核对的指标，不适用最多 2 条（标准第十节第 7 小节）。"""
import os, runpy
_lib = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib.py'))
TAIL = _lib['TAIL']
SOURCE = 'P0xx'
# 行区间用 grep -n 在 data/raw/reports/P0xx.md 中定位；name_col 为“三级指标”所在列（0 起）
sp = _lib['Spec'](SOURCE, ind=(0, 0), cost=(0, 0), ind_label='表x-x 绩效目标表', cost_label='表x-x 成本表', name_col=2, cat_col=1, val_col=3, src_col=4)
TABLES = sp.tables()
ITEMS = [
    # sp.drv('指标名', ['成本项'], '数量因子', '费用＝数量×单价，数量增加，费用同向增加。', [sp.cost_row('成本表中的关键词')], '指标值只写个数，应补充面积。'),
    # sp.mgmt('指标名', '该指标反映对服务商履约的考核结果，'),
    # sp.manual('指标名', '按阶段明确关键环节的完成时点', '时点确定后，对应现场人员的集中投入时段和人数。'),
    # sp.na('指标名', '效益类指标不直接进入成本公式，不判为问题。'),
]
SUMMARY = dict(covered=[], uncovered=[], unlinked=[], manual=[], suggestion='', think='汇总：…\n对照成本构成表：…' + TAIL + '\n结论：…')
SYNTHETIC = []   # 至少一组，格式见 P008.py
