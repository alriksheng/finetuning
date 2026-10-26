"""按拒绝采样的命中次数给训练样本分层，并决定每个样本在训练集里放几份。
Usage: python3 -I apply_tiers.py <data_dir> [in=out_rft/samples.jsonl] [tiers=out_rft/tiers.jsonl] [out=out_tier/samples.jsonl]
样本级命中率 h = 各条标准意见被命中的采样次数（封顶 5）之和 / (5 × 标准意见条数)：
  h > 0.6        稳定：1 份（只有 16 个，省不出多少预算）
  0.2 < h ≤ 0.6  不稳定、模型能做对：2 份（重点，111 个）
  0 < h ≤ 0.2    偶尔命中、较难：1 份
  h = 0          从未命中：1 份（可能是难例也可能是噪声，不放大）
没有采样结果的项目（c25 训练过的 26 个）：1 份。
与原建议（不稳定和从未命中都放 2 份）的差别：按原建议训练行数会增加约 65%，“放大”和“训练步数增加”混在一起，改成只放大最有信息量的一档（约 +17%）。
只对 meta 写 copies / tier，make_splits.py 在训练项目上按 copies 复制；开发集、测试集不受影响。"""
import sys, os, json, collections
D = sys.argv[1]; a = sys.argv[2:]
src = os.path.join(D, a[0] if len(a) > 0 else 'out_rft/samples.jsonl'); tf = os.path.join(D, a[1] if len(a) > 1 else 'out_rft/tiers.jsonl'); dst = os.path.join(D, a[2] if len(a) > 2 else 'out_tier/samples.jsonl')
os.makedirs(os.path.dirname(dst), exist_ok=True)
h = {}
for l in open(tf, encoding='utf-8'):
    t = json.loads(l); h[t['id']] = sum(min(x, 5) for x in t['hits']) / (5 * max(1, len(t['hits'])))
cnt = collections.Counter()
with open(dst, 'w', encoding='utf-8') as fo:
    for l in open(src, encoding='utf-8'):
        r = json.loads(l); x = h.get(r['id'])
        if x is None: tier, c = '无采样结果', 1
        elif x > 0.6: tier, c = '稳定', 1
        elif x > 0.2: tier, c = '不稳定（能做对）', 2
        elif x > 0: tier, c = '偶尔命中（较难）', 1
        else: tier, c = '从未命中', 1
        r['meta']['tier'] = tier; r['meta']['copies'] = c; cnt[tier] += 1
        fo.write(json.dumps(r, ensure_ascii=False) + '\n')
print(dict(cnt))
