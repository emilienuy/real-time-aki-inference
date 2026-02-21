from prometheus_client import Counter, Histogram

# Total HL7 messages received from the MLLP stream (all types).
MESSAGES_RECEIVED = Counter(
    "messages_received_total",
    "Total HL7 messages received from the MLLP stream",
)

# Creatinine ORU^R01 results processed (deduplicated).
BLOOD_TESTS_RECEIVED = Counter(
    "blood_tests_received_total",
    "Total creatinine blood test results processed",
)

# Positive AKI predictions that triggered a pager alert.
AKI_PAGES_SENT = Counter(
    "aki_pages_sent_total",
    "Total positive AKI predictions that triggered a pager alert",
)

# Failed pager HTTP requests counted per attempt (before retry succeeds or gives up).
PAGER_ERRORS = Counter(
    "pager_errors_total",
    "Total failed pager HTTP request attempts",
)

# Every successful MLLP connection (including the first one and reconnections).
MLLP_CONNECTIONS = Counter(
    "mllp_connections_total",
    "Total MLLP connections established (including reconnections after failures)",
)

# Distribution of creatinine values seen in the stream.
CREATININE_VALUE = Histogram(
    "creatinine_value_umol_l",
    "Distribution of observed creatinine readings in umol/L",
    buckets=[50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 750, 1000],
)
