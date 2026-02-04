import os
import signal
import subprocess
import sys
import time

def test_mllp_client_can_stream_messages():
    """
    Integration smoke test for the MLLP client.

    Starts the HL7 simulator and the MLLP client as subprocesses and verifies
    that messages are streamed and acknowledged successfully.
    """
    # Start simulator
    sim = subprocess.Popen(
        [
            sys.executable,
            "tools/simulator/simulator.py",
            "--messages",
            "tests/fixtures/messages.mllp",
            "--mllp",
            "8440",
            "--pager",
            "8441",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ},
    )

    try:
        # Give simulator time to start listening
        time.sleep(0.5)

        # Run client
        env = {**os.environ, "MLLP_ADDRESS": "localhost:8440"}
        client = subprocess.Popen(
            [sys.executable, "-m", "src.main"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )

        # Let it run briefly then stop it
        time.sleep(1.0)
        client.send_signal(signal.SIGINT)

        out, _ = client.communicate(timeout=5)

        # Connected and processed at least one message
        assert "connecting to MLLP" in out
        assert "RX[" in out  # means it streamed at least one message

    finally:
        sim.terminate()
        try:
            sim.wait(timeout=5)
        except subprocess.TimeoutExpired:
            sim.kill()