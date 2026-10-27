"""训练标签一致性检查：用意见文字（problem+suggestion）训练轻量文本分类器，按项目分组做交叉验证，
找出“标注规则与文字预测规则高置信度不一致”的训练意见，供人工（或 Claude Code 按 8 号文、15 号文）复核。
Usage: python3 -I flag_label_noise.py <data_dir> <out.json> [阈值=0.5]
只看训练集项目（排除开发集、测试集）；只看专家来源的小节审核/比对包意见。"""
import sys, os, json, re, collections, yaml, numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
D, OUT = sys.argv[1], sys.argv[2]; TH = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
sp = yaml.safe_load(open(os.path.join(D, 'splits.yaml'), encoding='utf-8'))
heldout = set()
for g in sp['groups'].values():
    if g.get('split') in ('dev', 'test'): heldout |= set(g['projects'])
tx = lambda f: (f.get('problem') or '') + (f.get('suggestion') or '')
rows = []
for l in open(os.path.join(D, 'out/samples.jsonl'), encoding='utf-8'):
    r = json.loads(l); m = r['meta']
    if m['project_id'] in heldout or m.get('task_type') not in ('小节审核', '比对包') or m.get('source_kind') != 'expert': continue
    try: o = json.loads(r['messages'][1]['content'].split('</think>')[-1].strip())
    except Exception: continue
    for k, f in enumerate(o.get('findings') or []):
        if f.get('rule_id') and tx(f) and f.get('verdict') == '问题':
            rows.append(dict(sid=r['id'], k=k, project=m['project'], pid=m['project_id'], scope=m.get('input_scope'), rule=f['rule_id'], issue=f.get('issue_type'),
                             quotes=[e.get('quote', '') for e in f.get('evidence') or [] if isinstance(e, dict)], text=tx(f)))
cnt = collections.Counter(x['rule'] for x in rows)
rows = [x for x in rows if cnt[x['rule']] >= 5]
y = np.array([x['rule'] for x in rows]); g = np.array([x['pid'] for x in rows])
pipe = make_pipeline(TfidfVectorizer(analyzer='char', ngram_range=(1, 3), sublinear_tf=True, min_df=2), LogisticRegression(C=20, max_iter=2000))
P = cross_val_predict(pipe, [x['text'] for x in rows], y, cv=GroupKFold(5), groups=g, method='predict_proba')
cls = sorted(set(y)); pred = np.array(cls)[P.argmax(1)]
print(f'意见 {len(rows)} 条，规则 {len(cls)} 个，按项目分组 5 折：文字→规则准确率 {(pred == y).mean():.3f}')
out = []
for i, x in enumerate(rows):
    if pred[i] != y[i] and P[i].max() >= TH:
        x = dict(x); x.update(pred=str(pred[i]), prob=float(P[i].max()), p_label=float(P[i][cls.index(y[i])])); out.append(x)
out.sort(key=lambda x: (x['rule'], x['pred'], x['sid']))
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'高置信度（≥{TH}）不一致 {len(out)} 条 → {OUT}')
