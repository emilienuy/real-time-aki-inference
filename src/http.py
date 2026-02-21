import http
import logging
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

from src.metrics import PAGER_ERRORS

_MAX_RETRIES = 3
_RETRY_DELAY = 2.0  # seconds between attempts


def request(pager_port, parsed_msg, host="localhost", timeout=3.0):
    """Send a pager HTTP POST, retrying up to _MAX_RETRIES times on failure.

    On a transient network error or non-200 response the request is retried
    after _RETRY_DELAY seconds. If all attempts fail we log the error and
    return without raising, so the caller's message loop is not interrupted.
    """
    req_data = (f"{parsed_msg.mrn},{parsed_msg.result.timestamp}").encode("ascii")
    url = f"http://{host}:{pager_port}/page"

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            req = Request(url, data=req_data, headers={"Content-Type": "text/plain"})
            with urlopen(req, timeout=timeout) as resp:
                if resp.status != http.HTTPStatus.OK:
                    raise RuntimeError(f"Pager returned status {resp.status}")
                print(f"Positive AKI pager request: {parsed_msg.mrn},{parsed_msg.result.timestamp}")
                return
        except (URLError, OSError, RuntimeError) as e:
            PAGER_ERRORS.inc()
            if attempt < _MAX_RETRIES:
                logging.warning(
                    "Pager request failed (attempt %d/%d): %s; retrying in %.0fs",
                    attempt, _MAX_RETRIES, e, _RETRY_DELAY,
                )
                time.sleep(_RETRY_DELAY)
            else:
                logging.error(
                    "Pager request failed after %d attempts: %s; giving up",
                    _MAX_RETRIES, e,
                )
