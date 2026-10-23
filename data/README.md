# 数据目录说明

样本生成的规则、流程和核验要求统一见 **`样本生成标准.md`**，本文件只列目录。

```
specs/                 项目规格（样本的唯一来源）
  P001.py … P005.py      每个项目：小节、比对包、事实卡、样本与要点、推理过程
  spec_lib.py            从切分结果和对应表生成小节表与条文对应
  projects.json          项目信息（名称、部门、金额、报告版本、评审时点、分组、标注方式）
  clause_map.yaml        章节/比对包 → 条文对应表（经常性 / 新建工程 / 政策）
  focus_map.yaml         章节/比对包 → 审核重点对应表（同上三套）
  sections/              报告切分结果（section_report.py）
  review_points/         评审意见拆分结果（split_review.py）
  试跑报告.md             三类项目试跑记录
raw/reports, raw/reviews  报告文本与评审意见文本（核验逐字的依据）
clauses/clauses.json   条文包（build_clauses.py 按起止标记切片）；clauses_general.json 为通用数据用
rules/rules.yaml       规则库（待专家确认）；rules/cards、rules/L3-07 为规则专项
style/                 公文风格指南（只约束模型撰写的意见）与语料
match/                 报告与评审意见匹配结果（112 个可用项目）
feedback/              专家反馈原件
out/                   构建输出：samples.jsonl、samples_answer_only.jsonl、candidates_no_issue.jsonl、
                       rejected.jsonl、train_sharegpt.json、preview.md、report.txt、专家确认表_<轮次>.xlsx
out_rules/             规则专项样本
splits.yaml, train/    数据划分配置与训练文件
batch/                 批量生成：manifest.csv（项目清单与预处理问题）、标注指令.md、notes/（每个项目的结果说明）、logs/（用时和费用）
annotations_general、annotations_logic、annotations_jecqa、ext、out_general、out_logic、out_jecqa
                       通用逻辑数据，演示期（实验 A）不使用
```

完整重建：

```bash
python3 -I scripts/build.py data && python3 -I scripts/build_rule_samples.py data L3-07 && python3 -I scripts/make_splits.py data && python3 -I scripts/test_checks.py
```
