from datetime import datetime, timezone

def build_ack() -> bytes:
    """
    Build a minimal HL7 ACK message (AA).

    Returns:
        HL7 message bytes (not MLLP-framed).
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    ack = (
        f"MSH|^~\\&|||||{timestamp}||ACK|||2.5\r"
        "MSA|AA\r"
    )
    return ack.encode("ascii")