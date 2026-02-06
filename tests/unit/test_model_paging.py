import http.server
import threading

import pandas as pd

from src.hl7 import ParsedMessage, Result, EMPTY_PATIENT
from src.http import request as pager_request
from src.model import AkiModel


def _train_simple_model():
    # Linearly separable examples: high creatinine deltas -> positive.
    X = pd.DataFrame(
        [
            {"age": 50, "sex_m": 1, "num_results": 2, "latest": 220, "min_prev": 100, "median_prev": 100,
             "ratio_to_min": 2.2, "ratio_to_median": 2.2, "delta_to_min": 120, "delta_to_median": 120,
             "latest_delta": 70, "hours_since_previous": 24, "std_prev": 0},
            {"age": 60, "sex_m": 0, "num_results": 2, "latest": 25, "min_prev": 25, "median_prev": 25,
             "ratio_to_min": 1.0, "ratio_to_median": 1.0, "delta_to_min": 0, "delta_to_median": 0,
             "latest_delta": 0, "hours_since_previous": 24, "std_prev": 0},
            {"age": 45, "sex_m": 1, "num_results": 2, "latest": 210, "min_prev": 90, "median_prev": 95,
             "ratio_to_min": 2.3, "ratio_to_median": 2.2, "delta_to_min": 120, "delta_to_median": 115,
             "latest_delta": 80, "hours_since_previous": 12, "std_prev": 2},
            {"age": 70, "sex_m": 0, "num_results": 2, "latest": 30, "min_prev": 30, "median_prev": 30,
             "ratio_to_min": 1.0, "ratio_to_median": 1.0, "delta_to_min": 0, "delta_to_median": 0,
             "latest_delta": 0, "hours_since_previous": 12, "std_prev": 1},
        ]
    )
    y = [1, 0, 1, 0]

    model = AkiModel(threshold=0.5, random_state=0)
    model.fit(X, y)
    return model


def test_model_predicts_positive():
    model = _train_simple_model()

    X_pos = pd.DataFrame(
        [
            {"age": 55, "sex_m": 1, "num_results": 2, "latest": 230, "min_prev": 100, "median_prev": 105,
             "ratio_to_min": 2.3, "ratio_to_median": 2.19, "delta_to_min": 130, "delta_to_median": 125,
             "latest_delta": 90, "hours_since_previous": 24, "std_prev": 0},
        ]
    )

    pred = model.predict(X_pos)
    assert pred[0] == 1


def test_model_predicts_negative():
    model = _train_simple_model()

    X_neg = pd.DataFrame(
        [
            {"age": 65, "sex_m": 0, "num_results": 2, "latest": 28, "min_prev": 28, "median_prev": 28,
             "ratio_to_min": 1.0, "ratio_to_median": 1.0, "delta_to_min": 0, "delta_to_median": 0,
             "latest_delta": 0, "hours_since_previous": 24, "std_prev": 0},
        ]
    )

    pred = model.predict(X_neg)
    assert pred[0] == 0


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


def test_positive_detection_sends_http_request():
    server = http.server.ThreadingHTTPServer(("localhost", 0), _PagerHandler)
    server.received = []
    server.received_event = threading.Event()

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        model = _train_simple_model()
        X_pos = pd.DataFrame(
            [
                {"age": 55, "sex_m": 1, "num_results": 2, "latest": 230, "min_prev": 100, "median_prev": 105,
                 "ratio_to_min": 2.3, "ratio_to_median": 2.19, "delta_to_min": 130, "delta_to_median": 125,
                 "latest_delta": 90, "hours_since_previous": 24, "std_prev": 0},
            ]
        )
        pred = model.predict(X_pos)[0]
        assert pred == 1

        result = Result(timestamp="202401202243", test_type="CREATININE", value=103.4)
        msg = ParsedMessage(
            valid=True,
            msg_type="ORU^R01",
            message_time="202401201630",
            mrn="123",
            patient=EMPTY_PATIENT,
            result=result,
        )

        pager_request(server.server_address[1], msg, host="localhost")

        assert server.received_event.wait(timeout=3), "pager endpoint not called"
        assert server.received[0] == "123,202401202243"
    finally:
        server.shutdown()
