#!/usr/bin/env bash
# 云机器环境搭建（精简版：单卡 80GB，数据盘 50GB 也够用）。
# 用法：bash train/setup_env.sh [阶段 ...]；不带参数等于 all。阶段：
#   check     查 GPU、磁盘、Python、PyTorch，磁盘不足时提示
#   clone     克隆本仓库和 LLaMA-Factory 到数据盘
#   model     下载 MiniCPM-V 4.5 权重到数据盘（约 17GB，可断点续传）
#   train     训练环境：复用镜像自带的 PyTorch，装 LLaMA-Factory（不重复装 torch，省约 8GB 系统盘）
#   flashattn 可选：装 flash-attn（A800 可用；失败就把 yaml 里 flash_attn 改成 sdpa）
#   vllm      评测环境：单独的虚拟环境装 vLLM（和训练的 torch 版本隔离）
#   link      把数据和训练配置链接到 LLaMA-Factory 目录，打印训练命令
#   verify    核对：LLaMA-Factory 是否登记了 MiniCPM-V 4.5、分词器/处理器能否加载、数据文件是否齐全
# 训练数据 data/train、评测输入 data/eval、分词器 data/tokenizer 已在仓库里，clone 即得。
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$HERE/env.sh"
say() { printf '\n==== %s ====\n' "$*"; }
need_turbo() { [ -f /etc/network_turbo ] && [ "${USE_TURBO:-1}" = 1 ] && source /etc/network_turbo >/dev/null 2>&1 && echo "（已启用 AutoDL 学术加速）"; }
stop_turbo() { unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY 2>/dev/null || true; }

stage_check() {
  say "check"
  command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || echo "没有 nvidia-smi：当前可能是无卡模式或不是 GPU 机器"
  python3 --version; python3 -c "import torch;print('torch',torch.__version__,'cuda',torch.version.cuda,'gpu',torch.cuda.is_available())" 2>&1 | tail -1
  df -h / "$DATA_DISK" 2>/dev/null | cat
  local free_gb; free_gb=$(df -BG --output=avail "$DATA_DISK" 2>/dev/null | tail -1 | tr -dc '0-9')
  [ -n "${free_gb:-}" ] && { [ "$free_gb" -lt 40 ] && echo "警告：数据盘可用 ${free_gb}GB，低于精简方案所需的约 40GB，请先扩容或清理" || echo "数据盘可用 ${free_gb}GB，够用"; }
  echo "HF_HOME=$HF_HOME  PIP_CACHE_DIR=$PIP_CACHE_DIR  MODEL_DIR=$MODEL_DIR"
}

stage_clone() {
  say "clone"; need_turbo
  [ -d "$REPO_DIR/.git" ] && git -C "$REPO_DIR" pull --ff-only || git clone "$REPO_URL" "$REPO_DIR"
  [ -d "$LF_DIR/.git" ] || git clone --depth 1 https://github.com/hiyouga/LLaMA-Factory.git "$LF_DIR"
  stop_turbo
}

stage_model() {
  say "model（约 17GB）"
  [ -x "$VENV_TRAIN/bin/python" ] && PY="$VENV_TRAIN/bin/python" || PY=python3
  $PY -c "import huggingface_hub" 2>/dev/null || $PY -m pip install -q huggingface_hub
  stop_turbo
  echo "镜像：$HF_ENDPOINT"
  $PY - <<PYEOF || { echo "HF 下载失败，改用魔搭：pip install modelscope && modelscope download --model OpenBMB/MiniCPM-V-4_5 --local_dir $MODEL_DIR"; exit 1; }
from huggingface_hub import snapshot_download
p = snapshot_download('openbmb/MiniCPM-V-4_5', local_dir='$MODEL_DIR', max_workers=4)
print('已下载到', p)
PYEOF
  du -sh "$MODEL_DIR"
}

stage_train() {
  say "train 环境"; need_turbo
  [ -d "$VENV_TRAIN" ] || python3 -m venv --system-site-packages "$VENV_TRAIN"
  source "$VENV_TRAIN/bin/activate"
  pip install -U pip wheel >/dev/null
  pip install -e "$LF_DIR[metrics]" && pip install tensorboard
  python -c "import torch,transformers,peft;print('torch',torch.__version__,'transformers',transformers.__version__,'peft',peft.__version__)"
  stop_turbo
}

