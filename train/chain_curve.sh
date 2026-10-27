#!/usr/bin/env bash
# 学习曲线实验：25% / 50% 训练项目，其余同训练 A（学习率 1e-4、3 轮、种子 42）。等实验 B（ALLDONE6）结束后接着跑。
W=/root/autodl-tmp/work; LF=$W/LLaMA-Factory; PY=/root/miniconda3/bin/python; OUT=$W/eval_out; F=$W/finetuning
while ! grep -q ALLDONE6 $W/chain_expB.log 2>/dev/null; do sleep 30; done
echo "[$(date +%H:%M)] 开始学习曲线：关闭 vLLM，等待 GPU 空闲"
pkill -f "vllm serve"; sleep 15
while nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '{exit !($1>1000)}'; do sleep 5; done
cd $LF
for n in c25 c50; do
  bash -lc "source $W/venv_train/bin/activate && source $F/train/env.sh && llamafactory-cli train $F/train/sft_$n.yaml model_name_or_path=\$MODEL_DIR flash_attn=sdpa save_only_model=true dataset_dir=$F/data/train_$n" > $W/train_curve_$n.log 2>&1
  echo "[$(date +%H:%M)] 训练 $n 结束"
done
MODS=""
for n in 25 50; do S=$LF/saves/minicpmv45/lora/curve${n}_lr1e-4_e3_s42
  for i in 2 3; do CK=$(ls -d $S/checkpoint-* | sort -t- -k2 -n | sed -n ${i}p); MODS="$MODS c${n}e$i=$CK"; done
done
setsid nohup bash -lc "source $W/venv_vllm/bin/activate && source $F/train/env.sh && vllm serve \$MODEL_DIR --served-model-name base --trust-remote-code --max-model-len 16384 --gpu-memory-utilization 0.85 --enable-lora --max-lora-rank 32 --max-loras 4 --lora-modules $MODS --port 8000" > $W/vllm_serve7.log 2>&1 < /dev/null &
until curl -s -m 5 localhost:8000/v1/models | grep -q c50e3; do sleep 10; done
echo "[$(date +%H:%M)] vLLM 就绪，评测学习曲线"
cd $F
for m in c25e2 c25e3 c50e2 c50e3; do
  for kind in audit_dev rule_L3-07_dev_tag; do
    $PY -I scripts/eval_run.py --inputs data/eval/$kind.jsonl --out $OUT/pred_${m}_$kind.jsonl --model $m --thinking on --max-tokens 6144 --workers 8 > /dev/null 2>&1
    $PY -I scripts/eval_score.py --inputs data/eval/$kind.jsonl --pred $OUT/pred_${m}_$kind.jsonl --name ${m}_$kind --out $OUT > /dev/null
  done
  echo "[$(date +%H:%M)] 评测 $m 完成"
done
echo ALLDONE7
