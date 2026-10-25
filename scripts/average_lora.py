"""LoRA 检查点平均（同一次训练不同轮次的检查点，相当于 SWA）。Usage: python3 average_lora.py <输出目录> <检查点目录1> <检查点目录2> ... [--weights w1,w2,...]
逐个张量取（加权）平均，A、B 矩阵分别平均。只适用于同一次训练（同一随机种子）的检查点：不同种子的 LoRA 初始化不同，A、B 不能直接平均。
输出目录里写 adapter_model.safetensors 和 adapter_config.json，可直接给 vLLM 的 --lora-modules 用。依赖 safetensors、torch。"""
import sys, os, json, shutil
from safetensors.torch import load_file, save_file
args = sys.argv[1:]; w = None
if '--weights' in args:
    i = args.index('--weights'); w = [float(x) for x in args[i + 1].split(',')]; args = args[:i] + args[i + 2:]
out, dirs = args[0], args[1:]
w = w or [1.0] * len(dirs); s = sum(w); w = [x / s for x in w]
sds = [load_file(os.path.join(d, 'adapter_model.safetensors')) for d in dirs]
keys = list(sds[0])
assert all(set(sd) == set(keys) for sd in sds), '检查点的张量名不一致'
avg = {k: sum(wi * sd[k].float() for wi, sd in zip(w, sds)).to(sds[0][k].dtype).contiguous() for k in keys}
os.makedirs(out, exist_ok=True)
save_file(avg, os.path.join(out, 'adapter_model.safetensors'), metadata={'format': 'pt'})
shutil.copy(os.path.join(dirs[0], 'adapter_config.json'), os.path.join(out, 'adapter_config.json'))
json.dump(dict(sources=dirs, weights=w), open(os.path.join(out, 'averaged_from.json'), 'w'), ensure_ascii=False, indent=1)
print(f'已平均 {len(dirs)} 个检查点 → {out}（{len(keys)} 个张量）')
