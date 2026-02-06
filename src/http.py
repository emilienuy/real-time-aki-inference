import http
from urllib.request import Request, urlopen

def request(pager_port, parsed_msg, host="localhost", timeout=3.0):
    """Send a pager HTTP request given a positive test result message."""
    req_data = (f"{parsed_msg.mrn},{parsed_msg.result.timestamp}").encode("ascii")
    url = f"http://{host}:{pager_port}/page"

    # Keep a short timeout so paging doesn't block the stream.
    req = Request(url, data=req_data, headers={"Content-Type": "text/plain"})
    with urlopen(req, timeout=timeout) as resp:
        if resp.status != http.HTTPStatus.OK:
            raise RuntimeError(f"Pager HTTP request failed with status {resp.status}.")
