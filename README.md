# AKI Real-Time Inference Service

This service connects to a stream of HL7v2 messages over MLLP, acknowledges each message, maintains patient state from a historical CSV file, and sends HTTP pager alerts when Acute Kidney Injury (AKI) is detected.

---

## Run Locally (Python)

Start the HL7 simulator:

```bash
python3 tools/simulator/simulator.py \
  --messages tests/fixtures/messages.mllp \
  --mllp 8440 \
  --pager 8441
```

In a separate terminal, run the inference service from the repository root:

```bash
export MLLP_ADDRESS=localhost:8440
export PAGER_ADDRESS=localhost:8441
export HISTORY_CSV=tests/fixtures/history.csv

python3 -m src.main
```

---

## Run with Docker

Build the image:

```bash
docker build -t aki-infer .
```

Start the simulator (on host):

```bash
python3 tools/simulator/simulator.py \
  --messages tests/fixtures/messages.mllp \
  --mllp 8440 \
  --pager 8441
```

Run the container:

```bash
docker run --rm \
  -e MLLP_ADDRESS=host.docker.internal:8440 \
  -e PAGER_ADDRESS=host.docker.internal:8441 \
  -e HISTORY_CSV=/data/history.csv \
  -v "$(pwd)/tests/fixtures/history.csv:/data/history.csv:ro" \
  aki-infer
```

---

## Environment Variables

- `MLLP_ADDRESS` – Host:port of the MLLP server (default: `localhost:8440`)
- `PAGER_ADDRESS` – Host:port of the pager HTTP server (default: `localhost:8441`)
- `HISTORY_CSV` – Path to historical blood test data (default: `/data/history.csv`)
- `MODEL_PATH` – Path to trained model (default: `model.joblib`)
- `PAGER_TIMEOUT` – Timeout (seconds) for pager HTTP request (default: `1.0`)

---

## Running Tests

```bash
pytest -q tests
```

---

## Assessment Environment Notes

In the assessment environment:

- The simulator provides `MLLP_ADDRESS` and `PAGER_ADDRESS`
- Historical data is mounted at `/data/history.csv`
- The service runs inside a single Docker container
- The entrypoint is:

```bash
python -m src.main
```
