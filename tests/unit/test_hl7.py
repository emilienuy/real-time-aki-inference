import math
from pathlib import Path

import pytest

from src.hl7 import (
    parse_hl7_message,
    EMPTY_RESULT,
    EMPTY_PATIENT,
)


def _hl7_str_to_bytes(text: str) -> bytes:
    """
    Helper: turn a human-readable HL7 message into bytes.
    """
    if not text.endswith("\r"):
        text += "\r"
    return text.encode("ascii", errors="strict")


def test_parse_adt_a01_extracts_required_fields():
    # ADT^A01 includes PID.3, PID.5, PID.7, PID.8
    message = _hl7_str_to_bytes(
        "MSH|^~\\&|SIMULATION|SOUTH RIVERSIDE|||202401201630||ADT^A01|||2.5\r"
        "PID|1||478237423||ELIZABETH HOLMES||19840203|F\r"
        "NK1|1|SUNNY BALWANI|PARTNER\r"
    )

    result = parse_hl7_message(message)

    assert result.valid is True
    assert result.msg_type == "ADT^A01"
    assert result.message_time == "202401201630"
    assert result.mrn == "478237423"

    # Demographics populated for ADT^A01
    assert result.patient.name == "ELIZABETH HOLMES"
    assert result.patient.date_of_birth == "19840203"
    assert result.patient.sex == "F"

    # LIMS result not applicable
    assert result.result == EMPTY_RESULT
    assert math.isnan(result.result.value)


def test_parse_adt_a03_extracts_mrn_and_no_demographics_required():
    message = _hl7_str_to_bytes(
        "MSH|^~\\&|SIMULATION|SOUTH RIVERSIDE|||202401201630||ADT^A03|||2.5\r"
        "PID|1||478237423\r"
    )

    result = parse_hl7_message(message)

    assert result.valid is True
    assert result.msg_type == "ADT^A03"
    assert result.message_time == "202401201630"
    assert result.mrn == "478237423"

    # ADT^A03 does not require demographics => empty sentinel is fine
    assert result.patient == EMPTY_PATIENT

    # No lab result
    assert result.result == EMPTY_RESULT
    assert math.isnan(result.result.value)


def test_parse_oru_r01_extracts_creatinine_result():
    # ORU^R01 includes PID.3, OBR.7, OBX.3, OBX.5
    message = _hl7_str_to_bytes(
        "MSH|^~\\&|SIMULATION|SOUTH RIVERSIDE|||202401201630||ORU^R01|||2.5\r"
        "PID|1||478237423\r"
        "OBR|1||||||202401202243\r"
        "OBX|1|SN|CREATININE||103.4\r"
    )

    result = parse_hl7_message(message)

    assert result.valid is True
    assert result.msg_type == "ORU^R01"
    assert result.message_time == "202401201630"
    assert result.mrn == "478237423"

    # PAS demographics not required for LIMS messages
    assert result.patient == EMPTY_PATIENT

    # Result populated
    assert result.result.timestamp == "202401202243"
    assert result.result.test_type == "CREATININE"
    assert result.result.value == pytest.approx(103.4)


def test_parse_missing_msh_is_invalid_and_never_raises():
    message = _hl7_str_to_bytes("PID|1||478237423||ELIZABETH HOLMES||19840203|F\r")

    result = parse_hl7_message(message)

    assert result.valid is False
    assert result.patient == EMPTY_PATIENT
    assert result.result == EMPTY_RESULT


def test_parse_oru_bad_obx_value_is_invalid_and_never_raises():
    message = _hl7_str_to_bytes(
        "MSH|^~\\&|SIMULATION|SOUTH RIVERSIDE|||202401201630||ORU^R01|||2.5\r"
        "PID|1||478237423\r"
        "OBR|1||||||202401202243\r"
        "OBX|1|SN|CREATININE||NOT_A_NUMBER\r"
    )

    result = parse_hl7_message(message)

    assert result.valid is False
    assert result.patient == EMPTY_PATIENT
    assert result.result == EMPTY_RESULT


def test_parse_unsupported_message_type_is_invalid_and_safe():
    message = _hl7_str_to_bytes(
        "MSH|^~\\&|SIMULATION|SOUTH RIVERSIDE|||202401201630||ZZZ^ZZZ|||2.5\r"
        "PID|1||478237423\r"
    )

    result = parse_hl7_message(message)

    assert result.valid is False
    assert result.patient == EMPTY_PATIENT
    assert result.result == EMPTY_RESULT


def test_parse_real_message_from_messages_mllp_fixture_if_present():
    """
    Sanity test using fixtures/messages.mllp.
    """
    fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures"
    mllp_path = fixtures_dir / "messages.mllp"
    if not mllp_path.exists():
        pytest.skip("messages.mllp fixture not present")

    data = mllp_path.read_bytes()
    start = data.find(b"\x0b")
    end = data.find(b"\x1c\x0d", start + 1)
    if start == -1 or end == -1:
        pytest.skip("No complete MLLP frame found in messages.mllp")

    message = data[start + 1 : end]  # HL7 message bytes (no framing)
    parsed = parse_hl7_message(message)

    assert isinstance(parsed.valid, bool)
    
    if parsed.valid:
        assert parsed.msg_type != ""
        assert parsed.message_time != ""
        assert parsed.mrn != ""
    
    if not parsed.valid:
        assert parsed.patient == EMPTY_PATIENT
        assert parsed.result == EMPTY_RESULT