stage_flashattn() {
  say "flash-attn（可选）"; need_turbo
  source "$VENV_TRAIN/bin/activate"
  MAX_JOBS=${MAX_JOBS:-4} pip install flash-attn --no-build-isolation || echo "flash-attn 安装失败：把 train/*.yaml 里的 flash_attn 改成 sdpa 即可，不影响训练"
  stop_turbo
}

stage_vllm() {
  say "vllm 评测环境（单独虚拟环境，约 10~15GB）"; need_turbo
  [ -d "$VENV_VLLM" ] || python3 -m venv "$VENV_VLLM"
  source "$VENV_VLLM/bin/activate"
  pip install -U pip >/dev/null
  pip install --no-cache-dir vllm
  python -c "import vllm,torch;print('vllm',vllm.__version__,'torch',torch.__version__)"
  stop_turbo
}

stage_link() {
  say "link"
  mkdir -p "$LF_DIR/data"
  for d in train; do
    [ -d "$REPO_DIR/data/$d" ] && ln -sfn "$REPO_DIR/data/$d" "$LF_DIR/data/$d" || echo "缺少 $REPO_DIR/data/$d：先把本地 data/train 上传到这里"
  done
  ln -sfn "$REPO_DIR/train" "$LF_DIR/train"
  cat <<TXT
训练命令（在 $LF_DIR 下，先 source $VENV_TRAIN/bin/activate）：
  cd $LF_DIR && source $VENV_TRAIN/bin/activate
  llamafactory-cli train train/smoke.yaml model_name_or_path=$MODEL_DIR
  llamafactory-cli train train/sft_think.yaml model_name_or_path=$MODEL_DIR
评测服务（另开会话，source $VENV_VLLM/bin/activate）：
  vllm serve $MODEL_DIR --served-model-name base --trust-remote-code --max-model-len 16384 --enable-lora --lora-modules ft=<LoRA 目录>
TXT
}

stage_verify() {
  say "verify"
  source "$VENV_TRAIN/bin/activate" 2>/dev/null || true
  grep -n "MiniCPM-V-4.5" "$LF_DIR/src/llamafactory/extras/constants.py" | head -2 || echo "LLaMA-Factory 未登记 MiniCPM-V-4.5：换新版本或手动指定"
  grep -n 'name="minicpm_v"' "$LF_DIR/src/llamafactory/data/template.py" | head -1
  python - <<PYEOF
import json, os, glob
m = '$MODEL_DIR'
try:
    from transformers import AutoTokenizer, AutoProcessor
    tk = AutoTokenizer.from_pretrained(m, trust_remote_code=True)
    print('分词器 OK，词表', len(tk))
    try:
        AutoProcessor.from_pretrained(m, trust_remote_code=True); print('处理器 OK')
    except Exception as e: print('处理器加载失败（看缺哪个依赖，pip 补装）：', repr(e)[:300])
except Exception as e: print('分词器加载失败：', repr(e)[:300])
d = '$REPO_DIR/data/train'
need = ['dataset_info.json', 'audit_train_think.json', 'rule_L3-07_train_think.json', 'audit_dev_think.json', 'rule_L3-07_dev_tag.json']
for f in need:
    p = os.path.join(d, f)
    n = len(json.load(open(p, encoding='utf-8'))) if p.endswith('.json') and 'info' not in f and os.path.exists(p) else None
    print(('OK  ' if os.path.exists(p) else '缺失'), f, n if n is not None else '')
PYEOF
}

STAGES=("$@"); [ ${#STAGES[@]} -eq 0 ] && STAGES=(check clone train model vllm link verify)
for s in "${STAGES[@]}"; do
  case $s in check|clone|model|train|flashattn|vllm|link|verify) "stage_$s" ;; all) for x in check clone train model vllm link verify; do "stage_$x"; done ;; *) echo "未知阶段 $s"; exit 2 ;; esac
done
say "完成：${STAGES[*]}"
