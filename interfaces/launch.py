"""Console script that hands the terminal to the Ink UI.

``execvp`` replaces this process so Node inherits the TTY directly and
no Python parent sits between the terminal and the UI mangling signals.
"""

import os
import shutil
import sys
from importlib.resources import files
from pathlib import Path

from .bridge.config import default_config_directory, initialize_default_configs


def ui_bundle_path() -> Path:
    return Path(str(files("interfaces").joinpath("tui/dist/app.js")))


def main() -> None:
    node = shutil.which("node")
    if node is None:
        raise SystemExit(
            "Jarvis requires Node.js 22 or newer on PATH for its terminal "
            "interface. Install it from https://nodejs.org and try again."
        )

    bundle = ui_bundle_path()
    if not bundle.is_file():
        raise SystemExit(
            f"Jarvis terminal interface is not built: {bundle} is missing. "
            "Run 'npm install && npm run build' in interfaces/tui."
        )

    initialize_default_configs(default_config_directory())

    # The bridge must run in the interpreter that owns agent_core.
    os.environ["JARVIS_PYTHON"] = sys.executable
    os.execvp(node, [node, str(bundle), *sys.argv[1:]])
