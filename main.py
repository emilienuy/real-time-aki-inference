import os
import socket

from src.mllp import extract_mllp_messages, wrap_mllp_message
from src.ack import build_ack
from src.hl7 import parse_hl7_message

from src.data_processing import read_history, update_history, construct_features
from src.model import AkiModel
from joblib import load


def parse_hostport(addr: str) -> tuple[str, int]:
    host, port_str = addr.split(":")
    return host, int(port_str)


def main():
    """
    MLLP client entrypoint.

    Connects to an HL7 MLLP server, receives HL7 messages from a TCP stream,
    extracts complete MLLP-framed messages, and sends HL7 ACKs (AA) to allow
    the sender to continue streaming.
    """
    
    # Use Emilie's model from Coursework 1
    model = load("model.joblib")

    # Read the provided history.csv file
    history_path = "data/history.csv"
    history = read_history(history_path)

    # Connect to the assessment simulator
    mllp_address = os.environ.get("MLLP_ADDRESS", "localhost:8440")
    mllp_host, mllp_port = parse_hostport(mllp_address)

    print(f"connecting to MLLP at {mllp_host}:{mllp_port} ...")
    sock = socket.create_connection((mllp_host, mllp_port), timeout=10)
    sock.settimeout(10)

    buffer = bytearray()
    count = 0

    while True:
        chunk = sock.recv(4096)
        if not chunk:
            print("server closed connection")
            break

        buffer.extend(chunk)

        hl7_messages = extract_mllp_messages(buffer)
        for msg in hl7_messages:
            count += 1

            # Print MSH lines so we can see progress
            text = msg.decode("ascii", errors="replace")
            msh = text.split("\r", 1)[0]
            # if count == 1 or count % 1000 == 0:
            #     print(f"RX[{count}] {msh}")

            # Send ACK (must be MLLP-framed)
            ack_bytes = wrap_mllp_message(build_ack())

            sock.sendall(ack_bytes)

            # Add the data from the parsed message to the history
            parsed_msg = parse_hl7_message(msg)          
            history = update_history(history, parsed_msg)

            # Make a prediction if a new test result is received
            if (parsed_msg.valid is True and 
                parsed_msg.msg_type == "ORU^R01" and
                parsed_msg.result.test_type == "CREATININE"):

                mrn = int(parsed_msg.mrn)

                patient_record = history[mrn]

                patient_features = construct_features(patient_record)
                is_AKI_predicted = model.predict(patient_features)[0]

                # Print the test that leads to a positive diagnosis
                if is_AKI_predicted:

                    print(f"{mrn}, {parsed_msg.result.timestamp}")
    
    # print(f"finished, processed {count} messages")


if __name__ == "__main__":
    main()
