#!/usr/bin/env bash
# ① DPO 冒烟测试（50 对，在 e3 上继续训练 1 轮）并在开发集上看有没有崩 → ② 分层 SFT（含 66 条拒绝采样样本）从基座重训并评测。
W=/root/autodl-tmp/work; LF=$W/LLaMA-Factory; PY=/root/miniconda3/bin/python; OUT=$W/eval_out; F=$W/finetuning
serve() {  # $1=日志名 $2=lora-modules 字符串 $3=等待的模块名
  setsid nohup bash -lc "source $W/venv_vllm/bin/activate && source $F/train/env.sh && vllm serve \$MODEL_DIR --served-model-name base --trust-remote-code --max-model-len 16384 --gpu-memory-utilization 0.85 --enable-lora --max-lora-rank 32 --max-loras 4 --lora-modules $2 --port 8000" > $W/$1 2>&1 < /dev/null &
  until curl -s -m 5 localhost:8000/v1/models | grep -q $3; do sleep 10; done
}
evalm() {  # $1=模型名 $2..=评测集
  m=$1; shift
  for kind in "$@"; do
    case $kind in
      audit_dev|rule_L3-07_dev_tag)
        $PY -I scripts/eval_run.py --inputs data/eval/$kind.jsonl --out $OUT/pred_${m}_$kind.jsonl --model $m --thinking on --max-tokens 6144 --workers 8 > /dev/null 2>&1
        $PY -I scripts/eval_score.py --inputs data/eval/$kind.jsonl --pred $OUT/pred_${m}_$kind.jsonl --name ${m}_$kind --out $OUT > /dev/null ;;
      *)
        $PY -I scripts/eval_run.py --inputs data/eval/$kind.jsonl --out $OUT/pred_${m}_$kind.jsonl --model $m --thinking on --max-tokens 6144 --workers 8 > /dev/null 2>&1
        $PY -I scripts/eval_neg.py --inputs data/eval/$kind.jsonl --pred $OUT/pred_${m}_$kind.jsonl --name ${m}_$kind --out $OUT > /dev/null ;;
    esac
  done
}
echo "[$(date +%H:%M)] 关闭 vLLM，等待 GPU 空闲"
pkill -f "vllm serve"; sleep 15
while nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '{exit !($1>1000)}'; do sleep 5; done
cd $LF
echo "[$(date +%H:%M)] ① DPO 冒烟测试开始"
bash -lc "source $W/venv_train/bin/activate && source $F/train/env.sh && llamafactory-cli train $F/train/dpo.yaml model_name_or_path=\$MODEL_DIR ref_model=\$MODEL_DIR flash_attn=sdpa save_only_model=true dataset_dir=$F/data/dpo_smoke gradient_accumulation_steps=2 num_train_epochs=1 logging_steps=2 output_dir=saves/minicpmv45/lora/dpo_smoke" > $W/train_dpo_smoke.log 2>&1
echo "[$(date +%H:%M)] DPO 冒烟训练结束"
S=$LF/saves/minicpmv45/lora/dpo_smoke; CK=$(ls -d $S/checkpoint-* 2>/dev/null | sort -t- -k2 -n | tail -1)
if [ -n "$CK" ]; then
  cd $F; serve vllm_serve10.log "sm=$CK" sm
  evalm sm audit_dev audit_dev_neg audit_dev_negp
  echo "[$(date +%H:%M)] 冒烟模型评测完成"
  pkill -f "vllm serve"; sleep 15
  while nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '{exit !($1>1000)}'; do sleep 5; done
else echo "[$(date +%H:%M)] 冒烟训练没有产出检查点，见 train_dpo_smoke.log"; fi
echo SMOKEDONE
cd $LF
echo "[$(date +%H:%M)] ② 分层 SFT 开始"
bash -lc "source $W/venv_train/bin/activate && source $F/train/env.sh && llamafactory-cli train $F/train/sft_tier.yaml model_name_or_path=\$MODEL_DIR flash_attn=sdpa save_only_model=true dataset_dir=$F/data/train_tier" > $W/train_tier.log 2>&1
echo "[$(date +%H:%M)] 分层 SFT 训练结束"
T=$LF/saves/minicpmv45/lora/expTier_lr1e-4_e3_s42; MODS=""
for i in 1 2 3; do MODS="$MODS t$i=$(ls -d $T/checkpoint-* | sort -t- -k2 -n | sed -n ${i}p)"; done
cd $F; serve vllm_serve11.log "$MODS" t3
echo "[$(date +%H:%M)] vLLM 就绪，评测分层 SFT"
for m in t1 t2 t3; do evalm $m audit_dev rule_L3-07_dev_tag; echo "[$(date +%H:%M)] 评测 $m 完成"; done
echo ALLDONE10
