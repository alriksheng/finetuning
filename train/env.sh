# 云上环境变量：所有大文件和缓存都放数据盘（系统盘只有 30GB）。每次登录后 `source train/env.sh`。
# AutoDL 的数据盘是 /root/autodl-tmp；其他平台改 DATA_DISK。
export DATA_DISK=${DATA_DISK:-/root/autodl-tmp}
export WORK=$DATA_DISK/work
export HF_HOME=$DATA_DISK/hf                       # HuggingFace 缓存，默认在系统盘 ~/.cache，会撑满
export HF_HUB_CACHE=$HF_HOME/hub
export MODELSCOPE_CACHE=$DATA_DISK/modelscope
export PIP_CACHE_DIR=$DATA_DISK/pip-cache
export TMPDIR=$DATA_DISK/tmp
export TORCH_HOME=$DATA_DISK/torch
export HF_ENDPOINT=${HF_ENDPOINT:-https://hf-mirror.com}     # 国内下载镜像；能直连 huggingface.co 时可 export HF_ENDPOINT=https://huggingface.co
export MODEL_DIR=$WORK/models/MiniCPM-V-4_5
export REPO_URL=${REPO_URL:-https://github.com/alriksheng/finetuning.git}
export REPO_DIR=$WORK/finetuning
export LF_DIR=$WORK/LLaMA-Factory
export VENV_TRAIN=$WORK/venv_train
export VENV_VLLM=$WORK/venv_vllm
mkdir -p "$WORK" "$HF_HOME" "$MODELSCOPE_CACHE" "$PIP_CACHE_DIR" "$TMPDIR" "$TORCH_HOME" "$WORK/models"
