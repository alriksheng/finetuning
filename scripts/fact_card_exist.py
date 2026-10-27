"""项目级事实卡 L2：存在性清单 E1~E8 的检测函数（设计见 项目级事实卡设计.md 第 12 节）。
detect(units, lines, exclude_lines) → {编号: [(小节路径, 摘录), ...]}；空列表表示在（除当前小节外的）全报告中没有检测到。
纯程序，逐字摘录；规则是初版，用 143 条“缺失”类意见做一致率检验后再调。"""
import re
Q = r'\d[\d,\.]*\s*(?:万平方米|平方米|平方公里|公里|米|㎡|m²|亩|套|个|台|座|条|盏|人|名|场|次|间|辆|艘|户|吨|件|块|栋|处|家)'
PAT = {
    'E1': re.compile(r'(?:20(?:2[6-9]|3\d))\s*年(?:度)?[^。；\n]{0,14}(?:预算|资金|经费)[^。；\n]{0,14}(?:安排|建议|测算|申报|调整|编制)|(?:后续|下一|以后|未来)年度[^。；\n]{0,16}(?:预算|资金|经费)'),
    'E2': re.compile(r'(?:分析结果|成本分析|核定结果|测算结果|分析结论)[^。；\n]{0,14}(?:应用|运用|挂钩|用于|作为)[^。；\n]{0,14}(?:预算|绩效目标|申报)'),
    'E4': re.compile(r'(?:人员配置|岗位设置|定员|定岗|人员配备|岗位配置|人员编制)'),
    'E5': re.compile(Q),
}
STRONG = {  # 强检测：不只是提到话题，而是出现了具体内容（带金额的年度预算、带人数的配置等）
    'E1': re.compile(r'(?:20(?:2[6-9]|3\d))\s*年(?:度)?[^。；\n]{0,20}(?:预算|资金|经费)[^。；\n]{0,25}\d[\d,\.]*\s*(?:万元|元)'),
    'E4': re.compile(r'(?:人员配置|岗位设置|定员|定岗|人员配备|岗位配置|人员编制)[^。；\n]{0,30}\d+\s*(?:人|名|个岗位|个)|\d+\s*(?:人|名)[^。；\n]{0,20}(?:人员配置|岗位设置|定员|人员配备|岗位配置)'),
}
norm = lambda s: re.sub(r'\s+', ' ', s)


def detect(units, lines, exclude_lines=()):
    ex = set(exclude_lines); out = {k: [] for k in ('E1', 'E2', 'E3', 'E4', 'E5', 'E6', 'E7', 'E8')}
    for u in units:
        a, b = u['lines']
        if set(range(a, b + 1)) & ex: continue
        raw = lines[a - 1:b]; t = norm('\n'.join(raw)); path = u['path']
        for k in ('E1', 'E2', 'E4'):
            m = PAT[k].search(t)
            if m:
                g = 'S' if k in STRONG and STRONG[k].search(t) else 'W'
                out[k].append((path, g + '|' + t[max(0, m.start() - 20): m.end() + 30]))
        n3 = sum(1 for w in ('采购', '合同', '考核', '验收', '履约', '付款', '支付') if w in t)
        if n3 >= 3 and '合同' in t and '采购' in t:
            out['E3'].append((path, ('S' if n3 >= 5 and ('考核' in t or '验收' in t) else 'W') + '|' + t[max(0, t.find('合同') - 20): t.find('合同') + 60]))
        if u['kind'] in ('basic', 'abs_basic') and len(PAT['E5'].findall(t)) >= 3:
            m = PAT['E5'].search(t); out['E5'].append((path, ('S' if len(PAT['E5'].findall(t)) >= 5 else 'W') + '|' + t[max(0, m.start() - 20): m.end() + 20]))
        rows = [x for x in raw if x.strip().startswith('|')]
        if u['kind'] in ('cost', 'abs_cost') and len(rows) >= 5 and re.search(r'金额|单价|数量|成本', ' '.join(rows[:2])):
            out['E6'].append((path, ('S' if len(rows) >= 8 else 'W') + '|' + rows[0][:60]))
        if u['kind'] in ('basic', 'abs_basic') and re.search(r'20\d\d', t) and '预算' in t and re.search(r'决算|执行', t) and len(rows) >= 3:
            out['E7'].append((path, ('S' if len(rows) >= 4 and '预算' in ' '.join(rows[:2]) else 'W') + '|' + rows[0][:60]))
        if u['kind'] == 'annex' and u['chars'] < 300: out['E8'].append((path, f"S|附件仅 {u['chars']} 字"))
    return out
