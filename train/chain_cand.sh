#!/usr/bin/env bash
# 候选意见流水线 第 2 步：用 e3 对“没有专家意见的小节”各采样 4 次（temperature 0.7，带预算强制）。
# 等 chain_smoke_tier.sh 结束（ALLDONE10）后再开始：关掉那条链留下的 vLLM，只加载 e3。
W=/root/autodl-tmp/work; LF=$W/LLaMA-Factory; PY=/root/miniconda3/bin/python; OUT=$W/eval_out; F=$W/finetuning
while ! grep -q ALLDONE10 $W/chain_smoke_tier.log 2>/dev/null; do sleep 30; done
echo "[$(date +%H:%M)] 前一条链已结束，切换 vLLM 到 e3"
pkill -f "vllm serve"; sleep 15
while nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '{exit !($1>1000)}'; do sleep 5; done
CK=$LF/saves/minicpmv45/lora/think_lr1e-4_s42/checkpoint-363
cd $F
setsid nohup bash -lc "source $W/venv_vllm/bin/activate && source $F/train/env.sh && vllm serve \$MODEL_DIR --served-model-name base --trust-remote-code --max-model-len 16384 --gpu-memory-utilization 0.85 --enable-lora --max-lora-rank 32 --max-loras 4 --lora-modules e3=$CK --port 8000" > $W/vllm_serve12.log 2>&1 < /dev/null &
until curl -s -m 5 localhost:8000/v1/models | grep -q '"e3"'; do sleep 10; done
echo "[$(date +%H:%M)] 开始候选意见采样（$(wc -l < data/cand/cand_inputs.jsonl) 个小节 × 4 次）"
$PY -I scripts/eval_run.py --inputs data/cand/cand_inputs.jsonl --out $OUT/cand_e3.jsonl --model e3 --thinking on --max-tokens 6144 --budget-think 3800 --n 4 --temperature 0.7 --workers 8 > $W/cand.log 2>&1
echo "[$(date +%H:%M)] 采样完成"
echo CANDDONE
