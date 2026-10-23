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
a = ap.parse_args()
key = os.environ.get('OPENAI_API_KEY', 'EMPTY')
rows = [json.loads(l) for l in open(a.inputs, encoding='utf-8')]
done = {json.loads(l)['id'] for l in open(a.out, encoding='utf-8')} if os.path.exists(a.out) else set()
todo = [r for r in rows if r['id'] not in done]; lock = threading.Lock()
print(f'共 {len(rows)} 条，已完成 {len(done)}，待跑 {len(todo)}', flush=True)

def call(r):
    body = dict(model=a.model, messages=[{'role': 'system', 'content': r['system']}, {'role': 'user', 'content': r['prompt']}],
                max_tokens=a.max_tokens, temperature=a.temperature, chat_template_kwargs={'enable_thinking': a.thinking == 'on'})
    req = urllib.request.Request(a.base_url.rstrip('/') + '/chat/completions', json.dumps(body).encode(), {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    t = time.time()
    try:
        d = json.load(urllib.request.urlopen(req, timeout=a.timeout)); ch = d['choices'][0]
        rec = dict(id=r['id'], output=ch['message'].get('content') or '', reasoning=ch['message'].get('reasoning_content'), finish=ch.get('finish_reason'), usage=d.get('usage'), sec=round(time.time() - t, 1))
    except Exception as e:
        rec = dict(id=r['id'], output='', error=str(e)[:300], sec=round(time.time() - t, 1))
    with lock:
        with open(a.out, 'a', encoding='utf-8') as f: f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return rec

with cf.ThreadPoolExecutor(a.workers) as ex:
    for i, rec in enumerate(ex.map(call, todo), 1):
        if i % 10 == 0 or rec.get('error'): print(f'{i}/{len(todo)} {rec["id"]} {rec.get("finish") or rec.get("error")}', flush=True)
