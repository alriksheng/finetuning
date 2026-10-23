# 云上训练说明（LLaMA-Factory + MiniCPM-V 4.5 LoRA）

## 1. 要上传到云机器的文件
- （数据已随仓库提供，克隆即得，不用再传；下面是各目录用途）
- `data/train/`：`dataset_info.json`，以及 `audit_train_think|nothink.json`、`rule_L3-07_train_think|nothink.json`、`audit_dev_*.json`、`rule_L3-07_dev_tag.json`（开发集损失用）。测试集文件不用上传训练机。
- `data/eval/`：评测输入（`eval_make_inputs.py` 的输出）。
- `scripts/eval_run.py`、`scripts/eval_score.py`、`scripts/checks.py` 不需要；评测脚本只用 `eval_run.py`（推理）和 `eval_score.py`（打分，可在本地做）。
- `train/` 下的 yaml 与本说明。
- 目录约定：在 LLaMA-Factory 根目录下放 `data/train/`、`train/`，yaml 里的 `dataset_dir: data/train` 即相对该目录。

## 2. 环境（单卡 80GB；数据盘 50GB 也够用）
用脚本搭，所有大文件和缓存都放数据盘（`/root/autodl-tmp`，脚本里 `DATA_DISK` 可改）：
```bash
git clone https://github.com/alriksheng/finetuning.git /root/autodl-tmp/work/finetuning      # 或先 bash train/setup_env.sh clone
cd /root/autodl-tmp/work/finetuning
bash train/setup_env.sh check            # GPU、磁盘、Python、PyTorch；数据盘可用不足 40GB 会警告
bash train/setup_env.sh clone train      # 克隆 LLaMA-Factory；训练环境复用镜像自带的 PyTorch，不重复装
bash train/setup_env.sh model            # 下载 MiniCPM-V 4.5（约 17GB，断点续传；默认走 hf-mirror，可改 HF_ENDPOINT）
bash train/setup_env.sh flashattn        # 可选；失败就把 yaml 里 flash_attn 改成 sdpa
bash train/setup_env.sh vllm             # 评测环境，单独虚拟环境
bash train/setup_env.sh link verify      # 链接数据与配置到 LLaMA-Factory 目录，核对版本、分词器、数据文件，并打印训练命令
```
- 每次重新登录后先 `source train/env.sh`。
- 模型已下载到本地目录，训练时用命令行覆盖：`llamafactory-cli train train/sft_think.yaml model_name_or_path=$MODEL_DIR`（`link` 阶段会把完整命令打印出来）。
- 版本核对：`verify` 会检查 LLaMA-Factory 是否登记了 `MiniCPM-V-4.5` 及模板 `minicpm_v`；MiniCPM-V 4.5 的处理器若报缺依赖，按报错补装，并以模型卡的 `transformers` 版本为准。
- 磁盘预算：系统盘约 30GB，放不下就别往系统盘装东西；数据盘约 35GB（模型 17、vLLM 环境 10~12、检查点与数据 5~8）。每轮评测后只留最好的检查点。

## 3. 思考标记怎么对齐（最容易出错）
- 训练数据的回答已经写成 Qwen3 原生格式：带推理版 `<think>\n推理\n</think>\n\n{JSON}`，不带推理版 `<think>\n\n</think>\n\n{JSON}`（`make_splits.py` 统一了 `</think>` 后空一行）。
- yaml 用 `template: minicpm_v`（ChatML，LLaMA-Factory 对 MiniCPM-V 4.5 的默认模板），它只拼接角色标记，**不会再添加或删除思考标记**，所以训练目标就是数据里写的回答。
- 因此训练后的模型**自己生成**思考段（带推理版是一段推理，不带推理版是空段）。推理评测时一律用 `eval_run.py --thinking on`（提示末尾不预填思考标记），带推理和不带推理两个版本都是。若用 `--thinking off`，Qwen3 模板会在提示里预填空思考段，与训练时它是回答的一部分不一致。原版模型（基线）两种都测。
- 冒烟测试时核对：预处理日志会打印第一条样本的 `inputs` 和 `label_ids`，应看到 `...<|im_start|>assistant\n` 之后才是 `<think>`，且 `<think>` 起算损失。
- 备选：如果 `minicpm_v` 模板在文本样本上报错或渲染异常，改用 `template: qwen3`（带推理版，需 `enable_thinking: true`）或 `qwen3_nothink`（不带推理版）；改后重做冒烟测试。

## 4. 冒烟测试（方案 3.2）
1. `llamafactory-cli train train/smoke.yaml`（10 条样本，30 步）。
2. 检查：模板渲染见上；损失下降；没有 OOM（`cutoff_len: 12288` 的显存占用，记下峰值）；没有样本被截断（日志里的截断提示）。
3. 用 vLLM 加载 LoRA：`vllm serve openbmb/MiniCPM-V-4_5 --served-model-name base --trust-remote-code --enable-lora --lora-modules ft=saves/minicpmv45/lora/smoke --max-model-len 16384`，对同一条训练样本用 vLLM 和 LLaMA-Factory 的 `llamafactory-cli chat`/`api` 各推理一次，输出应一致或几乎一致。
4. 用 `eval_run.py` 对 `data/eval/audit_dev.jsonl` 前几条试跑（`--limit` 未实现，可先截取前 5 行成小文件），确认输出能被 `eval_score.py` 解析。

## 5. 正式训练
- 一次：`llamafactory-cli train train/sft_think.yaml`（约 360 步，3 轮，检查点每轮一个）。
- 扫参：`bash train/run_sweep.sh think`（学习率 1e-4/2e-4 × 种子 42/43，共 4 次）。不带推理版同理：`bash train/run_sweep.sh nothink`。
- 不要把 think 和 nothink 数据合在一次训练里：内容相同，只是格式不同，是两个对照。
- 每个检查点评测：起 vLLM 挂 LoRA，跑 `eval_run.py` + `eval_score.py`，在开发集上比较综合命中、格式指标和 L3-07 准确率，**不按训练损失选**。选定后，可把开发集并回训练再训一次（测试集始终不动），最后只在测试集上评测一次。
- 训练量参考：带推理版每轮约 297 万 token，3 轮约 900 万 token；按每秒 2000~4000 token 估计，一次约 1~1.5 GPU 小时（需实测）。
