"""给评测预测打分。Usage: python3 -I eval_score.py --inputs data/eval/audit_dev.jsonl --pred data/eval/pred_x_audit_dev.jsonl --name x_audit_dev [--out data/eval]
自动识别评测类型（audit 或 rule）。写 <out>/score_<name>.json、score_<name>.md；audit 另写 judge_<name>.jsonl（未匹配的预测意见，供人工或老师模型复核）。

audit（小节审核）指标：
  格式：JSON 可解析率、字段完整率、verdict 合法率、证据引文逐字出现率、rule_id 在审核重点内的比例、意见中不含条文编号的比例；
  覆盖（对标准答案里每条意见）：规则命中（rule_id 相同）、证据命中（引文重合）、文本命中（问题+建议的二字组召回 ≥ TEXT_T）、综合命中 = 文本命中 或 （规则命中 且 证据命中）；
  额外意见：预测中未匹配任何标准意见的条数。注意标准答案只含专家提过的意见，额外意见不等于误报，需抽样复核（见 judge 文件）。
rule（L3-07 专项）指标：逐项判断的 judgment 准确率与混淆矩阵；汇总的指标集合 F1。"""
import argparse, json, os, re, sys, difflib, collections, statistics
ap = argparse.ArgumentParser()
ap.add_argument('--inputs', required=True); ap.add_argument('--pred', required=True); ap.add_argument('--name', required=True); ap.add_argument('--out', default='data/eval')
a = ap.parse_args()
TEXT_T, EVID_T = 0.40, 0.50
squash = lambda s: re.sub(r'\s+', '', s or '')
ID_RE = re.compile(r'\b(P\d+(?:-[A-Za-z0-9]+)+)\b')
VERDICTS = {'问题', '提示核实', '证据不足', '无问题'}
KEYS = ('issue_type', 'rule_id', 'verdict', 'evidence', 'clause_ids', 'problem', 'suggestion')
inputs = {r['id']: r for r in map(json.loads, open(a.inputs, encoding='utf-8'))}
preds = {r['id']: r for r in map(json.loads, open(a.pred, encoding='utf-8'))}


def parse(text):
    """去掉 <think>…</think>，取其后第一个 JSON 对象；失败返回 None。"""
    t = (text or '').split('</think>')[-1].strip()
    i = t.find('{')
    if i < 0: return None
    try: return json.JSONDecoder().raw_decode(t[i:])[0]
    except Exception: return None


bigrams = lambda s: collections.Counter(s[i:i + 2] for i in range(len(s) - 1))
def recall(gold, pred):
    g, p = bigrams(squash(gold)), bigrams(squash(pred))
    return sum((g & p).values()) / max(1, sum(g.values()))
def quote_hit(gq, pq):
    gq, pq = squash(gq), squash(pq)
    if not gq or not pq: return False
    m = difflib.SequenceMatcher(None, gq, pq, autojunk=False).find_longest_match(0, len(gq), 0, len(pq))
    return m.size >= 10 and m.size >= EVID_T * min(len(gq), len(pq))
quotes = lambda f: [e.get('quote', '') for e in (f.get('evidence') or []) if isinstance(e, dict)]
ftext = lambda f: (f.get('problem') or '') + (f.get('suggestion') or '')

def match(g, p):
    """标准意见 g 与预测意见 p：返回 (规则命中, 证据命中, 文本召回)。"""
    gq = quotes(g); hit = sum(any(quote_hit(x, y) for y in quotes(p)) for x in gq)
    return g.get('rule_id') == p.get('rule_id'), bool(gq) and hit / len(gq) >= EVID_T, recall(ftext(g), ftext(p))


