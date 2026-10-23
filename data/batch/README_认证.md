# 批量标注的模型与认证设置

## 现状与原因

`~/.claude/settings.json` 的 `env` 中设置了火山方舟（豆包）：
- `ANTHROPIC_BASE_URL=https://ark.cn-beijing.volces.com/api/coding`
- `ANTHROPIC_MODEL=doubao-seed-2-0-code`
- `ANTHROPIC_AUTH_TOKEN`：方舟的密钥

这个 `env` 每次启动 `claude` 都会生效，所以非交互调用不会走 Claude Opus 5.5。从桌面 App 会话里启动时，还会继承 App 的临时凭证，结果就是 401 认证失败。

## 切换步骤（在你自己的终端里执行）

**1. 把豆包配置挪成单独的文件，从全局配置里去掉。**

先备份；再把 `env` 中这 3 项写入 `~/.claude/settings.doubao.json`；然后从 `settings.json` 中删去这 3 项：

```bash
cp ~/.claude/settings.json ~/.claude/settings.json.bak_20261016
python3 -c "import json,os;p=os.path.expanduser('~/.claude/settings.json');d=json.load(open(p));e=d.get('env',{});keep={k:e.pop(k) for k in ['ANTHROPIC_AUTH_TOKEN','ANTHROPIC_BASE_URL','ANTHROPIC_MODEL'] if k in e};json.dump({'env':keep},open(os.path.expanduser('~/.claude/settings.doubao.json'),'w'),ensure_ascii=False,indent=2);json.dump(d,open(p,'w'),ensure_ascii=False,indent=2);print('已移出:',list(keep))"
```

以后要用豆包，启动时加上：

```bash
claude --settings ~/.claude/settings.doubao.json
```

**2. 登录 Anthropic 账号，二选一：**

- **Claude 订阅账号**：运行 `claude`，在界面中输入 `/login`，按提示在浏览器中登录，完成后退出。
- **API 密钥**（Anthropic Console 创建）：在终端中 `export ANTHROPIC_API_KEY=...`，只对当前终端生效。

**3. 验证并试跑。** 脚本会先做连通测试，显示实际调用的模型，通过后才开始标注：

```bash
cd /Users/alrik/Documents/Finetuning && scripts/run_batch.sh P011 P090
```

## 恢复原状

不再需要批量时，可以恢复原配置：

```bash
cp ~/.claude/settings.json.bak_20261016 ~/.claude/settings.json
```

## 说明

- 批处理脚本默认使用 `claude-opus-5-5`。如需更换，可设置 `BATCH_MODEL=模型名` 后再运行。
- 脚本会清掉桌面 App 会话注入的变量，不会把调用带到其他服务上。
- 但脚本覆盖不了 `settings.json` 中的 `env`，所以第 1 步必须做。
