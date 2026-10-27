"""把项目级事实卡（scripts/fact_card.py：L0 结构索引 + L1 摘要节选 + 存在性标志 E1/E2/E7）写进样本输入的【事实卡】栏。
Usage: python3 -I build_card_samples.py <data_dir> [src=out/samples.jsonl] [dst=out_card/samples.jsonl]
规则：小节审核和比对包样本的【事实卡】= 生成的项目级卡 + 原有人工字段（原有字段是样本证据引用过的，必须保留以保证可达性；无则不加）。
P001、P002（PDF 分页，没有切分文件）不变。事实卡抽取、漏项清单样本不变。思考和回答不变。"""
import sys, os, json, glob, runpy, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fact_card import FactCards
D = sys.argv[1]; SRC = os.path.join(D, sys.argv[2] if len(sys.argv) > 2 else 'out/samples.jsonl'); DST = os.path.join(D, sys.argv[3] if len(sys.argv) > 3 else 'out_card/samples.jsonl')
os.makedirs(os.path.dirname(DST), exist_ok=True)
fc = FactCards(D); secs_by_id = {}
for f in sorted(glob.glob(f'{D}/specs/P*.py')):
    sp = runpy.run_path(f); S, PK = sp['SECTIONS'], sp['PACKS']
    for s in sp['SAMPLES']:
        u = s['unit']; ids = [PK[u]['a'], PK[u]['b']] if u in PK else [u]
        if all('lines' in S[i] for i in ids): secs_by_id[s['id']] = (sp['SOURCE'], [(S[i]['lines'], S[i]['kind']) for i in ids])
stat = collections.Counter(); chars = []
with open(DST, 'w', encoding='utf-8') as fo:
    for line in open(SRC, encoding='utf-8'):
        r = json.loads(line); stat['总数'] += 1
        if r['meta'].get('task_type') not in ('小节审核', '比对包') or r['id'] not in secs_by_id: fo.write(line); stat['不处理'] += 1; continue
        pid, secs = secs_by_id[r['id']]; text, info = fc.card(pid, secs)
        if text is None: fo.write(line); stat['无切分'] += 1; continue
        p = r['messages'][0]['content']; head, rest = p.split('【事实卡】\n', 1); old, tail = rest.split('\n\n【条文】', 1)
        manual = '' if '本任务无相关字段' in old else '\n' + old
        r['messages'][0]['content'] = head + '【事实卡】\n' + text + manual + '\n\n【条文】' + tail
        r['meta']['fact_card'] = dict(chars=info['chars'], l1_units=info['l1_units'], has_abs=info['has_abs'], flags=info['flags'], manual_fields=bool(manual))
        chars.append(info['chars']); stat['已加卡'] += 1; stat['保留人工字段'] += bool(manual)
        fo.write(json.dumps(r, ensure_ascii=False) + '\n')
print(dict(stat), '卡平均字数', sum(chars) / max(1, len(chars)))
