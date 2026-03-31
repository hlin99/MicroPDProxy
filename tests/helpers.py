"""Shared test constants and dummy-node server bootstrap.

Importable from any test module (unlike ``conftest.py`` which is
auto-loaded by pytest but not importable as a regular module).
"""

import os
import socket
import threading
import time

import uvicorn

from dummy_nodes.decode_node import app as decode_app
from dummy_nodes.prefill_node import app as prefill_app

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOKENIZER_PATH = os.path.join(_REPO_ROOT, "tokenizers", "DeepSeek-R1")


def _free_port():
    """Find a free TCP port on localhost."""
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


_PREFILL_PORT = _free_port()
_DECODE_PORT = _free_port()


def _run_server(app, port):
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    uvicorn.Server(config).run()


# Start dummy nodes once when this module is first imported.
threading.Thread(
    target=_run_server, args=(prefill_app, _PREFILL_PORT), daemon=True
).start()
threading.Thread(
    target=_run_server, args=(decode_app, _DECODE_PORT), daemon=True
).start()
time.sleep(2)
