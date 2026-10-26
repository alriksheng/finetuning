#!/usr/bin/env bash
# 训练 A + 反事实“无问题”样本（数据优化实验）：等学习曲线（ALLDONE7）结束后训练，并和训练 A 一起在开发集上评测命中率与误报。
W=/root/autodl-tmp/work; LF=$W/LLaMA-Factory; PY=/root/miniconda3/bin/python; OUT=$W/eval_out; F=$W/finetuning
while ! grep -q ALLDONE7 $W/chain_curve.log 2>/dev/null; do sleep 30; done
echo "[$(date +%H:%M)] 开始数据优化实验：关闭 vLLM，等待 GPU 空闲"
pkill -f "vllm serve"; sleep 15
while nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '{exit !($1>1000)}'; do sleep 5; done
cd $LF
bash -lc "source $W/venv_train/bin/activate && source $F/train/env.sh && llamafactory-cli train $F/train/sft_fix.yaml model_name_or_path=\$MODEL_DIR flash_attn=sdpa save_only_model=true dataset_dir=$F/data/train_fix" > $W/train_fix.log 2>&1
echo "[$(date +%H:%M)] 训练 fix 结束"
S=$LF/saves/minicpmv45/lora/expFix_lr1e-4_e3_s42; A=$LF/saves/minicpmv45/lora/think_lr1e-4_s42
MODS="f2=$(ls -d $S/checkpoint-* | sort -t- -k2 -n | sed -n 2p) f3=$(ls -d $S/checkpoint-* | sort -t- -k2 -n | sed -n 3p) a2=$A/checkpoint-242 a3=$A/checkpoint-363"
setsid nohup bash -lc "source $W/venv_vllm/bin/activate && source $F/train/env.sh && vllm serve \$MODEL_DIR --served-model-name base --trust-remote-code --max-model-len 16384 --gpu-memory-utilization 0.85 --enable-lora --max-lora-rank 32 --max-loras 4 --lora-modules $MODS --port 8000" > $W/vllm_serve8.log 2>&1 < /dev/null &
until curl -s -m 5 localhost:8000/v1/models | grep -q a3; do sleep 10; done
echo "[$(date +%H:%M)] vLLM 就绪，评测数据优化实验"
cd $F
for m in f2 f3 a2 a3; do
  for kind in audit_dev rule_L3-07_dev_tag; do
    [ -f $OUT/score_${m}_$kind.json ] && continue
    $PY -I scripts/eval_run.py --inputs data/eval/$kind.jsonl --out $OUT/pred_${m}_$kind.jsonl --model $m --thinking on --max-tokens 6144 --workers 8 > /dev/null 2>&1
    $PY -I scripts/eval_score.py --inputs data/eval/$kind.jsonl --pred $OUT/pred_${m}_$kind.jsonl --name ${m}_$kind --out $OUT > /dev/null
  done
  for kind in audit_dev_neg audit_dev_negp; do
    $PY -I scripts/eval_run.py --inputs data/eval/$kind.jsonl --out $OUT/pred_${m}_$kind.jsonl --model $m --thinking on --max-tokens 6144 --workers 8 > /dev/null 2>&1
    $PY -I scripts/eval_neg.py --inputs data/eval/$kind.jsonl --pred $OUT/pred_${m}_$kind.jsonl --name ${m}_$kind --out $OUT > /dev/null
  done
  $PY -I scripts/eval_score.py --inputs data/eval/audit_dev_negp.jsonl --pred $OUT/pred_${m}_audit_dev_negp.jsonl --name ${m}_audit_dev_negp --out $OUT > /dev/null
  echo "[$(date +%H:%M)] 评测 $m 完成"
done
echo ALLDONE8
