"""对预测做后处理：引文核验。Usage: python3 -I eval_postprocess.py --inputs data/eval/audit_dev.jsonl --pred in.jsonl --out out.jsonl [--mode drop_evidence|drop_finding]
  drop_evidence（默认）：去掉不是逐字出现在输入里的证据条目；一条意见的证据全部被去掉时，整条意见丢弃；
  drop_finding：只要有一条证据不是逐字的，整条意见丢弃（更严）。
输出格式与 eval_run.py 的预测文件相同，可直接交给 eval_score.py 打分。同时打印丢弃了多少条。"""
import argparse, json, re
ap = argparse.ArgumentParser()
ap.add_argument('--inputs', required=True); ap.add_argument('--pred', required=True); ap.add_argument('--out', required=True)
ap.add_argument('--mode', choices=['drop_evidence', 'drop_finding'], default='drop_evidence')
a = ap.parse_args()
squash = lambda s: re.sub(r'\s+', '', s or '')
inputs = {r['id']: r for r in map(json.loads, open(a.inputs, encoding='utf-8'))}

def parse(text):
    t = (text or '').split('</think>')[-1].strip(); i = t.find('{')
    if i < 0: return None, None
    try: obj, end = json.JSONDecoder().raw_decode(t[i:]); return obj, (text or '')[:len((text or '')) - len(t) + i] if False else None
    except Exception: return None, None

n_f = n_drop = n_ev = n_ev_drop = 0
with open(a.out, 'w', encoding='utf-8') as f:
    for line in open(a.pred, encoding='utf-8'):
        p = json.loads(line); obj, _ = parse(p.get('output'))
        if not isinstance(obj, dict) or not isinstance(obj.get('findings'), list): f.write(line); continue
        hay = squash(inputs[p['id']]['prompt']); keep = []
        for fd in obj['findings']:
            if not isinstance(fd, dict): continue
            n_f += 1; evs = [e for e in (fd.get('evidence') or []) if isinstance(e, dict)]
            ok = [e for e in evs if squash(e.get('quote')) and squash(e.get('quote')) in hay]
            n_ev += len(evs); n_ev_drop += len(evs) - len(ok)
            if a.mode == 'drop_finding' and len(ok) < len(evs): n_drop += 1; continue
            if not ok: n_drop += 1; continue
            fd = dict(fd); fd['evidence'] = ok; keep.append(fd)
        obj = dict(obj); obj['findings'] = keep
        p = dict(p); p['output'] = (p.get('output') or '').split('</think>')[0] + ('</think>\n\n' if '</think>' in (p.get('output') or '') else '') + json.dumps(obj, ensure_ascii=False)
        f.write(json.dumps(p, ensure_ascii=False) + '\n')
print(f'意见 {n_f} 条，丢弃 {n_drop} 条（{n_drop / max(1, n_f):.1%}）；证据 {n_ev} 条，非逐字 {n_ev_drop} 条（{n_ev_drop / max(1, n_ev):.1%}）')
