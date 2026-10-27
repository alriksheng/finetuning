"""用“缺失”类意见检验存在性清单 E1~E8：专家断言“没有 X”，检测函数在除当前小节外的全报告里是否找到 X。
Usage: python3 -I fact_card_exist_eval.py <data_dir> [--show E3 5]"""
import sys, os, re, json, glob, runpy, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fact_card_exist import detect
D = sys.argv[1]; show = sys.argv[sys.argv.index('--show') + 1:] if '--show' in sys.argv else []
MAP = [  # (编号, 条件：规则集合, 专家文字正则)
    ('E1', None, r'20(?:2[6-9]|3\d)\s*年|后续年度|下一年度|以后年度'),
    ('E3', {'R-PROC-PURCHASE', 'R-SUGGEST-QUALITY', 'R-PROC-FLOW'}, r'采购管理|合同管理|服务考核|履约|验收|合同'),
    ('E4', None, r'人员配置|岗位设置|定员|人员配备|岗位|工时|人员数量'),
    ('E5', {'R-BASIC-CONTENT'}, r'体量|规模|面积|长度|数量|人数|场次|频次'),
    ('E6', {'R-COST-OPEN'}, r'成本明细|明细表|细化|打开|分项|单价和数量'),
    ('E7', {'R-BASIC-BUDGET'}, r'预算|决算|调剂|执行'),
]
pts = []
for f in sorted(glob.glob(f'{D}/specs/P*.py')):
    sp = runpy.run_path(f); pid = sp['SOURCE']
    sj, md = f'{D}/specs/sections/{pid}.json', f'{D}/raw/reports/{pid}.md'
    if not (os.path.exists(sj) and os.path.exists(md)): continue
    units = json.load(open(sj, encoding='utf-8'))['units']; lines = open(md, encoding='utf-8').read().split('\n')
    for s in sp['SAMPLES']:
        S = sp['SECTIONS'].get(s['unit'])
        if not S or 'lines' not in S: continue
        ex = set()
        for a, b in S['lines']: ex.update(range(a, b + 1))
        for p in s.get('points', []) or []:
            if p.get('type') != '缺失': continue
            txt = p.get('expert_text') or (p.get('problem', '') + p.get('suggestion', ''))
            rules = set(p.get('rules') or [])
            code = next((c for c, rs, rx in MAP if (rs is None or rules & rs) and re.search(rx, txt)), None)
            pts.append(dict(pid=pid, sid=s['id'], code=code, text=txt, rules=sorted(rules), units=units, lines=lines, ex=ex))
print('“缺失”类意见（md 项目）', len(pts), '；归入 E 项', sum(1 for p in pts if p['code']), '；未归入', sum(1 for p in pts if not p['code']))
STRONG_ONLY = '--strong' in sys.argv
res = collections.defaultdict(lambda: [0, 0, 0]); ex_ = collections.defaultdict(list)
cache = {}
for p in pts:
    if not p['code']: continue
    key = (p['pid'], tuple(sorted(p['ex'])))
    if key not in cache: cache[key] = detect(p['units'], p['lines'], p['ex'])
    found = cache[key][p['code']]; strong = [f for f in found if f[1].startswith('S|')]
    res[p['code']][0] += 1; res[p['code']][1] += bool(found); res[p['code']][2] += bool(strong)
    if (strong if STRONG_ONLY else found): ex_[p['code']].append((p, strong if STRONG_ONLY else found))
print('\n编号\t归入条数\t其他小节有检测（含弱）\t比例\t其他小节有强检测\t比例')
for c in sorted(res): print(f'{c}\t{res[c][0]}\t{res[c][1]}\t{res[c][1] / res[c][0]:.0%}\t{res[c][2]}\t{res[c][2] / res[c][0]:.0%}')
if show:
    c, n = show[0], int(show[1])
    for p, found in ex_[c][:n]:
        print('\n##', p['pid'], p['sid'], '专家:', p['text'][:110]); print('  检测到:', found[0][0][:30], '|', found[0][1][:110])
