# Nosis

个人 AI Agent：Python Agent Runtime，配套 TUI（Ink + React）和 GUI（React + assistant-ui）。TUI 与 GUI 共用同一套 Runtime、Tool、授权和 Session 行为。

## 快速开始

环境要求：Python >= 3.11、Node.js >= 22 和 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/EvannZhongg/Nosis.git
cd Nosis

npm install --prefix interfaces/tui
npm run build --prefix interfaces/tui
uv tool install --editable ".[gui]"
```

该命令会安装 `nosis` 和 `nosis-gui`；仓库新增依赖后重新执行即可更新安装环境。

在任意 Workspace 中启动 TUI：

```bash
cd ~/projects/my-project
nosis
```

启动 GUI：

```bash
npm install --prefix interfaces/gui
npm run build --prefix interfaces/gui
nosis-gui --workspace ~/projects/my-project
```

GUI 默认监听 <http://127.0.0.1:8737>。Windows 用户需要安装 [Git for Windows](https://git-scm.com/download/win)，`shell` Tool 使用其中的 Git Bash。

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [Agent Core](agent_core/README.md) | Runtime、Provider、配置、Tool、MCP 和 Session |
| [TUI](interfaces/tui/README.md) | 终端界面、命令行参数、快捷键和前端开发 |
| [GUI](interfaces/gui/README.md) | Web 界面、附件、开发服务器和前端测试 |
| [Bridge](interfaces/bridge/README.md) | Runtime 子进程、授权和取消流程 |
| [Protocol](interfaces/protocol/README.md) | TUI/GUI 共用的消息协议类型 |

## 项目结构

```text
Nosis/
├── agent_core/       Agent Runtime
├── interfaces/
│   ├── bridge/       Runtime 与前端之间的适配层
│   ├── protocol/     共用协议类型
│   ├── tui/          Ink + React 终端界面
│   └── gui/          FastAPI + React 可视化界面
└── tests/             Python Runtime 与接口测试
```

## 测试

Python 测试使用 Mock Provider，不需要真实 API Key：

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[gui]"
python -m unittest discover -s tests -v
```

前端测试和类型检查：

```bash
npm test --prefix interfaces/tui
npm run typecheck --prefix interfaces/tui
npm test --prefix interfaces/gui
npm run typecheck --prefix interfaces/gui
```
