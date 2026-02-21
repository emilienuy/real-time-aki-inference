import csv
import logging
import os
import signal
import socket
import time
import pickle
from collections import defaultdict

from prometheus_client import start_http_server

from src.ack import build_ack
from src.hl7 import parse_hl7_message
from src.http import request as pager_request
from src.metrics import (
    AKI_PAGES_SENT,
    BLOOD_TESTS_RECEIVED,
    CREATININE_VALUE,
    MESSAGES_RECEIVED,
    MLLP_CONNECTIONS,
)
from src.mllp import extract_mllp_messages, wrap_mllp_message
from src.model import AkiModel


# ── Graceful shutdown ─────────────────────────────────────────────────────────

_shutdown = False
_current_sock = None


def _handle_sigterm(_signum, _frame):
    """Mark shutdown and close the socket so recv() unblocks immediately."""
    global _shutdown, _current_sock
    logging.info("SIGTERM received; shutting down gracefully")
    _shutdown = True
    if _current_sock is not None:
        try:
            _current_sock.close()
        except OSError:
            pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_hostport(addr):
    host, port_str = addr.split(":")
    return host, int(port_str)


def _load_aki_labels(path):
    labels = set()
    if not path or not os.path.exists(path):
        return labels

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                labels.add(int(row.get("mrn")))
            except (TypeError, ValueError):
                continue

    return labels


def _build_training_data(history, aki_labels):
    import pandas as pd
    from src.data_processing import construct_features

    rows = []
    y = []

    for mrn, record in history.items():
        creat_history = record.get("creatinine_history", [])
        if not creat_history:
            continue

        features = construct_features(record)
        rows.append(features)
        y.append(1 if int(mrn) in aki_labels else 0)

    if not rows:
        return pd.DataFrame(), []

    X = pd.concat(rows, ignore_index=True)
    return X, y


def _fit_model(history_path, aki_path):
    from src.data_processing import read_history

    if not history_path or not os.path.exists(history_path):
        logging.warning("history csv not found at %s; skipping model fit", history_path)
        return None

    history = read_history(history_path)
    aki_labels = _load_aki_labels(aki_path)
    X, y = _build_training_data(history, aki_labels)

    if len(X) == 0 or len(y) == 0:
        logging.warning("no training data available; skipping model fit")
        return None

    model = AkiModel(threshold=0.5)
    model.fit(X, y)
    return model


def _load_model(model_path):
    from joblib import load

    if not model_path or not os.path.exists(model_path):
        return None
    return load(model_path)


def _should_page(force_page, model, patient_record):
    from src.data_processing import construct_features

    if force_page:
        return True

    if model is None:
        return False

    creat_history = patient_record.get("creatinine_history", [])
    if not creat_history:
        return False

    features = construct_features(patient_record)
    pred = model.predict(features)
    return bool(len(pred) > 0 and pred[0] == 1)


def _connect_with_retry(host, port, retry_interval=5.0):
    """Keep trying to open a TCP connection until we succeed or shutdown is set.

    After a successful connect we set a 30-second recv timeout so that
    _iter_messages wakes up periodically even when the stream is idle,
    allowing the SIGTERM handler to take effect promptly.
    """
    global _current_sock
    while not _shutdown:
        try:
            sock = socket.create_connection((host, port), timeout=10)
            sock.settimeout(30)
            _current_sock = sock
            logging.info("Connected to MLLP at %s:%s", host, port)
            return sock
        except OSError as e:
            logging.warning(
                "Cannot connect to MLLP at %s:%s: %s; retrying in %.0fs",
                host, port, e, retry_interval,
            )
            time.sleep(retry_interval)
    return None


def _iter_messages(sock):
    buffer = bytearray()
    while True:
        try:
            chunk = sock.recv(4096)
        except (TimeoutError, socket.timeout):
            continue  # idle; loop back so _shutdown can be checked by the caller
        if not chunk:
            return  # server closed the connection cleanly
        buffer.extend(chunk)
        for msg in extract_mllp_messages(buffer):
            yield msg


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    global _current_sock

    signal.signal(signal.SIGTERM, _handle_sigterm)

    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

    # Prometheus metrics endpoint (scraped by the cluster's Prometheus instance).
    metrics_port = int(os.environ.get("METRICS_PORT", "8000"))
    start_http_server(metrics_port)
    logging.info("Prometheus metrics on port %d", metrics_port)

    mllp_address = os.environ.get("MLLP_ADDRESS", "localhost:8440")
    host, port = _parse_hostport(mllp_address)

    history_path = os.environ.get("HISTORY_CSV", "/data/history.csv")
    aki_path = os.environ.get("AKI_CSV", "")
    model_path = os.environ.get("MODEL_PATH", "model.joblib")
    pager_address = os.environ.get("PAGER_ADDRESS", "localhost:8441")
    pager_host, pager_port = _parse_hostport(pager_address)

    force_page = os.environ.get("PAGER_ALWAYS", "0") == "1"

    from src.data_processing import read_history, update_history

    if os.path.exists("/state/updated_history.pkl"):
        with open("/state/updated_history.pkl", "rb") as file:
            history = pickle.load(file)
    else:
        history = read_history(history_path) if os.path.exists(history_path) else defaultdict(dict)

    skip_model = os.environ.get("SKIP_MODEL", "0") == "1"
    if skip_model:
        model = None
    else:
        model = _load_model(model_path)
        if model is None and aki_path:
            model = _fit_model(history_path, aki_path)

    count = 0

    # Outer loop: reconnect whenever the MLLP connection is lost.
    while not _shutdown:
        sock = _connect_with_retry(host, port)
        if sock is None:
            break  # _shutdown was set while waiting to connect

        MLLP_CONNECTIONS.inc()

        try:
            for msg in _iter_messages(sock):
                if _shutdown:
                    break

                count += 1
                MESSAGES_RECEIVED.inc()

                text = msg.decode("ascii", errors="replace")
                msh = text.split("\r", 1)[0]
                if count == 1 or count % 100 == 0:
                    print(f"RX[{count}] {msh}")

                parsed = parse_hl7_message(msg)

                # Always ACK to keep the stream moving.
                sock.sendall(wrap_mllp_message(build_ack()))

                if not parsed.valid:
                    continue

                history, duplicate = update_history(history, parsed)

                if (not duplicate
                        and parsed.msg_type == "ORU^R01"
                        and parsed.result.test_type == "CREATININE"):
                    BLOOD_TESTS_RECEIVED.inc()
                    CREATININE_VALUE.observe(parsed.result.value)

                    patient_record = history.get(int(parsed.mrn), {})
                    if _should_page(force_page, model, patient_record):
                        AKI_PAGES_SENT.inc()
                        pager_request(pager_port, parsed, host=pager_host)

                    os.makedirs("/state", exist_ok=True)
                    with open("/state/updated_history.pkl", "wb") as file:
                        pickle.dump(history, file)

        except OSError as e:
            if _shutdown:
                break
            logging.warning("MLLP connection lost: %s; reconnecting in 5s", e)
            time.sleep(5)

        finally:
            _current_sock = None
            try:
                sock.close()
            except OSError:
                pass

    logging.info("Shutdown complete, processed %d messages total", count)


if __name__ == "__main__":
    main()
