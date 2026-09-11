import argparse
import asyncio
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from threading import Event
from typing import Callable
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from agent_core import (
    Agent,
    AgentConfig,
    AgentEvent,
    JsonlSessionStore,
    ListDirectoryTool,
    LLMProvider,
    ShellApprovalPolicy,
    SubprocessCommandExecutor,
    Workspace,
    create_tools,
    load_agent_config,
)
from agent_core.config import (
    DEFAULT_AGENT_CONFIG_PATH,
    DEFAULT_CONFIG_DIRECTORY,
    DEFAULT_CONFIG_PATH,
    initialize_default_configs,
)
from agent_core.prompts import load_system_prompt
from agent_core.providers import LiteLLMProvider
from agent_core.providers.config import load_config, load_model_options


STATIC_PATH = Path(__file__).resolve().parent / "static"


def create_app(
    workspace: Workspace,
    provider_factory: Callable[[str], LLMProvider],
    config: AgentConfig,
    store: JsonlSessionStore,
    *,
    models: dict[str, str],
    default_model: str,
) -> FastAPI:
    app = FastAPI(title="Jarvis", docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    run_lock = asyncio.Lock()

    @app.get("/api/models")
    def list_models():
        return {
            "default": default_model,
            "models": [{"id": name, "model": model} for name, model in models.items()],
        }

    @app.get("/api/sessions")
    def list_sessions():
        return store.list_sessions()

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str):
        return jsonable_encoder(store.load(session_id))

    @app.get("/api/workspace")
    def get_workspace(path: str = "."):
        try:
            listing = ListDirectoryTool(workspace).execute({"path": path})
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"root": str(workspace.path), **listing}

    @app.websocket("/api/sessions/{session_id}/run")
    async def run(websocket: WebSocket, session_id: str):
        # A local webpage must not be able to drive the agent cross-origin.
        origin = websocket.headers.get("origin")
        allowed_origins = {
            f"http://{websocket.headers.get('host')}",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        }
        if origin is not None and origin not in allowed_origins:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        if run_lock.locked():
            await websocket.send_json({"type": "error", "message": "Jarvis 正在执行另一个任务，请稍后再试。"})
            await websocket.close()
            return

        async with run_lock:
            loop = asyncio.get_running_loop()
            disconnected = Event()
            approval: asyncio.Future[bool] | None = None
            approval_id: str | None = None
            receiver: asyncio.Task | None = None

            def publish(event: AgentEvent) -> None:
                if disconnected.is_set():
                    raise ConnectionError("GUI disconnected")
                payload = jsonable_encoder({"type": type(event).__name__, **asdict(event)})
                asyncio.run_coroutine_threadsafe(websocket.send_json(payload), loop).result()

            async def ask_approval(command: str) -> bool:
                nonlocal approval, approval_id
                if disconnected.is_set():
                    return False
                approval = loop.create_future()
                approval_id = str(uuid4())
                await websocket.send_json({
                    "type": "approval_required", "id": approval_id, "command": command,
                })
                return await approval

            def request_permission(command: str) -> bool:
                return asyncio.run_coroutine_threadsafe(ask_approval(command), loop).result()

            async def receive_approvals() -> None:
                try:
                    while True:
                        data = await websocket.receive_json()
                        if not isinstance(data, dict):
                            raise ValueError("Expected an approval object")
                        if (
                            data.get("type") == "approval"
                            and data.get("id") == approval_id
                            and type(data.get("approved")) is bool
                            and approval is not None
                            and not approval.done()
                        ):
                            approval.set_result(data["approved"])
                except (WebSocketDisconnect, ValueError):
                    disconnected.set()
                    if approval is not None and not approval.done():
                        approval.set_result(False)

            def execute(message: str, model_id: str):
                session = store.load(session_id)
                agent = Agent(
                    provider=provider_factory(model_id),
                    session=session,
                    system_prompt=load_system_prompt(workspace),
                    config=config,
                    workspace=workspace,
                    tools=create_tools(config.tools, workspace, SubprocessCommandExecutor(workspace.path)),
                    tool_policy=ShellApprovalPolicy(request_permission),
                )
                result = agent.run(message, on_event=publish)
                store.append_turn(session_id, result.request, result.response, result.items)
                return session

            try:
                data = await websocket.receive_json()
                message = data.get("message")
                if not isinstance(message, str) or not message.strip():
                    raise ValueError("请输入消息。")
                model_id = data.get("model")
                if not isinstance(model_id, str) or model_id not in models:
                    raise ValueError("请选择已配置的模型。")
                receiver = asyncio.create_task(receive_approvals())
                session = await asyncio.to_thread(execute, message.strip(), model_id)
                if not disconnected.is_set():
                    await websocket.send_json({"type": "done", "session": jsonable_encoder(session)})
            except WebSocketDisconnect:
                disconnected.set()
            except Exception as error:
                if not disconnected.is_set():
                    await websocket.send_json({"type": "error", "message": str(error)})
            finally:
                connected = not disconnected.is_set()
                disconnected.set()
                if approval is not None and not approval.done():
                    approval.set_result(False)
                if receiver is not None:
                    receiver.cancel()
                    with suppress(asyncio.CancelledError):
                        await receiver
                if connected:
                    await websocket.close()

    if STATIC_PATH.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_PATH, html=True), name="gui")
    return app


def main(argv: list[str] | None = None) -> None:
    import uvicorn

    parser = argparse.ArgumentParser(prog="jarvis-gui")
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--agent-config", type=Path, default=DEFAULT_AGENT_CONFIG_PATH)
    args = parser.parse_args(argv)
    try:
        if args.config == DEFAULT_CONFIG_PATH or args.agent_config == DEFAULT_AGENT_CONFIG_PATH:
            for path in initialize_default_configs(DEFAULT_CONFIG_DIRECTORY):
                print(f"Created configuration: {path}")
        load_dotenv(args.config.parent / ".env")
        workspace = Workspace(args.workspace or Path.cwd())
        default_model, models = load_model_options(args.config)
        config = load_agent_config(args.agent_config)

        def create_provider(model_id: str) -> LLMProvider:
            model_config = load_config(args.config, provider=model_id)
            return LiteLLMProvider(
                model=model_config.model,
                base_url=model_config.url,
                api_key=model_config.key,
                max_context_tokens=model_config.max_context_tokens,
            )

        app = create_app(
            workspace, create_provider, config, JsonlSessionStore(workspace.path / "sessions"),
            models=models, default_model=default_model,
        )
    except (OSError, ValueError) as error:
        raise SystemExit(f"Failed to start Jarvis: {error}") from error
    print(f"Workspace: {workspace.path}")
    print("Jarvis GUI: http://127.0.0.1:8000")
    if not STATIC_PATH.is_dir():
        print("Build the GUI with: cd gui && npm install && npm run build")
    uvicorn.run(app, host="127.0.0.1", port=8000)