def score_audit():
    S = collections.Counter(); per, judge, rec_best = [], [], []
    for id_, r in inputs.items():
        p = preds.get(id_); S['n'] += 1
        out = parse(p['output']) if p else None
        gold = (parse(r['gold']) or {}).get('findings', [])
        S['gold_findings'] += len(gold)
        if out is None or not isinstance(out.get('findings'), list):
            S['parse_fail'] += 1; per.append(dict(id=id_, parse=False, gold=len(gold), pred=0, covered=0)); continue
        F = [f for f in out['findings'] if isinstance(f, dict)]; S['parse_ok'] += 1; S['pred_findings'] += len(F)
        focus = r['prompt'].split('【审核重点】')[-1].split('【任务】')[0] if '【审核重点】' in r['prompt'] else ''
        hay = squash(r['prompt'])
        for f in F:
            S['schema_ok'] += all(k in f for k in KEYS)
            S['verdict_ok'] += f.get('verdict') in VERDICTS
            qs = [q for q in quotes(f) if q.strip()]
            S['quote_ok'] += bool(qs) and all(squash(q) in hay for q in qs)
            S['rule_in_focus'] += bool(f.get('rule_id')) and str(f.get('rule_id')) in focus
            S['no_clause_id'] += not ID_RE.search(ftext(f))
        used, cov = set(), 0
        for g in gold:
            best = (-1, None)
            for j, f in enumerate(F):
                rh, eh, tr = match(g, f)
                S_ = tr + (0.5 if rh and eh else 0)
                if S_ > best[0]: best = (S_, (j, rh, eh, tr))
            if best[1] is None: continue
            j, rh, eh, tr = best[1]; rec_best.append(tr)
            rule_hit = any(g.get('rule_id') == f.get('rule_id') for f in F)
            evid_hit = any(match(g, f)[1] for f in F)
            text_hit = tr >= TEXT_T
            S['rule_hit'] += rule_hit; S['evid_hit'] += evid_hit; S['text_hit'] += text_hit
            ok = text_hit or any(match(g, f)[0] and match(g, f)[1] for f in F)
            S['covered'] += ok; cov += ok
            gq_ = quotes(g)                                    # 宽松口径（诊断用，不替代综合命中）：规则相同且只要有一段标准引文被命中
            any_q = any(g.get('rule_id') == f.get('rule_id') and any(quote_hit(x, y) for x in gq_ for y in quotes(f)) for f in F)
            S['evid_any'] += any(quote_hit(x, y) for x in gq_ for f in F for y in quotes(f)); S['covered_loose'] += (text_hit or any_q); S['gold_quotes'] += len(gq_)
            if ok: used.add(j)
        for j, f in enumerate(F):                       # 额外意见：未被任何标准意见用到
            if j in used: continue
            if any((lambda m: m[2] >= TEXT_T or (m[0] and m[1]))(match(g, f)) for g in gold): continue
            S['extra'] += 1; judge.append(dict(id=id_, project=r['project'], finding=f))
        per.append(dict(id=id_, project=r['project'], parse=True, gold=len(gold), pred=len(F), covered=cov))
    n, ok, G, P = S['n'], max(1, S['parse_ok']), max(1, S['gold_findings']), max(1, S['pred_findings'])
    res = dict(samples=n, gold_findings=S['gold_findings'], pred_findings=S['pred_findings'],
               parse_rate=S['parse_ok'] / n, schema_rate=S['schema_ok'] / P, verdict_rate=S['verdict_ok'] / P, quote_verbatim_rate=S['quote_ok'] / P,
               rule_in_focus_rate=S['rule_in_focus'] / P, no_clause_id_rate=S['no_clause_id'] / P,
               rule_hit=S['rule_hit'] / G, evidence_hit=S['evid_hit'] / G, text_hit=S['text_hit'] / G, covered=S['covered'] / G,
               evidence_any_hit=S['evid_any'] / G, covered_loose=S['covered_loose'] / G, gold_quotes_per_finding=S['gold_quotes'] / G,
               mean_best_text_recall=statistics.mean(rec_best) if rec_best else 0, extra_per_sample=S['extra'] / ok, pred_per_sample=S['pred_findings'] / ok, gold_per_sample=S['gold_findings'] / n)
    byp = collections.defaultdict(lambda: [0, 0])
    for x in per:
        if x.get('project'): byp[x['project']][0] += x['covered']; byp[x['project']][1] += x['gold']
    res['covered_by_project'] = {p: round(c / max(1, g), 3) for p, (c, g) in sorted(byp.items())}
    with open(os.path.join(a.out, f'judge_{a.name}.jsonl'), 'w', encoding='utf-8') as f:
        for x in judge: f.write(json.dumps(x, ensure_ascii=False) + '\n')
    return res


