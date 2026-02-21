"""Tests for the three failure modes in src/main.py:

  1. MLLP read error (connection closed mid-stream) → _iter_messages terminates cleanly
  2. MLLP connection initially failing → _connect_with_retry retries until success
  3. SIGTERM → _handle_sigterm sets shutdown flag and closes socket
"""
import socket
import threading
import time

import src.main as main_module
from src.mllp import wrap_mllp_message


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bind_free_port():
    """Return a (server_socket, port) bound to a free OS-assigned port."""
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("localhost", 0))
    return s, s.getsockname()[1]


# ── Failure mode 1: MLLP read error (connection reset / closed) ───────────────

def test_iter_messages_returns_cleanly_when_server_closes_connection():
    """If the server closes the connection, _iter_messages must return (not hang).

    This covers the 'connection reset by peer' failure mode.
    """
    server, port = _bind_free_port()
    server.listen(1)

    def _accept_and_close():
        conn, _ = server.accept()
        conn.close()  # immediately drop the connection

    threading.Thread(target=_accept_and_close, daemon=True).start()

    client = socket.create_connection(("localhost", port))
    client.settimeout(2.0)

    messages = list(main_module._iter_messages(client))

    assert messages == []  # no messages yielded, but no hang or exception
    client.close()
    server.close()


def test_iter_messages_yields_message_before_server_closes():
    """_iter_messages yields complete messages before the connection closes."""
    hl7 = b"MSH|^~\\&|SIM|||||||ORU^R01|||2.5\r"
    server, port = _bind_free_port()
    server.listen(1)

    def _send_one_then_close():
        conn, _ = server.accept()
        conn.sendall(wrap_mllp_message(hl7))
        conn.close()

    threading.Thread(target=_send_one_then_close, daemon=True).start()

    client = socket.create_connection(("localhost", port))
    client.settimeout(2.0)

    messages = list(main_module._iter_messages(client))

    assert messages == [hl7]
    client.close()
    server.close()


# ── Failure mode 2: connection attempt failing, then succeeding ───────────────

def test_connect_with_retry_succeeds_immediately_when_server_is_up():
    """_connect_with_retry connects on the first attempt when the server is ready."""
    main_module._shutdown = False

    server, port = _bind_free_port()
    server.listen(1)
    threading.Thread(target=lambda: server.accept(), daemon=True).start()

    sock = main_module._connect_with_retry("localhost", port, retry_interval=0.1)

    assert sock is not None
    sock.close()
    server.close()
    main_module._current_sock = None


def test_connect_with_retry_retries_until_server_becomes_available():
    """_connect_with_retry keeps retrying and succeeds once the server starts.

    This covers the 'simulator restarts' failure mode.
    """
    main_module._shutdown = False

    # Reserve a port without listening on it yet.
    tmp = socket.socket()
    tmp.bind(("localhost", 0))
    port = tmp.getsockname()[1]
    tmp.close()

    # Start listening after a short delay.
    def _delayed_server():
        time.sleep(0.3)
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("localhost", port))
        server.listen(1)
        conn, _ = server.accept()
        conn.close()
        server.close()

    threading.Thread(target=_delayed_server, daemon=True).start()

    sock = main_module._connect_with_retry("localhost", port, retry_interval=0.1)

    assert sock is not None
    sock.close()
    main_module._current_sock = None


# ── Failure mode 3: SIGTERM ───────────────────────────────────────────────────

def test_sigterm_handler_sets_shutdown_flag():
    """_handle_sigterm sets _shutdown to True."""
    original = main_module._shutdown
    try:
        main_module._shutdown = False
        main_module._handle_sigterm(None, None)
        assert main_module._shutdown is True
    finally:
        main_module._shutdown = original


def test_sigterm_handler_closes_active_socket():
    """_handle_sigterm closes the current socket so recv() unblocks immediately."""
    original_shutdown = main_module._shutdown
    original_sock = main_module._current_sock

    server, port = _bind_free_port()
    server.listen(1)

    client_sock = socket.create_connection(("localhost", port))
    main_module._shutdown = False
    main_module._current_sock = client_sock

    try:
        main_module._handle_sigterm(None, None)

        assert main_module._shutdown is True

        # The socket should now be closed — any recv should raise OSError.
        try:
            client_sock.recv(1)
            assert False, "Expected OSError from closed socket"
        except OSError:
            pass  # expected

    finally:
        main_module._shutdown = original_shutdown
        main_module._current_sock = original_sock
        try:
            server.close()
        except OSError:
            pass
