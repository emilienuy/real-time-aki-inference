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
    return bytes([MLLP_START_OF_BLOCK]) + hl7_message + bytes([MLLP_END_OF_BLOCK, MLLP_CARRIAGE_RETURN])


def extract_mllp_messages(buffer: bytearray) -> list[bytes]:
    """
    Extract complete MLLP-framed HL7 messages from a stream buffer.

    Args:
        buffer: A mutable byte buffer containing bytes read from a TCP stream.
                This may contain partial messages or multiple messages.

    Returns:
        A list of HL7 message payloads (bytes), with MLLP framing removed.
    """
    hl7_messages: list[bytes] = []

    block_start = bytes([MLLP_START_OF_BLOCK])
    block_end = bytes([MLLP_END_OF_BLOCK])

    while True:
        start_index = buffer.find(block_start)
        if start_index == -1:
            buffer.clear()
            break

        if start_index > 0:
            del buffer[:start_index]

        end_index = buffer.find(block_end, 1)
        if end_index == -1:
            break

        # Need CR after EOB
        if end_index + 1 >= len(buffer):
            break
        if buffer[end_index + 1] != MLLP_CARRIAGE_RETURN:
            # Bad framing; drop one byte to try to resync
            del buffer[0:1]
            continue

        hl7_messages.append(bytes(buffer[1:end_index]))
        del buffer[: end_index + 2]  # consume through EOB+CR

    return hl7_messages