def toset(x):
    """预测里的列表元素可能是字典等不可哈希的东西（格式出错的输出）；统一转成字符串再比较。"""
    return set(i if isinstance(i, str) else json.dumps(i, ensure_ascii=False, sort_keys=True) for i in (x if isinstance(x, list) else []))


def score_rule():
    S = collections.Counter(); conf = collections.Counter(); f1s = []; f1l = []
    for id_, r in inputs.items():
        p = preds.get(id_); S['n'] += 1
        out, gold = (parse(p['output']) if p else None), parse(r['gold'])
        if out is None or gold is None: S['parse_fail'] += 1; continue
        S['parse_ok'] += 1
        if gold.get('step') == '逐项判断':
            S['item_n'] += 1; S['item_ok'] += out.get('judgment') == gold.get('judgment'); conf[(gold.get('judgment'), out.get('judgment'))] += 1
            if gold.get('judgment') == '驱动成本' and out.get('judgment') == '驱动成本':
                g, o = toset(gold.get('cost_items')), toset(out.get('cost_items')); S['cost_n'] += 1; S['cost_jac'] += len(g & o) / max(1, len(g | o))
        else:
            tp = fp = fn = 0
            for k in ('unlinked_key_indicators', 'need_manual_check', 'uncovered_cost_items'):
                g, o = toset(gold.get(k)), toset(out.get(k)); tp += len(g & o); fp += len(o - g); fn += len(g - o)
            f1s.append(1.0 if tp + fp + fn == 0 else 2 * tp / max(1, 2 * tp + fp + fn))
            tp2 = fp2 = fn2 = 0                                # 宽松口径：只比较条目名称（去掉括号里的说明文字）
            for k in ('unlinked_key_indicators', 'need_manual_check', 'uncovered_cost_items'):
                nm = lambda x: re.sub(r'[（(][^）)]*[）)]', '', x).strip()
                g, o = set(nm(x) for x in toset(gold.get(k))), set(nm(x) for x in toset(out.get(k))); tp2 += len(g & o); fp2 += len(o - g); fn2 += len(g - o)
            f1l.append(1.0 if tp2 + fp2 + fn2 == 0 else 2 * tp2 / max(1, 2 * tp2 + fp2 + fn2))
    n = S['n']
    res = dict(samples=n, parse_rate=S['parse_ok'] / n, item_samples=S['item_n'], judgment_accuracy=S['item_ok'] / max(1, S['item_n']),
               cost_items_jaccard=S['cost_jac'] / max(1, S['cost_n']), summary_samples=len(f1s), summary_f1=statistics.mean(f1s) if f1s else None, summary_f1_loose=statistics.mean(f1l) if f1l else None)
    byc = collections.defaultdict(lambda: [0, 0])
    for (g, o), c in conf.items(): byc[g][1] += c; byc[g][0] += c if g == o else 0
    res['accuracy_by_gold_class'] = {k: round(v[0] / v[1], 3) for k, v in byc.items()}
    res['confusion(gold→pred)'] = {f'{g}→{o}': c for (g, o), c in sorted(conf.items(), key=lambda x: -x[1])}
    return res


kind = 'rule' if os.path.basename(a.inputs).startswith('rule_') else 'audit'
res = score_rule() if kind == 'rule' else score_audit()
res['name'] = a.name; res['kind'] = kind; res['missing_preds'] = len(set(inputs) - set(preds))
json.dump(res, open(os.path.join(a.out, f'score_{a.name}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
md = [f'# 评测 {a.name}（{kind}）', ''] + [f'- {k}: {round(v, 3) if isinstance(v, float) else v}' for k, v in res.items() if not isinstance(v, dict)]
for k, v in res.items():
    if isinstance(v, dict): md += ['', f'## {k}'] + [f'- {x}: {y}' for x, y in v.items()]
open(os.path.join(a.out, f'score_{a.name}.md'), 'w', encoding='utf-8').write('\n'.join(md)); print('\n'.join(md))
