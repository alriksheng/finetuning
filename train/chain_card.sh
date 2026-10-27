#!/usr/bin/env bash
# 事实卡版训练（项目级事实卡，设计见 项目级事实卡设计.md）：与训练 A 同配置从基座重训 3 轮，输入的【事实卡】栏换成项目级卡；
# 评测：c1~c3 在带卡的开发集上评测，另外 e3 也在带卡的开发集上评测（看未训练过卡格式的模型遇到卡会怎样）；L3-07 不变。
W=/root/autodl-tmp/work; LF=$W/LLaMA-Factory; PY=/root/miniconda3/bin/python; OUT=$W/eval_out; F=$W/finetuning
serve() {  # $1=日志名 $2=lora-modules 字符串 $3=等待的模块名
  setsid nohup bash -lc "source $W/venv_vllm/bin/activate && source $F/train/env.sh && vllm serve \$MODEL_DIR --served-model-name base --trust-remote-code --max-model-len 16384 --gpu-memory-utilization 0.85 --enable-lora --max-lora-rank 32 --max-loras 4 --lora-modules $2 --port 8000" > $W/$1 2>&1 < /dev/null &
  until curl -s -m 5 localhost:8000/v1/models | grep -q $3; do sleep 10; done
}
echo "[$(date +%H:%M)] 关闭 vLLM，等待 GPU 空闲"
pkill -f "vllm serve"; sleep 15
while nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '{exit !($1>1000)}'; do sleep 5; done
cd $LF
echo "[$(date +%H:%M)] 事实卡版训练开始"
bash -lc "source $W/venv_train/bin/activate && source $F/train/env.sh && llamafactory-cli train $F/train/sft_card.yaml model_name_or_path=\$MODEL_DIR flash_attn=sdpa save_only_model=true dataset_dir=$F/data/train_card" > $W/train_card.log 2>&1
echo "[$(date +%H:%M)] 事实卡版训练结束"
T=$LF/saves/minicpmv45/lora/expCard_lr1e-4_e3_s42; MODS=""
for i in 1 2 3; do MODS="$MODS c$i=$(ls -d $T/checkpoint-* | sort -t- -k2 -n | sed -n ${i}p)"; done
MODS="$MODS e3=$LF/saves/minicpmv45/lora/think_lr1e-4_s42/checkpoint-363"
cd $F; serve vllm_serve13.log "$MODS" c3
echo "[$(date +%H:%M)] vLLM 就绪，评测事实卡版"
for m in c1 c2 c3 e3; do
  $PY -I scripts/eval_run.py --inputs data/eval/audit_dev_card.jsonl --out $OUT/pred_${m}_audit_dev_card.jsonl --model $m --thinking on --max-tokens 6144 --workers 8 > /dev/null 2>&1
  $PY -I scripts/eval_score.py --inputs data/eval/audit_dev_card.jsonl --pred $OUT/pred_${m}_audit_dev_card.jsonl --name ${m}_audit_dev_card --out $OUT > /dev/null
  if [ $m != e3 ]; then
    $PY -I scripts/eval_run.py --inputs data/eval/rule_L3-07_dev_tag.jsonl --out $OUT/pred_${m}_rule_L3-07_dev_tag.jsonl --model $m --thinking on --max-tokens 6144 --workers 8 > /dev/null 2>&1
    $PY -I scripts/eval_score.py --inputs data/eval/rule_L3-07_dev_tag.jsonl --pred $OUT/pred_${m}_rule_L3-07_dev_tag.jsonl --name ${m}_rule_L3-07_dev_tag --out $OUT > /dev/null
  fi
  echo "[$(date +%H:%M)] 评测 $m 完成"
done
echo ALLDONE11
