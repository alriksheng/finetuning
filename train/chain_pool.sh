#!/usr/bin/env bash
# 候选池采样：用没见过这些项目的模型（c50e3 对 49 个项目，c25e3 对 24 个项目）对训练项目的小节各采样 5 次（temperature 0.7，带预算强制）。
# 学习曲线（ALLDONE7）结束后 vLLM 还开着（已加载 c25e2/c25e3/c50e2/c50e3），直接复用，不重启。
W=/root/autodl-tmp/work; PY=/root/miniconda3/bin/python; OUT=$W/eval_out; F=$W/finetuning
while ! grep -q ALLDONE7 $W/chain_curve.log 2>/dev/null; do sleep 30; done
until curl -s -m 5 localhost:8000/v1/models | grep -q c50e3; do sleep 10; done
echo "[$(date +%H:%M)] 开始候选池采样"
cd $F
$PY -I scripts/eval_run.py --inputs data/pool/pool_a.jsonl --out $OUT/pool_a_c50e3.jsonl --model c50e3 --thinking on --max-tokens 6144 --budget-think 3800 --n 5 --temperature 0.7 --workers 8 > $W/pool_a.log 2>&1
echo "[$(date +%H:%M)] pool_a（c50e3，49 个项目）完成"
$PY -I scripts/eval_run.py --inputs data/pool/pool_b.jsonl --out $OUT/pool_b_c25e3.jsonl --model c25e3 --thinking on --max-tokens 6144 --budget-think 3800 --n 5 --temperature 0.7 --workers 8 > $W/pool_b.log 2>&1
echo "[$(date +%H:%M)] pool_b（c25e3，24 个项目）完成"
echo POOLDONE
