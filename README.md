# Jarvis

个人 AI Agent：Python Agent Runtime，配 TypeScript（Ink + React）终端界面和
React + assistant-ui 可视化界面。

## 安装

需要 Python >= 3.11 与 Node.js >= 22（Node 只在运行时需要）。

先构建终端界面（构建产物 `interfaces/tui/dist/app.js` 不入库），再用
[uv](https://docs.astral.sh/uv/) 把命令装到 PATH 上：

```bash
npm install --prefix interfaces/tui
npm run build --prefix interfaces/tui
uv tool install --editable ".[gui]"
```

`uv tool install` 会为 Jarvis 建一个独立环境，把 `jarvis` 和 `jarvis-gui`
放进 `~/.local/bin`（该目录不在 PATH 上时 uv 会提示需要执行的命令）。装完后
在任意目录、任意新开的终端直接执行，不需要激活虚拟环境。`--editable` 表示
直接使用本仓库源码，改完 `interfaces/tui` 后重新执行
`npm run build --prefix interfaces/tui` 即可生效，不用重装。

需要在仓库里跑测试时，仍可使用虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[gui]"
```

虚拟环境里的 `jarvis` 只在该环境激活后可用，且激活命令要写对：在仓库目录内用
`.\.venv\Scripts\Activate.ps1`，在其他目录要用绝对路径（如
`. C:\path\to\Jarvis-AI\.venv\Scripts\Activate.ps1`）。

可视化界面是可选的，构建步骤见 [GUI](#gui)。

## 使用

按[安装](#安装)装好后，在任意目录下执行：

```bash
jarvis
```

当前目录会作为 Workspace。可选参数：

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

shell 命令授权使用左右方向键选择，默认停在 `Allow`，按 `Enter` 确认；
按 `Esc` 直接拒绝。

## 配置

首次运行会在 `~/.jarvis/` 下自动生成：

```text
~/.jarvis/
├── provider_config.json
└── agent_config.json
```

Agent 的全局行为配置位于
`~/.jarvis/agent_config.json`：

```json
{
  "max_same_tool_calls": 5,
  "max_output_tokens": 8192,
  "shell_timeout_seconds": 60,
  "tools": {
    "read_file": true,
    ...
    "shell": true
  }
}
```

`max_same_tool_calls` 表示一次 `Agent.run()` 内完全相同的 Tool Call
最多可被连续执行的次数。Tool 名称和参数都相同才视为相同调用，连续执行请求相同调用时，Agent 会终止本轮
执行并抛出 `ToolCallLimitExceededError`。Tool 名称或参数发生变化都会
重置连续计数，每次新的 `Agent.run()` 也会重新计数。

`max_output_tokens` 表示每次回答预留并传给模型的最大输出 token 数。
每次调用模型前，Agent 都会统计完整输入（System Prompt、Session 消息和
Tool 定义）的 token 数。输入超过模型最大上下文减去
`max_output_tokens` 后的可用空间时，会在请求模型前抛出
`ContextWindowExceededError`。

`shell_timeout_seconds` 是 shell 命令的默认超时，默认为 60 秒，配置上限
为 900 秒。Tool Call 可以通过 `timeout_seconds` 指定不超过该默认值的
更短超时。

`tools` 用于管理内置 Tool。值为 `true` 时注册并开放给模型，值为
`false` 时不注册。所有已支持的 Tool 都需要显式配置；未知 Tool 名称、
缺少配置或使用非布尔值都会导致启动失败。

在 `~/.jarvis/provider_config.json` 顶部通过 `provider` 选择
当前使用的服务商。
每个服务商分别配置 LiteLLM 模型名、API URL 和密钥：

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

`max_context_tokens` 是可选的模型级配置。填写时使用该值作为模型最大
上下文；省略时通过 LiteLLM 的模型元数据读取 `max_input_tokens`。如果
LiteLLM 没有该模型的上下文元数据，则必须显式配置该字段。

对 OpenAI 兼容服务，`model` 也需要 LiteLLM 的接口前缀。例如智谱可配置
`openai/glm-5.3`，`url` 使用 `https://open.bigmodel.cn/api/paas/v4/`。
这里的 `openai/` 表示接口协议，请求仍发送到配置的 `url`；`providers`
中的条目名称不会自动作为 LiteLLM 的服务商标识。

`key` 支持直接填写，也支持 `${ENV_NAME}` 形式从环境变量或配置目录下的
`.env` 读取。例如：

```dotenv
DEEPSEEK_KEY=your-api-key
```

只需要填写当前所选服务商使用的密钥。Ollama 等无密钥服务可以省略 `key`。

`.env`、`provider_config.json` 和 Session 数据不会提交到 Jarvis 仓库。
Session 对话按 ID 保存在当前 Workspace 的 `sessions/`。

## 启动

按[安装](#安装)装好后，进入任意项目目录直接启动：

```bash
cd ~/projects/my-project
jarvis
```

未传 `--workspace` 时，Jarvis 使用启动命令时的当前目录作为 Workspace：

```text
~/projects/my-project
```

也可以显式指定其他目录：

```bash
jarvis --workspace ~/projects/another-project
```

Workspace 会作为显式对象传入 Agent Runtime。`Soul.md` 使用
`Current workspace: {{workspace}}` 模板显式声明 Workspace，加载 Prompt
时替换为 `Current workspace: {{/absolute/path/to/project}}`。启动后界面
底部也会显示解析出的 Workspace 与模型。

按 `Ctrl+D` 或在空输入时按 `Ctrl+C` 退出。

## GUI

GUI 使用 React + assistant-ui，布局为左侧 Sessions、中间 Chat、右侧
Workspace。新建会话、恢复历史、Markdown 回复、展开工具参数和结果、
Shell 执行确认以及目录展开均可直接在浏览器中操作。

模型和密钥沿用上面的配置步骤：首次运行会生成 `~/.jarvis/`，编辑
`~/.jarvis/provider_config.json`，密钥可放在 `~/.jarvis/.env`。

输入框左下角可以选择 `~/.jarvis/provider_config.json` 中配置的模型，默认选中
`provider` 对应的条目。切换从下一轮消息生效，保留当前会话上下文；执行期间
不可切换。选择只影响当前 GUI 页面，不修改配置文件或 TUI 的默认模型。
未配置所选服务商的密钥时，发送消息会显示配置错误。

安装 GUI 依赖并构建前端：

```bash
source .venv/bin/activate
python -m pip install -e '.[gui]'
npm install --prefix interfaces/gui
npm run build --prefix interfaces/gui
jarvis-gui
```

用[安装](#安装)里的 `uv tool install` 方式装好时，Python 依赖已经就绪，
只需要执行上面两条 `npm` 命令构建前端，然后直接运行 `jarvis-gui`。

打开 <http://127.0.0.1:8000>。也可以指定工作目录和配置文件：

```bash
jarvis-gui --workspace ~/projects/my-project
jarvis-gui --config path/to/provider_config.json --agent-config path/to/agent_config.json
```

GUI 和 TUI 共用同一个 Agent Runtime：每个 WebSocket 连接对应一个
`python -m interfaces.bridge` 子进程，服务端只在浏览器和 Bridge 之间转发
协议消息，不含任何 Agent 执行逻辑。因此模型配置、Tool 注册、Shell 授权、
Session 落盘和取消行为都与 TUI 完全一致，模型回复同样逐 token 流式输出。

执行中的工具卡显示名称、参数和成功/失败状态；`tool_result` 协议消息不携带
工具输出（大结果已转存为 Session Artifact），完整输出在本轮结束后随 Session
刷新出现。右侧目录随任务完成刷新，也可手动刷新；当前只浏览目录，不提供
文件编辑器。

会话在一轮成功执行后保存，首次保存后出现在左侧列表。恢复会话时使用
本次启动的 Workspace，与 TUI 的恢复行为一致。执行期间暂时禁用会话切换。
执行中可以点击「停止」中断当前轮次，等同 TUI 的 `Esc`；被取消的轮次不会
写入 Session 文件，已执行的工具操作不会撤销。同一时刻只允许一个页面驱动
Agent，第二个页面会收到提示。

前端开发时，先启动 `jarvis-gui`，另开终端运行：

```bash
npm run dev --prefix interfaces/gui
```

访问 Vite 显示的 <http://127.0.0.1:5173>，API 和 WebSocket 会代理到
Python 服务。服务仅监听本机地址。

代码位于 `interfaces/gui/server.py`（HTTP API 与中继）和
`interfaces/gui/src/`（界面），构建产物位于 `interfaces/gui/static/`，
不提交到版本控制。

## Runtime 与 Session

每次模型请求都会将 `agent_core/prompts/Soul.md` 和当前 Workspace 作为
系统指令加载到 `LLMRequest.system_prompt`。Agent Core 不决定系统指令在
具体模型 API 中的表达方式；当前由 `LiteLLMProvider` 将其转换为 LiteLLM
的 `system` 消息。System Prompt 不注入当前时间。

Session 使用 `items` 保存完整执行上下文，包括：

* `user` 输入
* 带 `tool_calls` 的 `assistant` item
* 带 `tool_call_id` 的 `tool` 执行结果
* 最终 `assistant` 回答

其中 `user` 和 `assistant` item 在发送给 LLM 时会附带各自的交互时间：

```text
[2026-09-09T16:00:00+08:00] 历史消息内容
```

时间使用运行机器的本地时区，并以最小前缀形式放在每条交互消息开头。

## Tool Call

Tool 公共接口和管理代码位于 `agent_core/tools/`，具体内置 Tool 统一位于
二级路径 `agent_core/tools/builtin/`。每个 Tool 提供模型可见的
`ToolDefinition`，并通过统一的 `execute(arguments)` 接口执行。
`create_tools()` 根据 `agent_config.json` 的 `tools` 配置统一完成实例化；
`ToolRegistry` 负责按名称注册和调度 Tool，并在 Tool 执行前调用注入的
Policy。当前仅提供 `ShellApprovalPolicy` 处理 shell 人工确认，没有引入
完整的 Policy Engine。

shell 的进程执行已从 `ShellTool` 抽离到 `CommandExecutor`：

```text
Agent
  ↓
ToolRegistry
  ↓
ToolPolicy
  ↓
ShellTool
  ↓
CommandExecutor
```

`ShellTool` 只负责参数校验和结果结构化，默认的
`SubprocessCommandExecutor` 负责在指定工作目录启动独立子进程组。命令
超时后会终止整个子进程组，而不是只终止 shell 父进程。`stdout` 与
`stderr` 分别最多保留 50K chars；每个输出流超过限制时保留开头和结尾，
并在中间标注该输出流被截断的字符数量。执行结果包含 `timed_out` 和实际采用的
`timeout_seconds`。后续接入沙箱执行后端时，不需要把进程管理逻辑重新
写回 Tool。

`read_file` 支持可选的 `offset` 和 `limit` 参数，默认从第 1 行开始读取
最多 2000 行，同时将返回内容限制在约 64K chars。超过 50 MiB 的文件会
在读取前被拒绝，错误中包含实际文件大小；正常结果也包含
`file_size_bytes`。返回内容带原始行号；超长单行会被裁剪并明确标记
“该行被截断”。文件尚未读完或受到字符数限制时会给出下一次读取使用的
`offset`，到达末尾时会返回文件总行数。文件内容通过顺序流式扫描读取，
跳过前置行和处理超长单行时也只保留有界缓冲区；达到行数限制后使用一行
lookahead 判断是否还有后续内容。

`LLMResponse` 同时支持普通文本和 Tool Call：

```python
LLMResponse(
    content=None,
    tool_calls=(
        ToolCall(
            id="call_123",
            name="read_file",
            arguments={"path": "README.md"},
        ),
    ),
)
```

`Agent.run()` 会显式执行以下循环：

1. 将注册 Tool 的定义随 `LLMRequest` 发送给模型。
2. 模型返回 Tool Call 时，由 `ToolRegistry` 先执行 Policy，再调用 Tool。
3. 由 `ToolResultNormalizer` 在统一边界治理 Tool Result：不超过
   16K chars 的结果原样回灌；更大的结果完整写入 Workspace artifact，
   模型仅接收 artifact 路径、字符数、约 1200 chars 的预览和读取说明。
4. 将 assistant Tool Call 消息和治理后的结构化 Tool 结果回灌给模型。
5. 重复调用模型，直到获得不包含 Tool Call 的最终文本。

当前不设置 Agent Loop 总步数限制；完全相同的 Tool Call 在单轮中的连续
执行次数由 `agent_config.json` 限制。Bridge 根据 `tools` 配置注册
`ReadFileTool`、`EditFileTool`、`SearchFilesTool`、
`ListDirectoryTool` 和 `ShellTool`。文件工具只接受 Workspace 内的相对
路径；
`search_files` 使用 Python 正则表达式递归搜索 UTF-8 文件内容，并支持
`glob`、`offset`、`limit`、`case_insensitive` 和 `fixed_strings`。
默认最多返回 200 个匹配，单次结构化输出不超过 16K chars，单文件最多
扫描 1 MiB，总遍历路径数上限为 10,000；默认跳过 `.git`、`.venv`、
`node_modules`、`build`、`dist`、`target` 等常见依赖、缓存和构建目录。
返回值包含 `matches`、`has_more`、`next_offset`、`scanned_files` 和
`skipped_files`。
`list_directory` 返回指定目录的直接子项，`edit_file` 使用 `old_text`
和 `new_text` 对唯一匹配的文本进行替换。`shell` 以 Workspace 为当前
目录执行命令，并在每次执行前要求用户确认；结果包含退出码、标准输出和
标准错误、是否超时及采用的超时秒数。

启动时界面底部会显示当前 Session ID。每轮成功对话都会把本轮新增的
Session Items、发送给 LLM 的完整消息上下文和最终模型响应追加到
`sessions/<SESSION_ID>/<SESSION_ID>.jsonl`。超过回灌上限的完整 Tool
Result 保存在同一目录的 `<TOOL_CALL_ID>.txt` 中。

```text
sessions/
└── <SESSION_ID>/
    ├── <SESSION_ID>.jsonl
    └── <TOOL_CALL_ID>.txt
```

每个 Session 使用独立文件，文件中每行都是一个完整 JSON 对象。恢复
Session 时只读取对应文件中的 `items`，因此 Tool Call 和 Tool Result
也会进入后续模型上下文。

`usage` 来自模型服务返回的 token 用量。如果服务商没有返回 usage，
该字段记录为 `null`。

使用 Session ID 恢复历史对话：

```bash
jarvis --session SESSION_ID
```

指定其他模型配置文件：

```bash
jarvis --config path/to/provider_config.json
```

指定其他 Agent 行为配置文件：

```bash
jarvis --agent-config path/to/agent_config.json
```

## 架构

Agent Runtime 与界面解耦。界面进程不直接调用 Agent Runtime，而是启动一个
Python 子进程，通过 stdio 上的 newline-delimited JSON 通信：

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

`interfaces/bridge` 只负责把 `AgentEvent` 翻译成协议消息，不包含任何
Agent 决策逻辑；界面只负责渲染协议消息和采集输入。Bridge 进程把 fd 1
换成私有协议通道，其余输出重定向到 stderr，避免第三方库写 stdout 破坏
协议流。

GUI 服务端同样不含 Agent 执行逻辑：它把浏览器的 `user_turn` 和
`approval_response` 转发给 Bridge，把 Bridge 的协议消息转发给浏览器。
`start` 消息由服务端构造，页面无法指定配置文件路径。协议类型定义只有一份，
Python 侧在 `interfaces/bridge/protocol.py`，TypeScript 侧在
`interfaces/protocol/`，由 TUI 和 GUI 共同引用。

模型回答以增量方式流式渲染：`LLMProvider.stream()` 在产出
`LLMResponse` 的同时通过回调上报文本分片，Agent Loop 将其作为
`AssistantMessageDeltaEvent` 发出。

Agent 执行中按 `Esc` 或 `Ctrl+C`（GUI 中点击「停止」）会向 Runtime 发送
`SIGINT` 取消当前轮次。被取消的轮次不会写入 Session 文件，界面会显式标注。

## 测试

Python 测试使用 Mock Provider，不需要真实 API Key：

```bash
python -m unittest discover -s tests -v
```

界面测试：

```bash
npm test --prefix interfaces/tui
npm run typecheck --prefix interfaces/tui
npm test --prefix interfaces/gui
npm run typecheck --prefix interfaces/gui
```
