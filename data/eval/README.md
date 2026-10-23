# 评测流程（开发集、测试集）

1. 生成评测输入（本地，数据变动后重跑）：`python3 -I scripts/eval_make_inputs.py data`
   → `audit_dev|test.jsonl`（小节审核）、`rule_L3-07_dev|test_card|tag|none.jsonl`（L3-07 专项，三种输入版本）。
2. 云上起服务（vLLM，OpenAI 兼容接口）：
   - 基线：`vllm serve <原版 MiniCPM-V 4.5> --served-model-name base --max-model-len 16384`
   - 微调后：加 `--enable-lora --lora-modules ft=<LoRA 目录>`，评测时 `--model ft`。
3. 跑推理：`python3 -I scripts/eval_run.py --inputs data/eval/audit_dev.jsonl --out data/eval/pred_<名>_audit_dev.jsonl --model <名> --thinking on|off`
   原版模型两种思考模式都测；微调后的模型（带推理和不带推理两个版本）都用 `--thinking on`（提示末尾不预填思考标记，由模型自己生成思考段，见 train/README.md 第 3 节）。
4. 打分：`python3 -I scripts/eval_score.py --inputs data/eval/audit_dev.jsonl --pred data/eval/pred_<名>_audit_dev.jsonl --name <名>_audit_dev`
   → `score_<名>.json|md`；audit 另出 `judge_<名>.jsonl`（预测里没有匹配上标准意见的额外意见，抽样人工复核）。

## 指标怎么读
- 格式类（解析率、字段完整率、引文逐字率、规则编号在审核重点内、意见不含条文编号）：应接近 100%，低了先查模板和输出长度。
- 覆盖类：规则命中 ≥ 证据命中 ≈ 文本命中；`covered`（综合命中）是主指标。文本命中用二字组召回 ≥ 0.40 作代理，只能比较不同模型的相对好坏，不等于专家认可。
- 额外意见：标准答案只含专家提过的意见，额外意见不等于误报；以 judge 文件抽样复核后再算误报率。
- L3-07：逐项判断准确率、各类准确率和混淆矩阵、汇总 F1；card / tag / none 三个版本的差距反映规则是否已内化。

## 使用规则
- 开发集：选检查点、超参、思考模式，可以反复使用。
- 测试集：只在最后用一次，不据此调参。
- 通过条件要在看到基线结果之前定下（方案 3.4）。
