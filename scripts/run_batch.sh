#!/bin/zsh
# 批量标注：每个项目单独调用一次非交互的 Claude Code，按 data/batch/标注指令.md 生成样本，逐个顺序执行（避免同时改写构建输出）。
# Usage: scripts/run_batch.sh P006 P007 ...
# 日志：data/batch/logs/<P>.json（含用时、轮数、费用），结果说明：data/batch/notes/<P>.md
cd "$(dirname "$0")/.." || exit 1
mkdir -p data/batch/logs data/batch/notes
MODEL=${BATCH_MODEL:-claude-sonnet-5-5}
# 不继承桌面 App 会话注入的变量和其他模型服务的设置；认证用你在终端里登录的 Anthropic 账号（或 ANTHROPIC_API_KEY）
CLEAN=(env -u ANTHROPIC_BASE_URL -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_MODEL -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_CHILD_SESSION -u CLAUDE_CODE_ENTRYPOINT -u CLAUDE_CODE_OAUTH_SCOPES -u CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN -u CLAUDE_CODE_HOST_SESSION_ID)
echo "== 连通测试（模型 $MODEL）"
"${CLEAN[@]}" claude -p "只回复：OK" --model "$MODEL" --output-format json > data/batch/logs/_preflight.json 2>&1
python3 -I -c "
import json, sys
try: d = json.load(open('data/batch/logs/_preflight.json'))
except Exception: print('   连通测试输出无法解析，见 data/batch/logs/_preflight.json'); sys.exit(1)
if d.get('is_error'): print('   连通测试失败：', d.get('result')); sys.exit(1)
print('   通过；实际调用的模型：', ', '.join(d.get('modelUsage', {}).keys()) or '未知')
" || { echo "请先按 data/batch/README_认证.md 完成登录后重试。"; exit 2; }
for P in "$@"; do
  echo "== $P 开始 $(date '+%H:%M:%S')"
  "${CLEAN[@]}" claude -p "$(cat data/batch/标注指令.md)

本次项目编号：$P" \
    --model "$MODEL" --output-format json \
    --allowedTools "Read" "Write" "Edit" "Glob" "Grep" "Bash(python3 -I scripts/build.py data)" "Bash(python3 -I scripts/build_rule_samples.py data L3-07)" "Bash(python3 -I -c:*)" "Bash(grep:*)" "Bash(sed -n:*)" "Bash(wc:*)" \
    > "data/batch/logs/$P.json" 2> "data/batch/logs/$P.err"
  python3 -I -c "
import json, sys
d = json.load(open('data/batch/logs/$P.json'))
if d.get('is_error'):
    print('   失败：', d.get('result')); sys.exit(2 if d.get('api_error_status') in (401, 403) else 1)
print('   用时', round(d.get('duration_ms', 0) / 60000, 1), '分钟；轮数', d.get('num_turns'), '；费用', d.get('total_cost_usd'), '美元')
"
  rc=$?
  if [ $rc -eq 2 ]; then echo "认证失败，已停止。请先在终端运行 claude 完成登录后重试。"; exit 2; fi
  if [ $rc -ne 0 ]; then echo "   日志解析失败或运行出错，见 data/batch/logs/$P.err"; fi
done
python3 -I scripts/build.py data | head -1
python3 -I scripts/build_rule_samples.py data L3-07 | head -1
