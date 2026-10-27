"""对评测输入跑推理（OpenAI 兼容接口，如 vLLM serve）。只用标准库。
Usage: python3 -I eval_run.py --inputs data/eval/audit_dev.jsonl --out data/eval/pred_<名>_audit_dev.jsonl --model <served-model-name>
         [--base-url http://localhost:8000/v1] [--thinking on|off] [--max-tokens 6144] [--workers 4] [--temperature 0]
断点续跑：已在 --out 中的 id 会跳过。thinking 通过 chat_template_kwargs.enable_thinking 传给 vLLM（Qwen3 模板）。
基线（原版 MiniCPM-V 4.5）：vllm serve 原模型；微调后：vllm serve 原模型 --enable-lora --lora-modules <名>=<LoRA 目录>，--model 填 <名>。"""
import argparse, json, os, time, threading, urllib.request, concurrent.futures as cf
ap = argparse.ArgumentParser()
ap.add_argument('--inputs', required=True); ap.add_argument('--out', required=True); ap.add_argument('--model', required=True)
ap.add_argument('--base-url', default='http://localhost:8000/v1'); ap.add_argument('--thinking', choices=['on', 'off'], default='on')
ap.add_argument('--max-tokens', type=int, default=6144); ap.add_argument('--workers', type=int, default=4); ap.add_argument('--temperature', type=float, default=0.0)
ap.add_argument('--timeout', type=int, default=600)
ap.add_argument('--n', type=int, default=1, help='每条输入采样几次（多次采样投票用，需 temperature>0）；n>1 时预测记录里多一个 outputs 列表')
ap.add_argument('--budget-think', type=int, default=0, help='思考预算（token）：>0 时先限制生成长度，没写出 </think> 就截掉重复循环的部分，补上 </think> 再续写出 JSON（约束思考段死循环）')
ap.add_argument('--extra-tokens', type=int, default=2500, help='预算强制后续写的最大 token 数')
a = ap.parse_args()
key = os.environ.get('OPENAI_API_KEY', 'EMPTY')
rows = [json.loads(l) for l in open(a.inputs, encoding='utf-8')]
done = {json.loads(l)['id'] for l in open(a.out, encoding='utf-8')} if os.path.exists(a.out) else set()
todo = [r for r in rows if r['id'] not in done]; lock = threading.Lock()
print(f'共 {len(rows)} 条，已完成 {len(done)}，待跑 {len(todo)}', flush=True)

def post(path, body):
    req = urllib.request.Request(a.base_url.rstrip('/') + path, json.dumps(body).encode(), {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    return json.load(urllib.request.urlopen(req, timeout=a.timeout))

def cut_loop(t, w=20, rep=6):
    """找到最早出现在文中 ≥rep 次的 w 字片段（重复循环），在其首次出现处截断。"""
    from collections import Counter
    c = Counter(t[j:j + w] for j in range(0, max(0, len(t) - w)))
    for i in range(0, max(0, len(t) - w)):
        if c[t[i:i + w]] >= rep: return t[:i]
    return t

def force_json(r, partial):
    """预算强制：把（截掉循环后的）思考内容接上 </think>，用 completions 接口续写 JSON。提示拼法同 Qwen3 聊天模板（生成提示末尾带 <think>\\n）。"""
    think = cut_loop(partial).rstrip()
    prompt = f"<|im_start|>system\n{r['system']}<|im_end|>\n<|im_start|>user\n{r['prompt']}<|im_end|>\n<|im_start|>assistant\n<think>\n{think}\n</think>\n\n"
    d = post('/completions', dict(model=a.model, prompt=prompt, max_tokens=a.extra_tokens, temperature=a.temperature))
    return think + '\n</think>\n\n' + d['choices'][0]['text']

def call(r):
    body = dict(model=a.model, messages=[{'role': 'system', 'content': r['system']}, {'role': 'user', 'content': r['prompt']}],
                max_tokens=(a.budget_think or a.max_tokens), temperature=a.temperature, chat_template_kwargs={'enable_thinking': a.thinking == 'on'})
    if a.n > 1: body['n'] = a.n
    t = time.time()
    try:
        d = post('/chat/completions', body); outs, forced = [], 0
        for ch in d['choices']:
            o = ch['message'].get('content') or ''
            if a.budget_think and ch.get('finish_reason') == 'length' and '</think>' not in o: o = force_json(r, o); forced += 1
            outs.append(o)
        ch = d['choices'][0]
        rec = dict(id=r['id'], output=outs[0], reasoning=ch['message'].get('reasoning_content'), finish=ch.get('finish_reason'), usage=d.get('usage'), sec=round(time.time() - t, 1))
        if a.n > 1: rec['outputs'] = outs
        if forced: rec['forced'] = forced
    except Exception as e:
        rec = dict(id=r['id'], output='', error=str(e)[:300], sec=round(time.time() - t, 1))
    with lock:
        with open(a.out, 'a', encoding='utf-8') as f: f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return rec

with cf.ThreadPoolExecutor(a.workers) as ex:
    for i, rec in enumerate(ex.map(call, todo), 1):
        if i % 10 == 0 or rec.get('error'): print(f'{i}/{len(todo)} {rec["id"]} {rec.get("finish") or rec.get("error")}', flush=True)
