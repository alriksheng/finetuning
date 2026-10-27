# 用法：python3 -I scripts/cot_v2_tools/selfcheck.py [起始序号]
# 对 data/cot_v2/out/samples.json 做 build_cot_v2.py 之外的自查（样本生成标准第六、七、十二节）：
#   表号/附件号/页码必须出现在输入或意见中；禁用词（完全、毫无、根本、绝对、不了、脱钩）；“专家”作为意见来源；推理不足 450 字（仅提示）。
# 注意：摘录行是报告原文，其中的“专家建议”等词会被命中，属于误报，不用改。
import json, re, sys, os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
ENT = re.compile(r'(?<![代图])表\s?\d+(?:[-－—]\d+)*|附件\s?\d+|第\s?\d+\s?页')
ABS = re.compile(r'完全|毫无|根本|绝对|不了|脱钩|反映不了')
SRC = re.compile(re.search(r"SRC_EXPERT = re.compile\(r'(.*?)'\)", open('scripts/build.py', encoding='utf-8').read()).group(1))
sq = lambda s: re.sub(r'\s+', '', s)
d = json.load(open('data/cot_v2/out/samples.json', encoding='utf-8'))
n0 = int(sys.argv[1]) if len(sys.argv) > 1 else 0
for i, x in enumerate(d):
    if i < n0: continue
    u = x['conversations'][0]['value']; a = x['conversations'][1]['value']
    th = re.search(r'<think>\n(.*?)\n</think>', a, re.S).group(1)
    for e in set(ENT.findall(th)):
        if sq(e) not in sq(u) and sq(e) not in sq(a.split('</think>')[1]): print(i, '表号不在输入', e)
    for m in ABS.finditer(th): print(i, '绝对词', th[max(0, m.start() - 15):m.end() + 8].replace('\n', ' '))
    m = SRC.search(th)
    if m: print(i, '专家', th[max(0, m.start() - 15):m.end() + 10].replace('\n', ' '))
    if len(th) < 450: print(i, '短', len(th))
print('done', len(d))
