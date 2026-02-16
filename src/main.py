import csv
import logging
import os
import socket
import time
from collections import defaultdict

from src.ack import build_ack
from src.hl7 import parse_hl7_message
from src.http import request as pager_request
from src.mllp import extract_mllp_messages, wrap_mllp_message
from src.model import AkiModel


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
    from src.model import AkiModel

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


def _iter_messages(sock):
    buffer = bytearray()
    while True:
        try:
            chunk = sock.recv(4096)
        except (TimeoutError, socket.timeout):
            continue  # no data yet; keep waiting
        if not chunk:
            return
        if not chunk:
            return
        buffer.extend(chunk)
        for msg in extract_mllp_messages(buffer):
            yield msg


def main():
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

    mllp_address = os.environ.get("MLLP_ADDRESS", "localhost:8440")
    host, port = _parse_hostport(mllp_address)

    # Default to assessment layout but keep everything configurable for local runs/tests.
    history_path = os.environ.get("HISTORY_CSV", "/data/history.csv")
    aki_path = os.environ.get("AKI_CSV", "")
    # Load the pre-trained CW1 model by default.
    model_path = os.environ.get("MODEL_PATH", "model.joblib")
    pager_address = os.environ.get("PAGER_ADDRESS", "localhost:8441")
    pager_host, pager_port = _parse_hostport(pager_address)

    # PAGER_ALWAYS is used in integration tests to make paging deterministic.
    force_page = os.environ.get("PAGER_ALWAYS", "0") == "1"

    print(f"connecting to MLLP at {host}:{port} ...")
    logging.info("connecting to MLLP at %s:%s", host, port)
    # The simulator may take a moment to bind; retry briefly before failing.
    deadline = time.time() + 5.0
    while True:
        try:
            sock = socket.create_connection((host, port), timeout=10)
            break
        except OSError:
            if time.time() >= deadline:
                raise
            time.sleep(0.1)

    from src.data_processing import read_history, update_history

    # History is required to compute features for inference.
    history = read_history(history_path) if os.path.exists(history_path) else defaultdict(dict)
    # SKIP_MODEL lets smoke tests avoid expensive model imports/training.
    skip_model = os.environ.get("SKIP_MODEL", "0") == "1"
    if skip_model:
        model = None
    else:
        model = _load_model(model_path)
        if model is None and aki_path:
            model = _fit_model(history_path, aki_path)

    count = 0
    for msg in _iter_messages(sock):
        count += 1
        # Emit progress for the smoke test and for long-running streams.
        text = msg.decode("ascii", errors="replace")
        msh = text.split("\r", 1)[0]
        if count == 1 or count % 1000 == 0:
            print(f"RX[{count}] {msh}")

        parsed = parse_hl7_message(msg)

        # Always ACK to keep the stream moving
        sock.sendall(wrap_mllp_message(build_ack()))

        if not parsed.valid:
            continue

        history = update_history(history, parsed)

        if parsed.msg_type == "ORU^R01" and parsed.result.test_type == "CREATININE":
            patient_record = history.get(int(parsed.mrn), {})
            if _should_page(force_page, model, patient_record):
                pager_request(pager_port, parsed, host=pager_host)

    logging.info("finished, processed %s messages", count)


if __name__ == "__main__":
    main()
