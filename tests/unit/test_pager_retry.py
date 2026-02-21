"""Tests for pager HTTP retry behaviour and failure handling."""
import http.server
import threading
from unittest.mock import patch

from src.hl7 import EMPTY_PATIENT, ParsedMessage, Result
from src.http import request as pager_request


def _make_msg(mrn="42", timestamp="202401201630"):
    return ParsedMessage(
        valid=True,
        msg_type="ORU^R01",
        message_time=timestamp,
        mrn=mrn,
        patient=EMPTY_PATIENT,
        result=Result(timestamp=timestamp, test_type="CREATININE", value=100.0),
    )


class _FlakyPagerHandler(http.server.BaseHTTPRequestHandler):
    """Returns 500 for the first `fail_count` requests, then 200."""

    def do_POST(self):
        if self.path != "/page":
            self.send_response(400)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)

        with self.server.lock:
            self.server.call_count += 1
            succeed = self.server.call_count > self.server.fail_count

        if succeed:
            self.server.success_event.set()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"error")

    def log_message(self, *args):
        pass  # suppress request logging in test output


def _start_flaky_server(fail_count):
    server = http.server.ThreadingHTTPServer(("localhost", 0), _FlakyPagerHandler)
    server.fail_count = fail_count
    server.call_count = 0
    server.lock = threading.Lock()
    server.success_event = threading.Event()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_pager_succeeds_after_one_transient_failure():
    """Request retries and succeeds on the second attempt."""
    server = _start_flaky_server(fail_count=1)
    try:
        port = server.server_address[1]
        with patch("src.http.time.sleep"):  # skip real sleep in tests
            pager_request(port, _make_msg(), host="localhost")

        assert server.success_event.wait(timeout=3), "pager never called successfully"
        assert server.call_count == 2  # one failure + one success
    finally:
        server.shutdown()


def test_pager_gives_up_after_max_retries_without_raising():
    """If the pager always fails, request() should log and return, not raise."""
    server = _start_flaky_server(fail_count=999)
    try:
        port = server.server_address[1]
        with patch("src.http.time.sleep"):
            # Must not raise even though every attempt fails.
            pager_request(port, _make_msg(), host="localhost")
    finally:
        server.shutdown()


def test_pager_error_counter_increments_on_failure():
    """PAGER_ERRORS counter increases for each failed attempt."""
    from src.metrics import PAGER_ERRORS

    before = PAGER_ERRORS._value.get()

    server = _start_flaky_server(fail_count=999)
    try:
        port = server.server_address[1]
        with patch("src.http.time.sleep"):
            pager_request(port, _make_msg(), host="localhost")
    finally:
        server.shutdown()

    after = PAGER_ERRORS._value.get()
    # Should have incremented once per attempt (3 attempts = 3 errors).
    assert after - before == 3
