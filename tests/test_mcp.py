import os
import sys
import unittest
from pathlib import Path

from agent_core import ToolCall
from agent_core.mcp.config import load_mcp_config
from agent_core.mcp.tool import McpTool, qualified_tool_name
from agent_core.mcp.manager import McpClientManager
from agent_core.tools.policy import McpApprovalPolicy


class McpConfigTest(unittest.TestCase):
    def test_loads_stdio_and_expands_environment(self) -> None:
        os.environ["MCP_TOKEN_TEST"] = "secret"
        config = load_mcp_config(
            {
                "enabled": True,
                "servers": {
                    "demo": {
                        "transport": "stdio",
                        "command": "python",
                        "args": ["server.py"],
                        "env": {"TOKEN": "${MCP_TOKEN_TEST}"},
                        "tool_allowlist": ["echo"],
                    }
                },
            }
        )
        server = config.servers[0]
        self.assertEqual(server.env["TOKEN"], "secret")
        self.assertEqual(server.tool_allowlist, frozenset({"echo"}))

    def test_rejects_transport_specific_fields(self) -> None:
        with self.assertRaises(ValueError):
            load_mcp_config(
                {
                    "servers": {
                        "demo": {
                            "transport": "stdio",
                            "command": "python",
                            "url": "https://example.test/mcp",
                        }
                    }
                }
            )

    def test_rejects_unknown_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown"):
            load_mcp_config(
                {
                    "servers": {
                        "demo": {
                            "transport": "streamable_http",
                            "url": "https://example.test/mcp",
                            "unexpected": True,
                        }
                    }
                }
            )


class McpToolTest(unittest.TestCase):
    def test_qualifies_remote_name_and_delegates(self) -> None:
        calls = []

        class Manager:
            def call_tool(self, server, tool, arguments):
                calls.append((server, tool, arguments))
                return {"ok": True}

        adapted = McpTool(
            Manager(), "demo", "echo.text", "Echo", {"type": "object"}
        )
        self.assertEqual(adapted.definition.name, "mcp__demo__echo_text")
        self.assertEqual(adapted.execute({"text": "hi"}), {"ok": True})
        self.assertEqual(calls, [("demo", "echo.text", {"text": "hi"})])
        self.assertEqual(qualified_tool_name("demo", "echo.text"), "mcp__demo__echo_text")

    def test_approval_policy_only_prompts_selected_servers(self) -> None:
        prompts = []
        policy = McpApprovalPolicy(lambda call: prompts.append(call.name) or False, {"demo"})
        with self.assertRaises(PermissionError):
            policy.authorize(ToolCall("1", "mcp__demo__echo", {}))
        policy.authorize(ToolCall("2", "mcp__other__echo", {}))
        self.assertEqual(prompts, ["mcp__demo__echo"])


class McpClientManagerTest(unittest.TestCase):
    def test_discovers_calls_and_closes_fake_stdio_server(self) -> None:
        config = load_mcp_config(
            {
                "enabled": True,
                "servers": {
                    "fake": {
                        "transport": "stdio",
                        "command": sys.executable,
                        "args": [str(Path(__file__).with_name("fake_mcp_server.py"))],
                        "tool_allowlist": ["echo"],
                        "approval": "never",
                    }
                },
            }
        )
        statuses = []
        manager = McpClientManager(config, Path.cwd(), statuses.append)
        try:
            tools = manager.start()
            self.assertEqual(
                [tool.definition.name for tool in tools],
                ["mcp__fake__echo"],
            )
            result = tools[0].execute({"text": "hello"})
            self.assertFalse(result["is_error"])
            self.assertEqual(result["structured_content"], {"echo": "hello"})
        finally:
            manager.close()
        self.assertEqual(statuses[0].status, "connecting")
        self.assertEqual(statuses[-1].status, "closed")


if __name__ == "__main__":
    unittest.main()
