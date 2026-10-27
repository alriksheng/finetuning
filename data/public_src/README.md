# 公开数据题源（训练集 v3）

- 会计审计税务/items.jsonl：从 CMMLU（haonan-li/cmmlu，CC BY-NC 4.0）的 professional_accounting、construction_project_management 和 C-Eval（ceval/ceval-exam，CC BY-NC-SA 4.0）的 accountant、tax_accountant（dev+val，有答案）中按固定种子 42 抽取 281 题：会计 113、工程项目管理 60、注册会计师 54、税务师 54。2026-10-27 下载。
- 两个数据集均为非商业许可，本项目为非商业实验。
- 推理在 data/annotations_public/ 中逐题撰写，由 scripts/build_public_acct.py 核验后输出到 data/public/会计审计税务/。
