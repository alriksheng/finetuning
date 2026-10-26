"""候选池标注 + DPO 偏好对构造。
Usage: python3 -I build_pool_pairs.py --inputs data/pool/pool_a.jsonl --pred eval_out/pool_a_c50e3.jsonl [--inputs ... --pred ...] --out data/dpo [--margin 1.0]
对每个输入的 n 次采样输出逐个打分（与评测同一套命中口径）：
  命中数 hits = 被命中的标准意见条数（文本召回 ≥0.4，或 规则相同且命中一半以上标准引文）
  额外意见 extras = 没匹配任何标准意见的预测条数；quote_bad = 不是逐字出现在输入里的引文条数；parse_fail = JSON 不可解析
  奖励 R = hits − 0.5×extras − 1.0×quote_bad − 3.0×parse_fail
偏好对：每个输入取 R 最高的输出为 chosen（须可解析、不是被预算强制截断的）、R 最低的为 rejected，二者差 ≥ margin 才保留。
输出 data/dpo/pairs.jsonl（LLaMA-Factory 排序格式）、pool_labeled.jsonl（每个输出的标注）、pairs_preview.md、report.txt。"""
import argparse, json, re, difflib, collections, os, random
ap = argparse.ArgumentParser(); ap.add_argument('--inputs', action='append', required=True); ap.add_argument('--pred', action='append', required=True)
ap.add_argument('--out', required=True); ap.add_argument('--margin', type=float, default=1.0); ap.add_argument('--w-extra', type=float, default=0.5)
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
squash = lambda s: re.sub(r'\s+', '', s or '')
bg = lambda s: collections.Counter(s[i:i + 2] for i in range(len(s) - 1))
def recall(g, p):
    g, p = bg(squash(g)), bg(squash(p)); return sum((g & p).values()) / max(1, sum(g.values()))
def qh(x, y):
    x, y = squash(x), squash(y)
    if not x or not y: return False
    m = difflib.SequenceMatcher(None, x, y, autojunk=False).find_longest_match(0, len(x), 0, len(y)).size
    return m >= 10 and m >= 0.5 * min(len(x), len(y))
Q = lambda f: [e.get('quote', '') for e in (f.get('evidence') or []) if isinstance(e, dict)]
T = lambda f: (f.get('problem') or '') + (f.get('suggestion') or '')
def parse(t):
    t = (t or '').split('</think>')[-1].strip(); i = t.find('{')
    if i < 0: return None
    try: return json.JSONDecoder().raw_decode(t[i:])[0]
    except Exception: return None
def hit(g, f):
    gq = Q(g); ev = bool(gq) and sum(any(qh(x, y) for y in Q(f)) for x in gq) / len(gq) >= 0.5
    return recall(T(g), T(f)) >= 0.4 or (g.get('rule_id') == f.get('rule_id') and ev)
def norm_out(o):
    """统一成训练格式：<think>\\n思考\\n</think>\\n\\nJSON"""
    th, _, js = o.partition('</think>')
    return '<think>\n' + th.replace('<think>', '').strip() + '\n</think>\n\n' + js.strip()
def loopish(t, w=20, rep=6):
    c = collections.Counter(t[i:i + w] for i in range(0, max(0, len(t) - w)))
    return any(v >= rep for v in c.values())
