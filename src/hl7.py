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
        ParsedMessage: A structured representation of the message.

        This function never raises. On malformed or incomplete messages,
        it logs a warning and returns ParsedMessage(valid=False, ...)
        with safe default values.
    """
    def _invalid(reason: str) -> ParsedMessage:
        logging.warning("HL7 parse: %s", reason)
        return ParsedMessage(
            valid=False,
            msg_type="",
            message_time="",
            mrn="",
            patient=EMPTY_PATIENT,
            result=EMPTY_RESULT,
        )

    try:
        message_str = message.decode("ascii", errors="replace")
    except Exception as e:
        return _invalid(f"failed to decode message: {e}")

    segments = _split_segments(message_str)

    msh = _find_segment(segments, "MSH")
    if not msh:
        return _invalid("missing MSH segment")

    (message_time, msg_type), reason = _parse_header(msh)
    if reason:
        return _invalid(reason)

    pid = _find_segment(segments, "PID")
    if not pid:
        return _invalid("missing PID segment")

    mrn, reason = _parse_mrn(pid)
    if reason:
        return _invalid(reason)

    # Defaults
    patient = EMPTY_PATIENT
    result = EMPTY_RESULT

    if msg_type == "ADT^A01":
        patient_info, reason = _parse_patient_info_for_a01(pid)
        if reason:
            return _invalid(reason)
        patient = patient_info

    elif msg_type == "ADT^A03":
        pass  # only MRN required

    elif msg_type == "ORU^R01":
        parsed_result, reason = _parse_result_for_r01(segments)
        if reason:
            return _invalid(reason)
        result = parsed_result

    else:
        return _invalid(f"unsupported message type: {msg_type}")

    return ParsedMessage(
        valid=True,
        msg_type=msg_type,
        message_time=message_time,
        mrn=mrn,
        patient=patient,
        result=result,
    )


def _parse_header(msh: list[str]) -> tuple[tuple[str, str], str]:
    """
    Extract required header fields from an MSH segment.

    Args:
        msh: MSH segment fields split on '|'.

    Returns:
        A tuple ((message_time, msg_type), reason).

        On success, reason is an empty string and message_time/msg_type are
        populated. On failure, reason contains a human-readable error message
        and the returned values are empty strings.
    """
    message_time = _get_msh_field(msh, 7)  # MSH.7
    msg_type = _get_msh_field(msh, 9)      # MSH.9
    if not message_time:
        return ("", ""), "missing MSH.7 (message_time)"
    if not msg_type:
        return ("", ""), "missing MSH.9 (msg_type)"
    return (message_time, msg_type), ""


def _parse_mrn(pid: list[str]) -> tuple[str, str]:
    """
    Extract the patient MRN (PID.3) from a PID segment.

    Args:
        pid: PID segment fields split on '|'.

    Returns:
        A tuple (mrn, reason).

        On success, reason is an empty string and mrn is populated.
        On failure, reason contains a human-readable error message and
        mrn is an empty string.
    """
    mrn = _get_field(pid, 3)  # PID.3
    if not mrn:
        return "", "missing PID.3 (mrn)"
    return mrn, ""


def _parse_patient_info_for_a01(pid: list[str]) -> tuple[PatientInfo, str]:
    """
    Extract required patient demographics for an ADT^A01 message from PID.

    Args:
        pid: PID segment fields split on '|'.

    Returns:
        A tuple (patient_info, reason).

        On success, reason is an empty string and patient_info contains the
        extracted demographics (name, date of birth, sex). On failure, reason
        contains a human-readable error message and patient_info is
        EMPTY_PATIENT.
    """
    name = _get_field(pid, 5)            # PID.5
    date_of_birth = _get_field(pid, 7)   # PID.7
    sex = _get_field(pid, 8)             # PID.8

    if not name:
        return EMPTY_PATIENT, "ADT^A01 missing PID.5 (name)"
    if not date_of_birth:
        return EMPTY_PATIENT, "ADT^A01 missing PID.7 (date_of_birth)"
    if not sex:
        return EMPTY_PATIENT, "ADT^A01 missing PID.8 (sex)"

    return PatientInfo(name=name, date_of_birth=date_of_birth, sex=sex), ""


def _parse_result_for_r01(segments: list[list[str]]) -> tuple[Result, str]:
    """
    Extract required laboratory result fields for an ORU^R01 message.

    Args:
        segments: HL7 message segments split into fields.

    Returns:
        A tuple (result, reason).

        On success, reason is an empty string and result contains the extracted
        laboratory test information (timestamp, test type, value). On failure,
        reason contains a human-readable error message and result is
        EMPTY_RESULT.
    """
    obr = _find_segment(segments, "OBR")
    if not obr:
        return EMPTY_RESULT, "ORU^R01 missing OBR segment"

    obx = _find_segment(segments, "OBX")
    if not obx:
        return EMPTY_RESULT, "ORU^R01 missing OBX segment"

    test_timestamp = _get_field(obr, 7)  # OBR.7
    test_type = _get_field(obx, 3)       # OBX.3
    value_str = _get_field(obx, 5)       # OBX.5

    if not test_timestamp:
        return EMPTY_RESULT, "ORU^R01 missing OBR.7 (test_timestamp)"
    if not test_type:
        return EMPTY_RESULT, "ORU^R01 missing OBX.3 (test_type)"
    if not value_str:
        return EMPTY_RESULT, "ORU^R01 missing OBX.5 (value)"

    try:
        value = float(value_str)
    except ValueError:
        return EMPTY_RESULT, f"ORU^R01 invalid OBX.5 (not a float): {value_str!r}"

    return Result(timestamp=test_timestamp, test_type=test_type, value=value), ""


def _split_segments(message_str: str) -> list[list[str]]:
    """
    Split an HL7 message string into segments and fields.

    Args:
        message_str: Decoded HL7 message string.

    Returns:
        A list of segments, where each segment is represented as a list of
        fields split on the '|' character. The segment name (e.g. 'MSH',
        'PID') is at index 0 of each list.
    
    Example:
        >>> _split_segments("PID|1||123\\r")
        [["PID", "1", "", "123"]]
    """
    segments = []
    for line in message_str.split("\r"):
        if not line:
            continue
        segments.append(line.split("|"))
    return segments


def _find_segment(segments: list[list[str]], segment_name: str) -> list[str]:
    """
    Return the first HL7 segment with the given name.

    Args:
        segments: HL7 message segments split into fields, where each segment is
            represented as a list of strings and index 0 is the segment name.
        segment_name: Segment name to search for (e.g. 'MSH', 'PID', 'OBR').

    Returns:
        The fields for the first matching segment, or an empty list if the
        segment is not present.
    
    Example:
        >>> segments = [["MSH", "..."], ["PID", "1", "", "123"]]
        >>> _find_segment(segments, "PID")
        ["PID", "1", "", "123"]
    """
    for segment in segments:
        if segment and segment[0] == segment_name:
            return segment
    return []


def _get_field(fields: list[str], index: int) -> str:
    """
    Return the value of an HL7 field using 1-based indexing.

    Args:
        fields: Segment fields split on '|', with fields[0] being the segment name.
        index: HL7 field index (1-based).

    Returns:
        The field value if present, otherwise an empty string.
    
    Example:
        >>> _get_field(["PID", "1", "", "478237423"], 3)
        '478237423'
    """
    if 0 <= index < len(fields):
        return fields[index]
    return ""


def _get_msh_field(msh_fields: list[str], index: int) -> str:
    """
    Return the value of an HL7 field from the MSH segment using 1-based indexing.

    Note:
        MSH is special: MSH-1 is the field separator character and is not present
        in msh_fields after splitting on '|'. Therefore, HL7 field N maps to
        msh_fields[N - 1].

    Args:
        msh_fields: MSH segment fields split on '|', where msh_fields[0] == 'MSH'.
        index: HL7 field index (1-based).

    Returns:
        The field value if present, otherwise an empty string.
    """
    pos = index - 1
    if 0 <= pos < len(msh_fields):
        return msh_fields[pos]
    return ""