MLLP_START_OF_BLOCK = 0x0b
MLLP_END_OF_BLOCK = 0x1c
MLLP_CARRIAGE_RETURN = 0x0d


def wrap_mllp_message(hl7_message: bytes) -> bytes:
    """ 
    Wrap a raw HL7 message (bytes) in an MLLP frame.

    MLLP framing:
      - start of block: 0x0b
      - end of block: 0x1c
      - carriage return: 0x0d

    Returns the framed bytes ready to send on a TCP socket.
    """
    raise NotImplementedError


def extract_mllp_messages(buffer: bytearray) -> list[bytes]:
    """
    Extract complete MLLP-framed HL7 messages from a stream buffer.

    Args:
        buffer: A mutable byte buffer containing bytes read from a TCP stream.
                This may contain partial messages or multiple messages.

    Returns:
        A list of HL7 message payloads (bytes), with MLLP framing removed.
    """
    raise NotImplementedError