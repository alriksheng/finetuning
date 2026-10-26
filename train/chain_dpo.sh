#!/usr/bin/env bash
# DPO：等候选池采样结束（POOLDONE）且偏好对已上传（dpo_data_ready），训练，然后在开发集上评测 DPO 检查点与训练 A（e3）。
W=/root/autodl-tmp/work; LF=$W/LLaMA-Factory; PY=/root/miniconda3/bin/python; OUT=$W/eval_out; F=$W/finetuning
while ! grep -q POOLDONE $W/chain_pool.log 2>/dev/null || [ ! -f $W/dpo_data_ready ]; do sleep 30; done
echo "[$(date +%H:%M)] 开始 DPO：关闭 vLLM，等待 GPU 空闲"
pkill -f "vllm serve"; sleep 15
while nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '{exit !($1>1000)}'; do sleep 5; done
cd $LF
bash -lc "source $W/venv_train/bin/activate && source $F/train/env.sh && llamafactory-cli train $F/train/dpo.yaml model_name_or_path=\$MODEL_DIR ref_model=\$MODEL_DIR flash_attn=sdpa save_only_model=true dataset_dir=$F/data/dpo" > $W/train_dpo.log 2>&1
echo "[$(date +%H:%M)] DPO 训练结束"
S=$LF/saves/minicpmv45/lora/dpo_lr2e-5_e2_s42; A=$LF/saves/minicpmv45/lora/think_lr1e-4_s42
MODS="p1=$(ls -d $S/checkpoint-* | sort -t- -k2 -n | sed -n 1p) p2=$(ls -d $S/checkpoint-* | sort -t- -k2 -n | sed -n 2p) a3=$A/checkpoint-363"
setsid nohup bash -lc "source $W/venv_vllm/bin/activate && source $F/train/env.sh && vllm serve \$MODEL_DIR --served-model-name base --trust-remote-code --max-model-len 16384 --gpu-memory-utilization 0.85 --enable-lora --max-lora-rank 32 --max-loras 4 --lora-modules $MODS --port 8000" > $W/vllm_serve9.log 2>&1 < /dev/null &
until curl -s -m 5 localhost:8000/v1/models | grep -q a3; do sleep 10; done
echo "[$(date +%H:%M)] vLLM 就绪，评测 DPO"
cd $F
for m in p1 p2 a3; do
  for kind in audit_dev rule_L3-07_dev_tag; do
    [ -f $OUT/score_${m}_$kind.json ] && continue
    $PY -I scripts/eval_run.py --inputs data/eval/$kind.jsonl --out $OUT/pred_${m}_$kind.jsonl --model $m --thinking on --max-tokens 6144 --workers 8 > /dev/null 2>&1
    $PY -I scripts/eval_score.py --inputs data/eval/$kind.jsonl --pred $OUT/pred_${m}_$kind.jsonl --name ${m}_$kind --out $OUT > /dev/null
  done
  for kind in audit_dev_neg audit_dev_negp; do
    $PY -I scripts/eval_run.py --inputs data/eval/$kind.jsonl --out $OUT/pred_${m}_$kind.jsonl --model $m --thinking on --max-tokens 6144 --workers 8 > /dev/null 2>&1
    $PY -I scripts/eval_neg.py --inputs data/eval/$kind.jsonl --pred $OUT/pred_${m}_$kind.jsonl --name ${m}_$kind --out $OUT > /dev/null
  done
  echo "[$(date +%H:%M)] 评测 $m 完成"
done
# 单次采样之外，再对 DPO 最后一轮做 5 次采样（带预算强制），与 e3 的 5 次采样比较投票效果
$PY -I scripts/eval_run.py --inputs data/eval/audit_dev.jsonl --out $OUT/pred_p2_n5_audit_dev.jsonl --model p2 --thinking on --max-tokens 6144 --budget-think 3800 --n 5 --temperature 0.7 --workers 6 > /dev/null 2>&1
echo "[$(date +%H:%M)] p2 的 5 次采样完成"
echo ALLDONE9
