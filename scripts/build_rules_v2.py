"""合并原规则库与专家规则（xreport-reviewer），生成新版规则库 data/rules/rules_v2.yaml 和 data/rules/conduct.yaml（2026-10-27）。

用法：python3 -I scripts/build_rules_v2.py data
- 原有 31 条规则的编号、标签、层级等字段不变；每条增加 points（专家审核点：point、raise、not_raise、note、source_pids）。
- NEW: 开头的规则为拟新增规则，status 写“拟新增，待用户确认”，标签取 NEW_RULES。
- CONDUCT / PROGRAM / TERM / POLICY / META 写入 conduct.yaml，不进入【规则要点】。
- 检查：【规则要点】文字和非规则条目中不得出现任何项目名称（取自 splits_v2.yaml 的项目组名）；输出每条规则放进【规则要点】后的字数。
"""
import collections, glob, os, re, runpy, sys
import yaml

DATA = sys.argv[1]
R = os.path.join(DATA, 'rules')
NEW_RULES = {
    'R-BASIC-BASIS': dict(tag='立项依据', level='L2', question='立项依据是否完整、现行有效，依据表内容与文件是否对应'),
    'R-BASIC-MGMT': dict(tag='职责分工与业务管理', level='L2', question='相关主体职责分工是否明确，供应商与采购、合同、验收等业务管理内容是否介绍完整'),
    'R-PURCHASE-NEED': dict(tag='购买服务立项必要性', level='L2', question='购买服务项目是否论证立项必要性、规范性和必须通过购买服务完成的理由，是否符合分类管控要求'),
    'R-POL-SHARE': dict(tag='政策分担比例', level='L3', question='涉及多级财政分担的，分担比例是否合理'),
}
OTHER = {'CONDUCT', 'PROGRAM', 'TERM', 'POLICY', 'META'}


def injected(rule):
    """【规则要点】中这条规则的文字：标签、检查问题、各审核点的提出条件和不提条件。"""
    parts = [f"{rule['tag']}（{rule['rule_id']}）：{rule['question']}"]
    for p in rule.get('points', []):
        if p['raise']:
            parts.append(f"{p['point']}——提出：{p['raise']}" + (f"；不提：{p['not_raise']}" if p['not_raise'] else ''))
        elif p['not_raise']:
            parts.append(f"{p['point']}——不提：{p['not_raise']}")
    if len(parts) == 1 and rule.get('judgment_points'):
        parts.append('判断要点：' + rule['judgment_points'])
    return '\n'.join(parts)


def main():
    base = yaml.safe_load(open(os.path.join(R, 'rules.yaml'), encoding='utf-8'))
    rules = {r['rule_id']: dict(r) for r in base}
    other = collections.defaultdict(list)
    for f in sorted(glob.glob(os.path.join(R, 'expert_mapping', '*.py'))):
        for m in runpy.run_path(f)['MAPPING']:
            item = dict(point=m['point'], raise_=m.get('raise_', ''), not_raise=m.get('not_raise', ''), note=m.get('note', ''), source_pids=m['pids'])
            rid = m['rule']
            if rid in OTHER:
                other[rid].append(dict(point=item['point'], note=item['note'], source_pids=item['source_pids']))
                continue
            if rid.startswith('NEW:'):
                rid = rid[4:]
                if rid not in rules:
                    rules[rid] = dict(rule_id=rid, **NEW_RULES[rid], judgment_points='', policy_anchor=[], origin='评审经验（专家智能体规则）',
                                      source_cases=[], industries=[], valid_period='2025-', status='拟新增，待用户确认')
            rules[rid].setdefault('points', []).append(dict(point=item['point'], raise_=item['raise_'], not_raise=item['not_raise'],
                                                              note=item['note'], source_pids=item['source_pids']))
    for r in rules.values():
        r['points'] = [dict(point=p['point'], raise_=p['raise_'], not_raise=p['not_raise'], note=p['note'], source_pids=p['source_pids'])
                       for p in r.get('points', [])]
        for p in r['points']:
            p['raise'] = p.pop('raise_')
    # 检查项目名
    sp = yaml.safe_load(open(os.path.join(DATA, 'splits_v2.yaml'), encoding='utf-8'))
    names = {g.split('｜')[-1] for g in sp['groups']}
    text = '\n'.join(injected(r) for r in rules.values()) + yaml.safe_dump(dict(other), allow_unicode=True)   # 只查会进入输入或成文规范的文字
    hits = sorted(n for n in names if len(n) >= 6 and n in text)
    yaml.safe_dump(list(rules.values()), open(os.path.join(R, 'rules_v2.yaml'), 'w', encoding='utf-8'), allow_unicode=True, sort_keys=False, width=200)
    yaml.safe_dump(dict(other), open(os.path.join(R, 'conduct.yaml'), 'w', encoding='utf-8'), allow_unicode=True, sort_keys=False, width=200)
    lens = {rid: len(injected(r)) for rid, r in rules.items()}
    print(f'规则 {len(rules)} 条（新增 {sum(1 for r in rules.values() if str(r.get("status","")).startswith("拟新增"))} 条），专家审核点 {sum(len(r["points"]) for r in rules.values())} 个；'
          f'非规则条目 {dict((k, len(v)) for k, v in other.items())}')
    print('规则文本中出现的项目名：', hits or '无')
    print('每条规则放进【规则要点】的字数（从多到少）：')
    for rid, n in sorted(lens.items(), key=lambda x: -x[1]):
        print(f'  {rid:18s} {n}')
    # 按 focus_map 估算每个章节的【规则要点】总字数
    fm = yaml.safe_load(open(os.path.join(DATA, 'specs', 'focus_map.yaml'), encoding='utf-8'))
    tot = []
    for ptype, kinds in fm.items():
        for kind, rids in kinds.items():
            tot.append((sum(lens.get(x, 0) for x in rids), ptype, kind, len(rids)))
    tot.sort(reverse=True)
    print('各章节【规则要点】总字数（前 8）：', [(f'{p}/{k}', n, f'{c}条规则') for n, p, k, c in tot[:8]])
    print('各章节【规则要点】总字数 中位数：', sorted(t[0] for t in tot)[len(tot) // 2])


if __name__ == '__main__':
    main()
