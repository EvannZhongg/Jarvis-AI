from mcp.server.mcpserver import MCPServer


server = MCPServer("nosis-test")


@server.tool(description="Echo text from the fake MCP server")
def echo(text: str) -> dict[str, str]:
    return {"echo": text}


@server.tool(description="A tool excluded by the integration allowlist")
def hidden() -> str:
    return "hidden"


if __name__ == "__main__":
    server.run("stdio")
