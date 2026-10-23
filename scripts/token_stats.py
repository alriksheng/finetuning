"""统计训练文件的 token 长度（用 MiniCPM-V 4.5 的真实分词器，按 Qwen3 聊天模板拼接）。
Usage: python3 -I token_stats.py <data_dir> [tokenizer_dir]      （需要 pip install tokenizers）
读 data/train/*_train_*.json，写 data/train/token_stats.txt 和 token_stats.json（逐样本长度，供选 cutoff_len 用）。"""
import sys, os, json, re, glob, statistics
from tokenizers import Tokenizer
DATA = sys.argv[1]; TOK = sys.argv[2] if len(sys.argv) > 2 else os.path.join(DATA, 'tokenizer')
tk = Tokenizer.from_file(os.path.join(TOK, 'tokenizer.json'))
n_tok = lambda t: len(tk.encode(t, add_special_tokens=False).ids)
LIMITS = (4096, 6144, 8192, 10240, 12288, 16384)

def render(row):
    """与 tokenizer_config 里的聊天模板一致：最后一条助手消息总是 <think>\\n推理\\n</think>\\n\\n正文。"""
    h, g = row['conversations'][0]['value'], row['conversations'][1]['value']
    if '</think>' in g:
        reasoning = g.split('</think>')[0].rstrip('\n').split('<think>')[-1].lstrip('\n'); content = g.split('</think>')[-1].lstrip('\n')
    else: reasoning, content = '', g
    prompt = f"<|im_start|>system\n{row['system']}<|im_end|>\n<|im_start|>user\n{h}<|im_end|>\n<|im_start|>assistant\n"
    resp = f"<think>\n{reasoning.strip(chr(10))}\n</think>\n\n{content.lstrip(chr(10))}<|im_end|>\n"
    return prompt, resp

def pct(v, q): v = sorted(v); return v[min(len(v) - 1, int(round(q / 100 * (len(v) - 1))))]
rep, out = [], {}
for f in sorted(glob.glob(os.path.join(DATA, 'train', '*_train_*.json'))):
    name = os.path.basename(f)[:-5]; rows = json.load(open(f, encoding='utf-8'))
    cache, tot, P, R = {}, [], [], []
    for r in rows:
        key = r['conversations'][0]['value'][:200] + r['conversations'][1]['value'][-200:] + str(len(r['conversations'][1]['value']))
        if key not in cache:
            p, s = render(r); cache[key] = (n_tok(p), n_tok(s))
        a, b = cache[key]; P.append(a); R.append(b); tot.append(a + b)
    out[name] = tot
    over = {L: sum(x > L for x in tot) for L in LIMITS}
    rep.append(f"{name}：{len(tot)} 条；总 token {sum(tot):,}（输入 {sum(P):,} + 回答 {sum(R):,}）；平均 {statistics.mean(tot):.0f}，中位 {pct(tot,50)}，P90 {pct(tot,90)}，P95 {pct(tot,95)}，P99 {pct(tot,99)}，最大 {max(tot)}；"
               f"回答平均 {statistics.mean(R):.0f}、最大 {max(R)}；超过 " + '、'.join(f'{L}: {n} 条({n / len(tot):.1%})' for L, n in over.items()))
txt = '\n'.join(rep); print(txt)
open(os.path.join(DATA, 'train', 'token_stats.txt'), 'w', encoding='utf-8').write(txt)
json.dump(out, open(os.path.join(DATA, 'train', 'token_stats.json'), 'w'), ensure_ascii=False)
