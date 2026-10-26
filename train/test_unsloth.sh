#!/usr/bin/env bash
# Unsloth 加速试验（20 步对照）：同一份数据、同一随机种子，分别用 venv_train（基线）和 venv_unsloth（use_unsloth）跑 20 步，比较每步耗时和显存峰值。
# 需要 GPU 空闲（候选池采样结束、vLLM 关闭后再跑）。结果写入 $W/unsloth_test.log。
W=/root/autodl-tmp/work; LF=$W/LLaMA-Factory; F=$W/finetuning; OUT=$W/unsloth_test.log
cd $LF; : > $OUT
run() {  # $1=名称 $2=venv $3=附加参数
  echo "=== $1 $(date +%H:%M)" >> $OUT
  bash -lc "source $W/venv_$2/bin/activate && source $F/train/env.sh && /usr/bin/time -v llamafactory-cli train $F/train/sft_think.yaml model_name_or_path=\$MODEL_DIR flash_attn=sdpa save_only_model=true dataset_dir=$F/data/train max_steps=20 save_strategy=no eval_strategy=no output_dir=saves/minicpmv45/lora/tmp_$1 report_to=none $3" > $W/unsloth_test_$1.log 2>&1
  grep -E "train_runtime|train_samples_per_second|train_steps_per_second|Maximum resident|Unsloth|unsloth|Traceback|Error" $W/unsloth_test_$1.log | tail -8 >> $OUT
  python3 - <<PY >> $OUT
import json,glob
f=glob.glob("$LF/saves/minicpmv45/lora/tmp_$1/trainer_log.jsonl")
print(open(f[0]).read().strip().split("\n")[-1][:220] if f else "无 trainer_log")
PY
  nvidia-smi --query-gpu=memory.used --format=csv,noheader >> $OUT
}
run base train ""
run unsloth unsloth "use_unsloth=true"
echo UNSLOTHTEST_DONE >> $OUT
rm -rf $LF/saves/minicpmv45/lora/tmp_base $LF/saves/minicpmv45/lora/tmp_unsloth
