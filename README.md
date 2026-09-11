# Jarvis

个人 AI Agent：Python Agent Runtime，配 TypeScript（Ink + React）终端界面和
React + assistant-ui 可视化界面。

## 安装

需要 Python >= 3.11、Node.js >= 22（构建和运行终端界面都需要）和
[uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/EvannZhongg/Jarvis-AI.git
cd Jarvis-AI

npm install --prefix interfaces/tui
npm run build --prefix interfaces/tui
uv tool install --editable ".[gui]"
```

`uv tool install` 会为 Jarvis 建一个独立环境，把 `jarvis` 和 `jarvis-gui` 装到
`~/.local/bin`（该目录不在 PATH 上时 uv 会提示需要执行的命令）；装完后在任意
目录、任意新开的终端直接执行，不需要激活虚拟环境。`--editable` 表示直接使用
本仓库源码，改完 `interfaces/tui` 后重新执行
`npm run build --prefix interfaces/tui` 即可生效，不用重装。

Windows 上 `shell` Tool 需要 [Git for Windows](https://git-scm.com/download/win)
提供的 Git Bash。命令统一在 POSIX shell 中执行（macOS/Linux 用 `/bin/sh`，
Windows 用 Git Bash），因此命令写法在各平台一致；找不到 Git Bash 时 `shell`
会返回安装提示。

## 使用

在任意项目目录下启动：

```bash
cd ~/projects/my-project
jarvis
```

未传 `--workspace` 时，启动命令的当前目录就是 Workspace。可选参数：

| 参数 | 说明 |
| --- | --- |
| `--workspace <path>` | 指定 Workspace，默认当前目录 |
| `--session <id>` | 恢复已有 Session |
| `--config <path>` | 指定 Provider 配置文件 |
| `--agent-config <path>` | 指定 Agent 行为配置文件 |

按键：

| 按键 | 作用 |
| --- | --- |
| `Enter` | 提交输入；Agent 执行中输入会排队 |
| `←` / `→` | 在 shell 授权中切换 Allow / Deny |
| `Enter` | 确认当前授权选项 |
| `Esc` | 拒绝授权；Agent 执行中取消当前轮次 |
| `Ctrl+C` | 取消当前轮次；空输入时退出 |
| `Ctrl+D` | 退出 |

shell 授权默认停在 `Allow`，按 `Enter` 确认，按 `Esc` 直接拒绝。界面底部显示
当前 Workspace、模型和 Session ID。

## 配置

首次运行会在 `~/.jarvis/` 下生成 `provider_config.json` 和
`agent_config.json`。

`agent_config.json` 控制 Agent 行为：

```json
{
  "max_same_tool_calls": 5,
  "max_output_tokens": 8192,
  "shell_timeout_seconds": 60,
  "tools": {
    "read_file": true,
    "edit_file": true,
    "search_files": true,
    "list_directory": true,
    "shell": true
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `max_same_tool_calls` | 单轮内完全相同的 Tool Call 最多连续执行几次，超过即终止本轮 |
| `max_output_tokens` | 每次回答预留的输出 token 数；输入超出模型上限减去该值时直接报错 |
| `shell_timeout_seconds` | shell 默认超时，默认 60 秒、上限 900 秒；单次调用可用 `timeout_seconds` 指定更短值 |
| `tools` | 内置 Tool 开关，需要显式配置全部 Tool；未知名称或非布尔值会导致启动失败 |

`provider_config.json` 顶部用 `provider` 选择当前服务商，`providers` 里为每个
服务商配置 LiteLLM 模型名、API URL 和密钥：

```json
{
  "provider": "deepseek",
  "providers": {
    "deepseek": {
      "model": "deepseek/deepseek-chat",
      "url": "https://api.deepseek.com",
      "key": "${DEEPSEEK_KEY}",
      "max_context_tokens": 1048576
    }
  }
}
```

* `key` 可以直接填写，也可以用 `${ENV_NAME}` 从环境变量或配置目录下的 `.env`
  读取。只填当前所选服务商的密钥，Ollama 等无密钥服务可以省略。
* `max_context_tokens` 可选：填写时以它作为模型最大上下文；省略时读取 LiteLLM
  的模型元数据，元数据缺失则必须显式填写。
* OpenAI 兼容服务需要在 `model` 上带 LiteLLM 的接口前缀，例如智谱填
  `openai/glm-5.3`、`url` 填 `https://open.bigmodel.cn/api/paas/v4/`。`providers`
  里的条目名称不会自动作为 LiteLLM 的服务商标识。

密钥放在 `~/.jarvis/.env`：

```dotenv
DEEPSEEK_KEY=your-api-key
```

`.env`、`provider_config.json` 和 Session 数据都不会提交到仓库。

## GUI

GUI 使用 React + assistant-ui，布局为左侧 Sessions、中间 Chat、右侧 Workspace，
新建会话、恢复历史、Markdown 回复、工具参数与结果、Shell 授权确认和目录展开都
可以直接在浏览器中操作。

构建前端并启动（Python 依赖在安装步骤里已经装好）：

```bash
npm install --prefix interfaces/gui
npm run build --prefix interfaces/gui
jarvis-gui
```

打开 <http://127.0.0.1:8000>，服务只监听本机地址。参数与 `jarvis` 一致：

```bash
jarvis-gui --workspace ~/projects/my-project
jarvis-gui --config path/to/provider_config.json --agent-config path/to/agent_config.json
```

GUI 和 TUI 共用同一个 Agent Runtime（每个 WebSocket 连接对应一个
`python -m interfaces.bridge` 子进程），模型配置、Tool 注册、Shell 授权、Session
落盘和取消行为都一致，两边可以互相恢复同一批 Session。执行中可以点「停止」中断
当前轮次，等同 TUI 的 `Esc`；被取消的轮次不会写入 Session 文件，已执行的工具
操作不会撤销。同一时刻只允许一个页面驱动 Agent。

前端开发时先启动 `jarvis-gui`，另开终端执行
`npm run dev --prefix interfaces/gui`，访问 Vite 显示的
<http://127.0.0.1:5173>，API 和 WebSocket 会代理到 Python 服务。界面代码在
`interfaces/gui/`，构建产物在 `interfaces/gui/static/`（不提交）。

## 会话与工具

每轮成功对话都会把本轮新增的 Session Items、发送给模型的完整消息上下文和模型
响应追加到 Workspace 下的 `sessions/<SESSION_ID>/<SESSION_ID>.jsonl`，每行一个
JSON 对象；超过回灌上限的完整 Tool Result 保存在同一目录的
`<TOOL_CALL_ID>.txt`。用 `jarvis --session SESSION_ID` 恢复历史对话。

内置 Tool 有 `read_file`、`edit_file`、`search_files`、`list_directory` 和
`shell`：

* 文件工具只接受 Workspace 内的相对路径。`search_files` 递归搜索 UTF-8 文本，
  默认跳过超大文件、非文本文件、`.git`/`node_modules`/`build` 等目录，以及指向
  Workspace 之外的链接。
* `shell` 以 Workspace 为当前目录执行命令，每次执行前都需要人工确认，结果包含
  退出码、标准输出、标准错误、是否超时和实际超时秒数。
* 回灌给模型的 Tool Result 不超过 16K chars；更大的结果转存为上面的 Session
  Artifact，模型只拿到路径、字符数和预览。

## 架构

Agent Runtime 与界面解耦：界面进程不直接调用 Runtime，而是启动一个 Python
子进程，通过 stdio 上的 newline-delimited JSON 通信。

```text
jarvis (Python console script)
  └─ node interfaces/tui/dist/app.js      Ink + React 界面，持有 TTY
       └─ python -m interfaces.bridge      Agent Runtime
            └─ agent_core                  与界面无关

jarvis-gui (Python console script)
  └─ interfaces/gui/server.py             HTTP API + WebSocket 中继
       └─ python -m interfaces.bridge      Agent Runtime
            └─ agent_core                  与界面无关
```

```text
Jarvis/
├── agent_core/          Agent Runtime，不依赖任何界面
└── interfaces/
    ├── launch.py        jarvis 命令入口
    ├── bridge/          Runtime 与协议的适配层
    ├── protocol/        TUI 与 GUI 共用的协议类型
    ├── tui/             TypeScript + Ink + React 终端界面
    └── gui/             FastAPI 中继 + React + assistant-ui 界面
```

Bridge 只负责把 `AgentEvent` 翻译成协议消息，界面只负责渲染协议消息和采集输入；
GUI 服务端同样只做转发，不含任何 Agent 执行逻辑。Agent 执行中按 `Esc`、
`Ctrl+C` 或点「停止」会向 Runtime 发送 `SIGINT` 取消当前轮次。

## 测试

Python 测试使用 Mock Provider，不需要真实 API Key。在仓库里跑测试需要虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[gui]"

python -m unittest discover -s tests -v
```

界面测试：

```bash
npm test --prefix interfaces/tui
npm run typecheck --prefix interfaces/tui
npm test --prefix interfaces/gui
npm run typecheck --prefix interfaces/gui
```
