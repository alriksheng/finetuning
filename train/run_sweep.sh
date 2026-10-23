#!/usr/bin/env bash
# 方案 3.2：学习率 1e-4 / 2e-4 × 两个种子；think 版本为主。在 LLaMA-Factory 目录下运行。
# 用法：bash train/run_sweep.sh [think|nothink]
set -euo pipefail
V=${1:-think}
for LR in 1.0e-4 2.0e-4; do
  for SEED in 42 43; do
    llamafactory-cli train train/sft_${V}.yaml learning_rate=${LR} seed=${SEED} \
      output_dir=saves/minicpmv45/lora/${V}_lr${LR}_s${SEED}
  done
done
