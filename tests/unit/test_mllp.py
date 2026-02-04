from src.mllp import (
    wrap_mllp_message,
    extract_mllp_messages,
    MLLP_START_OF_BLOCK,
    MLLP_END_OF_BLOCK,
    MLLP_CARRIAGE_RETURN
)


def test_wrap_mllp_message_adds_markers_and_keeps_body():
    hl7_message = b"MSH|TEST\r"
    framed = wrap_mllp_message(hl7_message)

    assert framed[0] == MLLP_START_OF_BLOCK
    assert framed[-2] == MLLP_END_OF_BLOCK
    assert framed[-1] == MLLP_CARRIAGE_RETURN
    assert framed[1:-2] == hl7_message


def test_extract_single_message_consumes_buffer():
    hl7_message = b"MSH|ONE\r"
    buf = bytearray(wrap_mllp_message(hl7_message))

    msgs = extract_mllp_messages(buf)

    assert msgs == [hl7_message]
    assert buf == bytearray()


def test_extract_split_message_waits_for_more_bytes():
    hl7_message = b"MSH|SPLIT\r"
    framed = wrap_mllp_message(hl7_message)

    buf = bytearray(framed[:4])
    assert extract_mllp_messages(buf) == []

    buf.extend(framed[4:])
    msgs = extract_mllp_messages(buf)

    assert msgs == [hl7_message]
    assert buf == bytearray()


def test_extract_two_messages_back_to_back():
    m1 = b"MSH|ONE\r"
    m2 = b"MSH|TWO\r"
    buf = bytearray(wrap_mllp_message(m1) + wrap_mllp_message(m2))

    msgs = extract_mllp_messages(buf)

    assert msgs == [m1, m2]
    assert buf == bytearray()