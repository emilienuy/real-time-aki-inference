#!/usr/bin/env python3
import csv
from datetime import datetime
import math

import numpy as np
import pandas as pd

from collections import defaultdict
from src.hl7 import ParsedMessage


def _clean_cell(value) -> str:
    """Convert a CSV cell to a stripped string, treating None/NaN as empty."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return ""
    return s


def _parse_float(cell) -> float:
    """Parse a float from a CSV cell; return NaN if missing/unparseable."""
    s = _clean_cell(cell)
    if not s:
        return math.nan
    try:
        x = float(s)
    except (TypeError, ValueError):
        return math.nan
    return x if math.isfinite(x) else math.nan


def _sex_is_male(cell) -> float:
    """
    Encode sex as 1.0 for male, 0.0 otherwise.

    Unknown/missing -> 0.0.
    """
    s = _clean_cell(cell)
    return 1.0 if s == "M" else 0.0


def extract_creatinine_history(patient_record: dict) -> list:
    """
    Extract and order a patient's creatinine result history from a CSV row.

    Reads (creatinine_date_i, creatinine_result_i) pairs from a patient record, 
    parses valid pairs, and returns them chronologically sorted (oldest -> newest).
    Invalid or missing entries are ignored.

    Parameters
    ----------
    patient_record:
        Mapping of column names to CSV cell values.

    Returns
    -------
    list[tuple[datetime, float]]
        Chronologically ordered creatinine measurements.
        Returns an empty list if no valid measurements are present.
    """
    result_history = []
    i = 0

    while True:
        date_key = f"creatinine_date_{i}"
        result_key = f"creatinine_result_{i}"

        # Stop when date column does not exist
        if date_key not in patient_record:
            break

        date_s = _clean_cell(patient_record.get(date_key))
        result_s = _clean_cell(patient_record.get(result_key))

        if date_s and result_s:
            try:
                timestamp = datetime.fromisoformat(date_s)
            # Skip invalid timestamps
            except (TypeError, ValueError):
                i += 1
                continue

            try:
                result = float(result_s)
            # Skip invalid measurements
            except (TypeError, ValueError):
                i += 1
                continue

            # Skip NaN/inf values.
            if math.isfinite(result):
                result_history.append((timestamp, result))

        i += 1

    result_history.sort(key=lambda pair: pair[0])
    return result_history


def read_history(history_path: str) -> defaultdict:
    """ Read the provided as a nested dictionary keyed by the MRN. """

    history = defaultdict(dict)

    with open(history_path, newline="") as file:

        reader = csv.DictReader(file)

        for row in reader:

            mrn = int(row.get("mrn"))

            history[mrn]["creatinine_history"] = extract_creatinine_history(row)

    return history


def update_history(history:defaultdict, parsed_msg: ParsedMessage) -> defaultdict:
    """ Refreshes the history nested dictionary based on the received message. """

    # An ADT^A01 message could potentially contain new patient data
    if (parsed_msg.valid is True and 
        parsed_msg.msg_type == "ADT^A01"):

        mrn = int(parsed_msg.mrn)

        if "age" not in history[mrn]:

            history[mrn]["is_male"] = _sex_is_male(parsed_msg.patient.sex)
            history[mrn]["age"] = _parse_float(_compute_age(parsed_msg))

    # An ORU^R01 message could contain information about a new creatinine test
    elif (parsed_msg.valid is True and 
          parsed_msg.msg_type == "ORU^R01" and
          parsed_msg.result.test_type == "CREATININE"):

        mrn = int(parsed_msg.mrn)

        test_timestamp = datetime.strptime(parsed_msg.result.timestamp, 
                                           "%Y%m%d%H%M%S")
        test_result = float(parsed_msg.result.value)

        history[mrn].setdefault("creatinine_history", []).append(
            (test_timestamp, test_result))

    return history
        

def _compute_age(parsed_msg: ParsedMessage) -> int:
    """ Calculate the age of a patient when the message is received. """
    ref_date = datetime.strptime(parsed_msg.message_time, "%Y%m%d%H%M%S")
    birth_date = datetime.strptime(parsed_msg.patient.date_of_birth, "%Y%m%d")

    age = (ref_date.year - birth_date.year - (
           (ref_date.month, ref_date.day) < (birth_date.month, birth_date.day)))

    return age


def construct_features(patient_record: dict) -> pd.DataFrame:
    """
    Convert a single patient record into a fixed set of numeric features.

    Features summarize creatinine history: latest value, change relative to
    earlier measurements (min/median), the most recent delta, time gap, 
    and variability/count of measurements. 
    Missing or insufficient history yields NaN for the affected features.

    Parameters
    ----------
    patient_record:
        Mapping of column names to CSV cell values.

    Returns
    -------
    dict[str, float]
        Mapping of feature names to floats (may contain NaNs).
    """

    age = patient_record.get("age")
    is_male = patient_record.get("is_male")
    creatinine_history = patient_record.get("creatinine_history")

    num_results = float(len(creatinine_history))

    nan = math.nan
    creatinine_features = {"latest": nan,
                           "min_prev": nan,
                           "median_prev": nan,
                           "ratio_to_min": nan,
                           "ratio_to_median": nan,
                           "delta_to_min": nan,
                           "delta_to_median": nan,
                           "latest_delta": nan,
                           "hours_since_previous": nan,
                           "std_prev": nan,}
    
    dates = [dt for dt, _ in creatinine_history]
    results = [v for _, v in creatinine_history]
    latest = float(results[-1])
    creatinine_features["latest"] = latest

    if int(num_results) >= 2:

        prev_results = results[:-1]

        min_prev = float(min(prev_results))
        median_prev = float(np.median(prev_results))
        creatinine_features["min_prev"] = min_prev
        creatinine_features["median_prev"] = median_prev
        creatinine_features["std_prev"] = float(np.std(prev_results))

        creatinine_features["latest_delta"] = float(results[-1] - results[-2])

        dt_hours = (dates[-1] - dates[-2]).total_seconds() / 3600.0
        creatinine_features["hours_since_previous"] = (float(dt_hours) 
                                                       if dt_hours >= 0 else math.nan)

        creatinine_features["delta_to_min"] = float(latest - min_prev)
        creatinine_features["delta_to_median"] = float(latest - median_prev)

        creatinine_features["ratio_to_min"] = (float(latest / min_prev) 
                                               if min_prev != 0 else math.inf)
        creatinine_features["ratio_to_median"] = (float(latest / median_prev) 
                                                  if median_prev != 0 else math.inf)

    features = {"age": age, 
                "sex_m": is_male, 
                "num_results": num_results, 
                **creatinine_features}

    features = pd.DataFrame([features])

    return features