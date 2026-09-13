from ...content import ImagePart, TextPart
from ...session import Message
from ...llm import LLMProvider, LLMRequest
from ...workspace import Workspace
from ..base import JSONValue, Tool, ToolDefinition


class AnalyzeImageTool(Tool):
    """Ask a vision-capable provider about an image stored in the workspace."""

    def __init__(self, provider: LLMProvider, workspace: Workspace) -> None:
        self._provider = provider
        self._workspace = workspace

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="analyze_image",
            description="Analyze an image attachment and answer a question about it.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "question": {"type": "string"},
                },
                "required": ["path", "question"],
            },
        )

    def execute(self, arguments: dict[str, JSONValue]) -> JSONValue:
        path = arguments.get("path")
        question = arguments.get("question")
        if not isinstance(path, str) or not path:
            raise ValueError("path must be a non-empty string")
        if not isinstance(question, str) or not question:
            raise ValueError("question must be a non-empty string")
        resolved = self._workspace.resolve_path(path)
        if not resolved.is_file():
            raise ValueError(f"image does not exist: {path}")
        if "image" not in self._provider.capabilities.input_modalities:
            raise ValueError("the configured provider does not support image input")
        response = self._provider.stream(
            LLMRequest(
                system_prompt="Analyze the supplied image and answer the user's question.",
                messages=(
                    Message(
                        role="user",
                        content=(
                            TextPart(text=question),
                            ImagePart(path=str(resolved)),
                        ),
                    ),
                ),
            ),
            lambda _text: None,
        )
        if response.tool_calls or not response.content:
            raise ValueError("image analysis provider returned no text")
        return response.content
