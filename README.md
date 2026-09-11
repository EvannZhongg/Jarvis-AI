# Jarvis

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install jarvis-agent
```

## 配置

安装后初始化配置：

```bash
jarvis --init
```

默认会在 `~/.jarvis/` 下生成：

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

`key` 支持直接填写，也支持 `${ENV_NAME}` 形式从环境变量或配置目录下的
`.env` 读取。例如：

```dotenv
DEEPSEEK_KEY=your-api-key
```

只需要填写当前所选服务商使用的密钥。Ollama 等无密钥服务可以省略 `key`。

`.env`、`provider_config.json` 和 Session 数据不会提交到 Jarvis 仓库。
Session 对话按 ID 保存在当前 Workspace 的 `sessions/`。

从源码开发时可以使用可编辑安装：

```bash
python -m pip install -e .
```

## 启动

安装后会注册 `jarvis` 命令。进入任意项目目录直接启动：

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
时替换为 `Current workspace: {{/absolute/path/to/project}}`。启动时 CLI
也会输出解析后的绝对路径。

输入 `exit` 或 `quit` 退出。

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
执行次数由 `agent_config.json` 限制。CLI 根据 `tools` 配置注册
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

启动时会显示自动生成的 Session ID。每轮成功对话都会把本轮新增的
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
也会进入后续模型上下文。CLI 将最终响应的 UTC 时间转换成本机时区后
显示：

`usage` 来自模型服务返回的 token 用量。如果服务商没有返回 usage，
该字段记录为 `null`。

```text
Assistant [2026-09-09T16:00:00+08:00]: ...
```

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

## 测试

测试使用 Mock Provider，不需要真实 API Key：

```bash
python -m unittest discover -s tests -v
```
