"""Process entry point for the agent bridge.

Claims a private protocol channel before any provider import, because
LiteLLM writes diagnostics straight to stdout on failure and would
otherwise corrupt the newline-delimited JSON stream.
"""

import os
import sys
from typing import TextIO


def _claim_stdout() -> TextIO:
    protocol_fd = os.dup(1)
    os.dup2(2, 1)  # print()/library banners now land on stderr
    return os.fdopen(protocol_fd, "w", encoding="utf-8", buffering=1)


def main() -> None:
    protocol_out = _claim_stdout()

    from .bridge import Bridge

    bridge = Bridge(sys.stdin, protocol_out)
    try:
        first = bridge.read_message()
        if first is None:
            return
        if first["type"] != "start":
            bridge.emit(
                "fatal",
                error={
                    "type": "ProtocolError",
                    "message": "first message must be 'start'",
                },
            )
            raise SystemExit(1)
        bridge.start(first)
    except SystemExit:
        raise
    except BaseException as error:
        bridge.emit(
            "fatal",
            error={"type": type(error).__name__, "message": str(error)},
        )
        raise SystemExit(1)

    bridge.serve()


if __name__ == "__main__":
    main()
