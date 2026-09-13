# Protocol

`protocol.ts` 定义 TUI、GUI 与 Python Bridge 共用的消息结构和编解码类型。修改消息字段时，需要同时检查 `interfaces/bridge/protocol.py` 及两套界面的消息处理代码。

该目录是供前端通过 `file:` 依赖引用的 TypeScript 包，不包含 Agent 执行逻辑。
