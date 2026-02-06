import http.server
import os
import socket
import subprocess
import sys
import threading
import time

from src.mllp import wrap_mllp_message


class _PagerHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/page":
            self.send_response(400)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("ascii")
        self.server.received.append(body)
        self.server.received_event.set()

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def _start_pager_server():
    # Tiny in-process HTTP server to capture paging requests.
    server = http.server.ThreadingHTTPServer(("localhost", 0), _PagerHandler)
    server.received = []
    server.received_event = threading.Event()

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    host, port = server.server_address
    return server, port


def _start_mllp_server(hl7_message):
    # Single-message MLLP server so we can exercise the client end-to-end.
    ready = threading.Event()
    port_holder = {}

    def _serve():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("localhost", 0))
            s.listen(1)
            port_holder["port"] = s.getsockname()[1]
            ready.set()

            conn, _ = s.accept()
            with conn:
                conn.sendall(wrap_mllp_message(hl7_message))
                conn.settimeout(5)
                try:
                    conn.recv(4096)  # best-effort read ACK
                except Exception:
                    pass

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    ready.wait(timeout=2)
    return port_holder["port"], thread


def test_paging_smoke():
    pager, pager_port = _start_pager_server()

    # Minimal ORU^R01 with creatinine so the client attempts paging.
    hl7_message = (
        "MSH|^~\\&|SIM|SOUTH RIVERSIDE|||202401201630||ORU^R01|||2.5\r"
        "PID|1||123\r"
        "OBR|1||||||202401202243\r"
        "OBX|1|SN|CREATININE||103.4\r"
    ).encode("ascii")

    mllp_port, _ = _start_mllp_server(hl7_message)

    # Force paging regardless of model output so this test is deterministic.
    env = {
        **os.environ,
        "MLLP_ADDRESS": f"localhost:{mllp_port}",
        "PAGER_PORT": str(pager_port),
        "PAGER_HOST": "localhost",
        "PAGER_ALWAYS": "1",
        "HISTORY_CSV": "tests/fixtures/history.csv",
        "AKI_CSV": "tests/fixtures/aki.csv",
        "LOG_LEVEL": "WARNING",
    }

    client = subprocess.Popen(
        [sys.executable, "-m", "src.main"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    try:
        assert pager.received_event.wait(timeout=5), "pager was not called"
    finally:
        try:
            client.wait(timeout=5)
        except subprocess.TimeoutExpired:
            client.terminate()

        pager.shutdown()

    assert pager.received
    assert pager.received[0] == "123,202401202243"
