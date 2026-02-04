from dataclasses import dataclass
import logging
import math


@dataclass
class PatientInfo:
    """
    Basic patient demographics extracted from PAS messages (ADT^A01).

    HL7 fields:
    - PID.5: patient name
    - PID.7: date of birth
    - PID.8: sex
    """
    name: str
    date_of_birth: str
    sex: str


@dataclass
class Result:
    """
    Laboratory blood test result extracted from LIMS messages (ORU^R01).

    HL7 fields:
    - OBR.7: blood test timestamp
    - OBX.3: blood test type (e.g. 'CREATININE')
    - OBX.5: blood test value
    """
    timestamp: str
    test_type: str
    value: float


EMPTY_PATIENT = PatientInfo(name="", date_of_birth="", sex="")
EMPTY_RESULT = Result(timestamp="", test_type="", value=math.nan)


@dataclass
class ParsedMessage:
    """
    Structured representation of a parsed HL7 message.

    Fields:
    - valid: False if message is malformed or missing required fields.
    - msg_type: MSH.9, e.g. "ADT^A01", "ADT^A03", "ORU^R01"
    - message_time: MSH.7
    - mrn: PID.3

    patient:
      - For ADT^A01: populated with PID.5/PID.7/PID.8
      - Otherwise: EMPTY_PATIENT

    result:
      - For ORU^R01: populated with OBR.7/OBX.3/OBX.5
      - Otherwise: EMPTY_RESULT

    Callers should check `valid` before consuming msg_type/message_time/mrn.
    """
    valid: bool
    msg_type: str
    message_time: str
    mrn: str
    patient: PatientInfo
    result: Result


def parse_hl7_message(message: bytes) -> ParsedMessage:
    """
    Parse a single HL7v2 message into a ParsedMessage.

    Args:
        message: Raw HL7 message bytes (7-bit ASCII), without MLLP framing.
            Segments must be separated by carriage returns ('\\r').

    Returns:
        ParsedMessage:
            A structured representation of the message.

            This function never raises. On malformed or incomplete messages,
            it logs a warning and returns ParsedMessage(valid=False, ...)
            with safe default values.
    """
    raise NotImplementedError


def _split_segments(message_str: str) -> list[list[str]]:
    """
    Split an HL7 message string into segments and fields.

    Args:
        message_str: Decoded HL7 message string.

    Returns:
        A list of segments, where each segment is represented as a list of
        fields split on the '|' character. The segment name (e.g. 'MSH',
        'PID') is at index 0 of each list.
    """
    raise NotImplementedError


def _find_segment(segments: list[list[str]], segment_name: str) -> list[str]:
    """
    Find the first segment with the given name.

    Args:
        segments: Parsed segments from an HL7 message.
        segment_name: Segment name to search for (e.g. 'PID', 'OBR').

    Returns:
        The fields for the first matching segment. If the segment is not found,
        returns an empty list. This function never raises.
    """
    raise NotImplementedError


def _get_field(fields: list[str], index: int) -> str:
    """
    Safely get a field from a segment using HL7 1-based indexing.

    Args:
        fields: Segment fields split on '|', where fields[0] is the segment name.
        index: HL7 field index (1-based).

    Returns:
        The requested field value, or an empty string if the field is not present.
    """
    raise NotImplementedError