# Jarvis

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## 配置

复制模型配置和密钥示例：

```bash
cp provider_config.example.json provider_config.json
cp .env.example .env
```

Agent 的全局行为配置位于 `agent_config.json`：

```json
{
  "max_same_tool_calls": 5,
  "max_output_tokens": 8192
}
```

`max_same_tool_calls` 表示一次 `Agent.run()` 内完全相同的 Tool Call
最多可被连续执行的次数。Tool 名称和参数都相同才视为相同调用，Tool Call
ID 不参与比较。连续执行 5 次后仍再次请求相同调用时，Agent 会终止本轮
执行并抛出 `ToolCallLimitExceededError`。Tool 名称或参数发生变化都会
重置连续计数，每次新的 `Agent.run()` 也会重新计数。

`max_output_tokens` 表示每次回答预留并传给模型的最大输出 token 数。
每次调用模型前，Agent 都会统计完整输入（System Prompt、Session 消息和
Tool 定义）的 token 数。输入超过模型最大上下文减去
`max_output_tokens` 后的可用空间时，会在请求模型前抛出
`ContextWindowExceededError`。

在 `provider_config.json` 顶部通过 `provider` 选择当前使用的服务商。
每个服务商分别配置 LiteLLM 模型名、API URL 和密钥：

```json
{
  "provider": "deepseek",
  "providers": {
    "deepseek": {
      "model": "deepseek/deepseek-chat",
      "url": "https://api.deepseek.com",
      "key": "${DEEPSEEK_KEY}",
      "max_context_tokens": 131072
    }
  }
}
```

`max_context_tokens` 是可选的模型级配置。填写时使用该值作为模型最大
上下文；省略时通过 LiteLLM 的模型元数据读取 `max_input_tokens`。如果
LiteLLM 没有该模型的上下文元数据，则必须显式配置该字段。

`key` 支持直接填写，也支持 `${ENV_NAME}` 形式从 `.env` 读取。推荐在
`.env` 中保存密钥，例如：

```dotenv
DEEPSEEK_KEY=your-api-key
```

只需要填写当前所选服务商使用的密钥。Ollama 等无密钥服务可以省略 `key`。

`.env`、`provider_config.json` 和 Session 数据不会提交到版本控制。

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

Tool 能力位于独立的 `agent_core/tools/`。每个 Tool 提供模型可见的
`ToolDefinition`，并通过统一的 `execute(arguments)` 接口执行。
`ToolRegistry` 负责按名称注册和调用 Tool。

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
2. 模型返回 Tool Call 时，由 `ToolRegistry` 执行。
3. 将 assistant Tool Call 消息和结构化 Tool 结果回灌给模型。
4. 重复调用模型，直到获得不包含 Tool Call 的最终文本。

Agent Core 会为模型的每次非空回复输出 `AssistantMessageEvent`，包括
带 Tool Call 的中间说明；每批 Tool 使用 `ToolBatchStartedEvent` 标记，
并在单个 Tool 开始和结束时分别输出 `ToolCallEvent` 和
`ToolResultEvent`。CLI 使用这些结构化事件按模型调用轮次分组展示回复、
Tool 名称、参数和执行状态，例如：

```text
Assistant · model call #1 [2026-09-10T16:00:00+08:00]
I'll take a look at the workspace structure.

Tools · model call #1 · 2 call(s)
  [1/2] → list_directory {"path": "."}
        ✓ completed
  [2/2] → list_directory {"path": "agent_core"}
        ✓ completed

Tools · model call #2 · 1 call(s)
  [1/1] → read_file {"path": "README.md"}
        ✓ completed

Assistant · model call #3 [2026-09-10T16:00:02+08:00]
README.md 已读取。
```

当前不设置 Agent Loop 总步数限制；完全相同的 Tool Call 在单轮中的连续
执行次数由 `agent_config.json` 限制。CLI 默认注册
`ReadFileTool`、`EditFileTool`、`SearchFilesTool` 和
`ListDirectoryTool`，以及用于执行命令的 `ShellTool`。文件工具只接受
Workspace 内的相对路径；
`search_files` 使用 Python 正则表达式递归搜索 UTF-8 文件内容，
`list_directory` 返回指定目录的直接子项，`edit_file` 使用 `old_text`
和 `new_text` 对唯一匹配的文本进行替换。`shell` 以 Workspace 为当前
目录执行命令，并在每次执行前要求用户确认；结果包含退出码、标准输出和
标准错误。

启动时会显示自动生成的 Session ID。每轮成功对话都会把本轮新增的
Session Items、发送给 LLM 的完整消息上下文和最终模型响应追加到
`sessions.jsonl`。

文件中每行都是一个完整 JSON 对象。恢复 Session 时直接读取 `items`，
因此 Tool Call 和 Tool Result 也会进入后续模型上下文。CLI 将最终响应的
UTC 时间转换成本机时区后显示：

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
