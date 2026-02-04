# AKI Real-Time Inference Service

## Running the MLLP client locally
1. Start the HL7 simulator:
    ```bash
    python3 tools/simulator/simulator.py --messages tests/fixtures/messages.mllp

2. In a separate terminal, run the MLLP client:
    ```bash
    export MLLP_ADDRESS=localhost:8440
    python3 -m src.main


## Running tests
```bash
pytest -q tests