labeled, pairs, st = [], [], collections.Counter(); why = collections.Counter(); dr = []
for inp_f, pred_f in zip(a.inputs, a.pred):
    inp = {r['id']: r for r in map(json.loads, open(inp_f, encoding='utf-8'))}
    for line in open(pred_f, encoding='utf-8'):
        p = json.loads(line); r = inp.get(p['id'])
        if not r: continue
        gold = (parse(r['gold']) or {}).get('findings', []); hay = squash(r['prompt'])
        outs = p.get('outputs') or [p.get('output')]; rec = []
        for k, o in enumerate(outs):
            o = o or ''; ob = parse(o)
            if not isinstance(ob, dict) or not isinstance(ob.get('findings'), list):
                rec.append(dict(k=k, R=-3.0, parse_fail=1, hits=0, extras=0, qbad=0, forced=0)); continue
            F = [f for f in ob['findings'] if isinstance(f, dict)]
            used = set(); hits = 0
            for g in gold:
                m = [j for j, f in enumerate(F) if hit(g, f)]
                if m: hits += 1; used.update(m)
            extras = sum(1 for j, f in enumerate(F) if j not in used and not any(hit(g, f) for g in gold))
            qbad = sum(1 for f in F for q in Q(f) if squash(q) and squash(q) not in hay)
            loop = loopish(o.split('</think>')[0]); 
            rec.append(dict(k=k, R=hits - a.w_extra * extras - 1.0 * qbad, parse_fail=0, hits=hits, extras=extras, qbad=qbad, forced=int('forced' in p and loop), n_find=len(F)))
        for x in rec: labeled.append(dict(id=p['id'], gold_n=len(gold), **x))
        ok = [x for x in rec if not x['parse_fail'] and not x['forced']]
        if len(ok) < 1 or len(rec) < 2: st['样本无足够输出'] += 1; continue
        best = max(ok, key=lambda x: (x['R'], -x['extras'], x['hits'])); worst = min(rec, key=lambda x: (x['R'], -x['extras']))
        if best['k'] == worst['k'] or best['R'] - worst['R'] < a.margin: st['差距不足'] += 1; continue
        why['rejected 不可解析' if worst['parse_fail'] else ('rejected 有编造引文' if worst['qbad'] else ('rejected 额外意见多' if worst['extras'] > worst['hits'] else 'rejected 命中少'))] += 1
        dr.append(best['R'] - worst['R'])
        pairs.append(dict(system=r['system'], conversations=[{'from': 'human', 'value': r['prompt']}], chosen={'from': 'gpt', 'value': norm_out(outs[best['k']])},
                          rejected={'from': 'gpt', 'value': norm_out(outs[worst['k']])}, _meta=dict(id=p['id'], R_chosen=best['R'], R_rejected=worst['R'], chosen=best, rejected=worst, gold_n=len(gold))))
        st['成对'] += 1
open(os.path.join(a.out, 'pool_labeled.jsonl'), 'w', encoding='utf-8').write(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in labeled))
open(os.path.join(a.out, 'pairs.jsonl'), 'w', encoding='utf-8').write(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in pairs))
json.dump([{k: v for k, v in x.items() if k != '_meta'} for x in pairs], open(os.path.join(a.out, 'dpo_pairs.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
json.dump({'audit_dpo': {'file_name': 'dpo_pairs.json', 'formatting': 'sharegpt', 'ranking': True, 'columns': {'messages': 'conversations', 'chosen': 'chosen', 'rejected': 'rejected', 'system': 'system'}}}, open(os.path.join(a.out, 'dataset_info.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
n = len(labeled)
rep = [f'输出 {n} 个（{len({x["id"] for x in labeled})} 个输入）；不可解析 {sum(x["parse_fail"] for x in labeled)}；平均命中数 {sum(x["hits"] for x in labeled) / n:.2f}，平均额外意见 {sum(x["extras"] for x in labeled) / n:.2f}，编造引文 {sum(x["qbad"] for x in labeled)} 条',
       f'偏好对 {len(pairs)} 对（margin ≥ {a.margin}）；跳过：{dict((k, v) for k, v in st.items() if k != "成对")}；奖励差均值 {sum(dr) / max(1, len(dr)):.2f}', f'rejected 的主要问题：{dict(why)}']
open(os.path.join(a.out, 'report.txt'), 'w', encoding='utf-8').write('\n'.join(rep)); print('\n'.join(rep))
random.Random(0).shuffle(pairs)
with open(os.path.join(a.out, 'pairs_preview.md'), 'w', encoding='utf-8') as fo:
    for x in pairs[:8]:
        m = x['_meta']; fo.write(f"## {m['id']}  R: chosen {m['R_chosen']:.1f} / rejected {m['R_rejected']:.1f}（标准意见 {m['gold_n']} 条）\n\n**chosen** 命中 {m['chosen']['hits']} 额外 {m['chosen']['extras']} 编造引文 {m['chosen']['qbad']}\n\n```\n{x['chosen']['value'][-900:]}\n```\n\n**rejected** 命中 {m['rejected']['hits']} 额外 {m['rejected']['extras']} 编造引文 {m['rejected']['qbad']} 不可解析 {m['rejected']['parse_fail']}\n\n```\n{x['rejected']['value'][-900:]}\n```\n\n---\n\n")
