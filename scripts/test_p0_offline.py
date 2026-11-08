"""Run pytest with outbound sockets disabled, including model and database calls."""
from __future__ import annotations

import os
import socket
import sys
import threading
from pathlib import Path

_socketpair_state = threading.local()
_original_connect = socket.socket.connect
_original_socketpair = socket.socketpair


def deny_network(*args, **kwargs):
    raise RuntimeError("Network access is disabled by the CampusMind offline test runner")


def offline_connect(sock, address):
    if (getattr(_socketpair_state, "active", False)
            and address[0] in {"127.0.0.1", "::1"}):
        return _original_connect(sock, address)
    return deny_network()


def internal_socketpair(*args, **kwargs):
    # Windows implements asyncio's self-pipe using a loopback socket pair.
    _socketpair_state.active = True
    try:
        return _original_socketpair(*args, **kwargs)
    finally:
        _socketpair_state.active = False


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root / "src"))
    os.environ["RAG_EMBEDDING_PROVIDER"] = "deterministic"
    socket.socketpair = internal_socketpair
    socket.socket.connect = offline_connect
    socket.socket.connect_ex = deny_network
    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network
    from sqlalchemy import Engine, event

    @event.listens_for(Engine, "do_connect")
    def offline_database(dialect, connection_record, args, kwargs):
        # libpq can open sockets without going through Python's socket module.
        if dialect.name != "sqlite":
            deny_network()

    import pytest

    return pytest.main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
