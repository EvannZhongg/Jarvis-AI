# Jarvis

第一阶段 MVP：一个基于 LiteLLM 的多轮交互式 CLI Agent。

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

在 `provider_config.json` 顶部通过 `provider` 选择当前使用的服务商。
每个服务商分别配置 LiteLLM 模型名、API URL 和密钥：

```json
{
  "provider": "deepseek",
  "providers": {
    "openai": {
      "model": "openai/gpt-5",
      "url": "https://api.openai.com/v1",
      "key": "${OPENAI_KEY}"
    },
    "anthropic": {
      "model": "anthropic/claude-sonnet-4-5",
      "url": "https://api.anthropic.com",
      "key": "${ANTHROPIC_KEY}"
    },
    "gemini": {
      "model": "gemini/gemini-2.5-flash",
      "url": "https://generativelanguage.googleapis.com",
      "key": "${GEMINI_KEY}"
    },
    "deepseek": {
      "model": "deepseek/deepseek-chat",
      "url": "https://api.deepseek.com",
      "key": "${DEEPSEEK_KEY}"
    },
    "openrouter": {
      "model": "openrouter/openai/gpt-5",
      "url": "https://openrouter.ai/api/v1",
      "key": "${OPENROUTER_KEY}"
    },
    "ollama": {
      "model": "ollama/llama3.1",
      "url": "http://localhost:11434"
    }
  }
}
```

`key` 支持直接填写，也支持 `${ENV_NAME}` 形式从 `.env` 读取。推荐在
`.env` 中保存密钥，例如：

```dotenv
OPENAI_KEY=your-api-key
ANTHROPIC_KEY=your-api-key
GEMINI_KEY=your-api-key
DEEPSEEK_KEY=your-api-key
OPENROUTER_KEY=your-api-key
```

只需要填写当前所选服务商使用的密钥。Ollama 等无密钥服务可以省略 `key`。

`.env`、`provider_config.json` 和 Session 数据不会提交到版本控制。

## 启动

```bash
python -m agent_cli
```

输入 `exit` 或 `quit` 退出。

每次模型请求都会将 `agent_core/prompts/system_prompt.md` 作为第一条
`system` 消息注入上下文。

启动时会显示自动生成的 Session ID。每轮成功对话都会把发送给 LLM 的
完整消息上下文、模型响应和 UTC 时间追加到 `sessions.jsonl`：

```json
{
  "session_id": "...",
  "timestamp_utc": "2026-09-09T08:00:00Z",
  "request": {
    "messages": [
      {"role": "system", "content": "..."},
      {"role": "user", "content": "hello"}
    ]
  },
  "response": {"content": "..."}
}
```

文件中每行都是一个完整 JSON 对象。CLI 将 UTC 时间转换成本机时区后显示：

```text
Assistant [2026-09-09T16:00:00+08:00]: ...
```

使用 Session ID 恢复历史对话：

```bash
python -m agent_cli --session SESSION_ID
```

指定其他模型配置文件：

```bash
python -m agent_cli --config path/to/provider_config.json
```

## 测试

测试使用 Mock Provider，不需要真实 API Key：

```bash
python -m unittest discover -s tests -v
```
