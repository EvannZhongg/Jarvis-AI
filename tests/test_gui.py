import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_core import (
    AgentConfig,
    CommandExecutionResult,
    JsonlSessionStore,
    LLMRequest,
    LLMResponse,
    Message,
    ToolCall,
    ToolConfig,
    Workspace,
)
from test_agent import MockProvider

try:
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    from agent_gui.server import create_app, main
except ModuleNotFoundError:
    TestClient = None


@unittest.skipIf(TestClient is None, "Install the gui extra to test the GUI API")
class GuiTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "README.md").write_text("Hello Jarvis", encoding="utf-8")
        (self.root / "src").mkdir()
        self.store = JsonlSessionStore(self.root / "sessions")
        self.config = AgentConfig(
            max_same_tool_calls=5,
            max_output_tokens=100,
            tools=ToolConfig(enabled=frozenset({"read_file", "shell"})),
        )

    def client(self, provider):
        return TestClient(
            create_app(
                Workspace(self.root), lambda model: provider, self.config, self.store,
                models={"test": "test/model"}, default_model="test",
            ),
            base_url="http://127.0.0.1",
            headers={"host": "127.0.0.1"},
        )

    def receive_turn(self, socket):
        events = []
        while True:
            event = socket.receive_json()
            events.append(event)
            if event["type"] in {"done", "error"}:
                return events

    def test_gui_initializes_shared_default_configuration(self):
        directory = self.root / "config"
        with (
            patch("agent_gui.server.DEFAULT_CONFIG_DIRECTORY", directory),
            patch("agent_gui.server.DEFAULT_CONFIG_PATH", directory / "provider_config.json"),
            patch("agent_gui.server.DEFAULT_AGENT_CONFIG_PATH", directory / "agent_config.json"),
            patch("agent_gui.server.load_dotenv") as load_dotenv,
            patch("uvicorn.run") as serve,
            patch("builtins.print"),
        ):
            main(["--workspace", str(self.root)])
        self.assertTrue((directory / "provider_config.json").is_file())
        self.assertTrue((directory / "agent_config.json").is_file())
        load_dotenv.assert_called_once_with(directory / ".env")
        with TestClient(serve.call_args.args[0], base_url="http://127.0.0.1") as client:
            self.assertEqual(client.get("/api/models").json()["default"], "openai")

    def test_gui_custom_configuration_persists_session_in_workspace(self):
        directory = self.root / "config"
        directory.mkdir()
        provider_path = directory / "provider.json"
        provider_path.write_text(json.dumps({
            "provider": "test",
            "providers": {"test": {"model": "openai/test", "max_context_tokens": 1000}},
        }))
        agent_path = directory / "agent.json"
        agent_path.write_text(json.dumps({
            "max_same_tool_calls": 5,
            "max_output_tokens": 100,
            "tools": {name: False for name in ("read_file", "edit_file", "search_files", "list_directory", "shell")},
        }))
        with (
            patch("agent_gui.server.initialize_default_configs") as initialize,
            patch("agent_gui.server.load_dotenv") as load_dotenv,
            patch("uvicorn.run") as serve,
            patch("builtins.print"),
        ):
            main(["--workspace", str(self.root), "--config", str(provider_path), "--agent-config", str(agent_path)])
        initialize.assert_not_called()
        load_dotenv.assert_called_once_with(directory / ".env")
        with (
            patch("agent_gui.server.LiteLLMProvider", return_value=MockProvider(["saved"])),
            TestClient(serve.call_args.args[0], base_url="http://127.0.0.1", headers={"host": "127.0.0.1"}) as client,
        ):
            with client.websocket_connect("/api/sessions/from-gui/run") as socket:
                socket.send_json({"model": "test", "message": "hello"})
                self.assertEqual(self.receive_turn(socket)[-1]["type"], "done")
        self.assertEqual(self.store.load("from-gui").items[-1].content, "saved")
        self.assertTrue((self.root / "sessions" / "from-gui.jsonl").is_file())

    def test_selects_provider_per_turn_and_keeps_session_context(self):
        first = MockProvider(["第一个模型的回答"])
        second = MockProvider(["第二个模型的回答"])
        factory = unittest.mock.Mock(side_effect=lambda name: {"first": first, "second": second}[name])
        app = create_app(
            Workspace(self.root), factory, self.config, self.store,
            models={"first": "openai/first", "second": "openai/second"},
            default_model="first",
        )
        with TestClient(app, base_url="http://127.0.0.1", headers={"host": "127.0.0.1"}) as client:
            self.assertEqual(client.get("/api/models").json(), {
                "default": "first",
                "models": [{"id": "first", "model": "openai/first"}, {"id": "second", "model": "openai/second"}],
            })
            factory.assert_not_called()
            for model in ("first", "second"):
                with client.websocket_connect("/api/sessions/switch/run") as socket:
                    socket.send_json({"model": model, "message": "你好"})
                    self.assertEqual(self.receive_turn(socket)[-1]["type"], "done")
            self.assertEqual([call.args[0] for call in factory.call_args_list], ["first", "second"])
            self.assertEqual(len(second.requests[0].messages), 3)
            self.assertIn("第一个模型的回答", second.requests[0].messages[1].content)
            for model in ("unknown", None):
                with client.websocket_connect("/api/sessions/switch/run") as socket:
                    socket.send_json({"model": model, "message": "你好"})
                    self.assertEqual(self.receive_turn(socket)[-1]["type"], "error")
            self.assertEqual(factory.call_count, 2)
            self.assertEqual(len(self.store.load("switch").items), 4)

    def test_streams_tools_and_resumes_the_same_session_as_cli(self):
        call = ToolCall("read-1", "read_file", {"path": "README.md"})
        provider = MockProvider([
            LLMResponse("让我看看。", tool_calls=(call,)),
            "这是一个项目。",
            "继续讨论。",
        ])
        with self.client(provider) as client:
            self.assertEqual(client.get("/api/sessions").json(), [])
            with client.websocket_connect("/api/sessions/example/run") as socket:
                socket.send_json({"model": "test", "message": "帮我检查这个项目"})
                events = self.receive_turn(socket)
            self.assertEqual([event["type"] for event in events], [
                "AssistantMessageEvent", "ToolBatchStartedEvent", "ToolCallEvent",
                "ToolResultEvent", "AssistantMessageEvent", "done",
            ])
            self.assertIn("Hello Jarvis", str(events[3]["tool_result"]["output"]))
            self.assertEqual(client.get("/api/sessions").json()[0]["title"], "帮我检查这个项目")
            saved = client.get("/api/sessions/example").json()
            self.assertEqual(saved["items"], events[-1]["session"]["items"])
            self.assertEqual(len(self.store.load("example").items), 4)
            with client.websocket_connect("/api/sessions/example/run") as socket:
                socket.send_json({"model": "test", "message": "继续"})
                self.assertEqual(self.receive_turn(socket)[-1]["type"], "done")
            self.assertEqual(len(provider.requests[-1].messages), 5)
            self.assertEqual(provider.requests[-1].messages[2].tool_call_id, "read-1")

    def test_shell_waits_for_explicit_approval_and_handles_denial(self):
        for approved in (True, False):
            with self.subTest(approved=approved):
                provider = MockProvider([
                    LLMResponse(None, tool_calls=(ToolCall("shell-1", "shell", {"command": "pwd"}),)),
                    "完成。",
                ])
                with self.client(provider) as client, patch(
                    "agent_gui.server.SubprocessCommandExecutor.execute",
                    return_value=CommandExecutionResult("pwd", 0, str(self.root), ""),
                ) as execute:
                    with client.websocket_connect(f"/api/sessions/shell-{approved}/run") as socket:
                        socket.send_json({"model": "test", "message": "执行 pwd"})
                        self.assertEqual(socket.receive_json()["type"], "ToolBatchStartedEvent")
                        self.assertEqual(socket.receive_json()["type"], "ToolCallEvent")
                        approval = socket.receive_json()
                        self.assertEqual(approval["type"], "approval_required")
                        self.assertEqual(approval["command"], "pwd")
                        execute.assert_not_called()
                        socket.send_json({"type": "approval", "id": approval["id"], "approved": approved})
                        events = self.receive_turn(socket)
                    result = events[0]["tool_result"]
                    if approved:
                        execute.assert_called_once_with("pwd")
                        self.assertIsNone(result["error"])
                    else:
                        execute.assert_not_called()
                        self.assertEqual(result["error"]["type"], "PermissionError")
                    self.assertEqual(events[-1]["type"], "done")

    def test_rejects_concurrent_runs_while_waiting_for_approval(self):
        provider = MockProvider([
            LLMResponse(None, tool_calls=(ToolCall("shell-1", "shell", {"command": "pwd"}),)),
            "已拒绝。",
        ])
        with self.client(provider) as client:
            with client.websocket_connect("/api/sessions/first/run") as first:
                first.send_json({"model": "test", "message": "pwd"})
                first.receive_json()
                first.receive_json()
                approval = first.receive_json()
                with client.websocket_connect("/api/sessions/second/run") as second:
                    self.assertEqual(second.receive_json()["type"], "error")
                first.send_json({"type": "approval", "id": approval["id"], "approved": False})
                self.assertEqual(self.receive_turn(first)[-1]["type"], "done")
            self.assertEqual(len(provider.requests), 2)

    def test_failed_run_is_not_saved_and_next_run_can_proceed(self):
        provider = MockProvider([LLMResponse(None), "第二轮成功。"])
        with self.client(provider) as client:
            with client.websocket_connect("/api/sessions/failure/run") as socket:
                socket.send_json({"model": "test", "message": "第一轮"})
                self.assertEqual(self.receive_turn(socket)[-1]["type"], "error")
            self.assertEqual(self.store.load("failure").items, [])
            with client.websocket_connect("/api/sessions/failure/run") as socket:
                socket.send_json({"model": "test", "message": "第二轮"})
                self.assertEqual(self.receive_turn(socket)[-1]["type"], "done")
            self.assertEqual(len(provider.requests[-1].messages), 1)

    def test_workspace_listing_rejects_traversal_and_external_symlinks(self):
        (self.root / "outside").symlink_to(self.root.parent)
        with self.client(MockProvider([])) as client:
            listing = client.get("/api/workspace").json()
            self.assertEqual(listing["root"], str(self.root.resolve()))
            self.assertIn({"name": "src", "type": "directory"}, listing["entries"])
            self.assertEqual(client.get("/api/workspace?path=src").json()["entries"], [])
            for path in ("..", "/tmp", "outside"):
                self.assertEqual(client.get("/api/workspace", params={"path": path}).status_code, 400)

    def test_rejects_foreign_websocket_origins_and_hosts(self):
        with self.client(MockProvider([])) as client:
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect("/api/sessions/test/run", headers={"origin": "https://other.example"}):
                    pass
            self.assertEqual(client.get("/api/sessions", headers={"host": "other.example"}).status_code, 400)

    def test_reads_history_written_by_cli_without_exposing_request_config(self):
        self.store.append_turn("from-cli", LLMRequest("private prompt", ()), LLMResponse("你好"), (
            Message("user", "CLI 对话"), Message("assistant", "你好"),
        ))
        with self.client(MockProvider([])) as client:
            self.assertEqual(client.get("/api/sessions").json()[0]["session_id"], "from-cli")
            data = client.get("/api/sessions/from-cli").json()
            self.assertEqual(data["items"][0]["content"], "CLI 对话")
            self.assertNotIn("request", data)
            self.assertNotIn("private prompt", json.dumps(data))
