"""核验脚本的单元测试（方案 v4 〇.5：核验脚本是安全网，用已知正确和错误的例子验证）。
Usage: python3 -I test_checks.py"""
import os, runpy

D = os.path.dirname(os.path.abspath(__file__))
C = runpy.run_path(os.path.join(D, 'checks.py'))
R = runpy.run_path(os.path.join(D, 'render_opinion.py'))
fails = []
def check(name, cond):
    if not cond: fails.append(name)

# 1. 引文核验：逐字（忽略空白）通过；改一个字不通过；省略号分段
inp = '2024年成本金额为427.35万元，核定金额为668.67万元，核减金额为13.69万元'
check('quote ok', C['quotes_ok']('写为「核定金额为668.67万元」', inp) == [])
check('quote whitespace', C['quotes_ok']('「核定金额为 668.67 万元」', inp) == [])
check('quote altered', C['quotes_ok']('「核定金额为668.76万元」', inp) != [])
check('quote ellipsis', C['quotes_ok']('「成本金额为427.35万元……核减金额为13.69万元」', inp) == [])

# 2. 算式与数字来源
e, _ = C['check_arith']('427.35−13.69=413.66；13.69÷427.35≈3.20%', inp); check('arith ok', e == [])
e, _ = C['check_arith']('427.35−13.69=415.00', inp); check('arith wrong', any('arith' in x for x in e))
e, _ = C['check_arith']('13.69÷427.35≈3.13%', inp); check('arith pct wrong', any('arith' in x for x in e))
e, _ = C['check_arith']('另增约999.99万元', inp); check('number no source', any('not in input' in x for x in e))
e, _ = C['check_arith']('降本率处于5%至10%之间', inp, extra_allowed=['5%', '10%']); check('rule threshold allowed', e == [])

# 3. 意见组装：结构化字段渲染为文字
obj = dict(task='小节审核', findings=[
    dict(issue_type='历史成本未打开至末端', verdict='问题', problem='委托服务费仅按类别列示。', suggestion='建议补充单价和数量。', clause_ids=['X-1'], basis_type='政策'),
    dict(issue_type='支出明细', verdict='提示核实', problem='现有材料未体现支出明细。', suggestion='建议核对第三章。', clause_ids=[], basis_type='评审经验')])
check('render', R['render'](obj) == '一、历史成本未打开至末端\n委托服务费仅按类别列示。建议补充单价和数量。\n请核实：现有材料未体现支出明细。建议核对第三章。')
check('render basis unknown clause', R['render_basis'](obj, {}) == ['X-1（依据待核实）', '评审经验'])
check('render empty', R['render'](dict(task='小节审核', findings=[])) == '未发现问题。')
fc = dict(task='事实卡抽取', fields=[dict(name='a', value='1', page='第1页', quote='q'), dict(name='b', value='2', page='第1页', quote='q')])
check('render factcard 同上', R['render'](fc) == '- a：1（第1页）“q”\n- b：2（第1页）同上')

# 4. 公文格式组装：同一部分合并为“一是……二是……”，部分名不进正文、单列为标签，提示核实单列
fs = [dict(part='成本核算分析部分', issue_type='a', verdict='问题', problem='甲，', suggestion='建议乙。'),
      dict(part='成本核算分析部分', issue_type='b', verdict='问题', problem='丙。', suggestion='需丁。'),
      dict(part='降本增效情况', issue_type='c', verdict='问题', problem='戊，', suggestion='建议己。'),
      dict(part='成本核算分析部分', issue_type='d', verdict='提示核实', problem='庚，', suggestion='需核对辛。')]
check('render formal', R['render'](dict(task='小节审核', findings=fs)) == '一是甲，建议乙。二是丙。需丁。\n戊，建议己。\n请核实：庚，需核对辛。')
check('render tags', R['render_tags'](dict(task='小节审核', findings=fs)) == ['成本核算分析部分', '降本增效情况', '提示核实（成本核算分析部分）'])

print('PASS' if not fails else 'FAIL: ' + ', '.join(fails))
raise SystemExit(1 if fails else 0)
