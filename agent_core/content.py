"""Provider-neutral multimodal message parts.

Images are represented by a workspace path until a provider request is
constructed.  This keeps session logs small and avoids persisting encoded
media in the runtime protocol.
"""

from dataclasses import dataclass, field
from typing import Literal, TypeAlias


@dataclass(frozen=True)
class TextPart:
    text: str = ""
    type: Literal["text"] = field(default="text", init=False)


@dataclass(frozen=True)
class ImagePart:
    path: str = ""
    mime_type: str = "image/png"
    type: Literal["image"] = field(default="image", init=False)


ContentPart: TypeAlias = TextPart | ImagePart
Content: TypeAlias = str | tuple[ContentPart, ...] | None


def content_parts(content: Content) -> tuple[ContentPart, ...]:
    if content is None:
        return ()
    if isinstance(content, str):
        return (TextPart(text=content),)
    return content


def text_content(content: Content) -> str | None:
    parts = content_parts(content)
    if not parts:
        return None
    text = "".join(part.text for part in parts if isinstance(part, TextPart))
    return text or None


def historical_content(content: Content) -> str | None:
    """Return text suitable for old turns and context compression.

    Media is intentionally omitted: historical context must not cause the
    same image bytes to be uploaded again on every model call.
    """
    text = text_content(content)
    has_image = any(isinstance(part, ImagePart) for part in content_parts(content))
    if text and has_image:
        return f"{text}\n[Image attachment omitted from historical context]"
    if has_image:
        return "[Image attachment omitted from historical context]"
    return text
