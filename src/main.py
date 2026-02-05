import os
import socket

from src.mllp import extract_mllp_messages, wrap_mllp_message
from src.ack import build_ack


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
    mllp_address = os.environ.get("MLLP_ADDRESS", "localhost:8440")
    host, port = parse_hostport(mllp_address)

    print(f"connecting to MLLP at {host}:{port} ...")
    sock = socket.create_connection((host, port), timeout=10)
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
            if count == 1 or count % 1000 == 0:
                print(f"RX[{count}] {msh}")

            # Send ACK (must be MLLP-framed)
            ack_bytes = wrap_mllp_message(build_ack())
            sock.sendall(ack_bytes)
    
    print(f"finished, processed {count} messages")


if __name__ == "__main__":
    main()
