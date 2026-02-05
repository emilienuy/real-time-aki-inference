from src.hl7 import ParsedMessage
import http
from urllib.request import urlopen

def request(pager_port: int, parsed_msg: ParsedMessage) -> None:
    """ Send a pager HTTP request given a positive test result message. """

    req_data = (f"{parsed_msg.mrn},{parsed_msg.result.timestamp}").encode("ascii")
    
    req = urlopen(f"http://localhost:{pager_port}/page", data=req_data)
    
    # Raise an error if the HTTP request is unsuccessful
    if req.status != http.HTTPStatus.OK:

        raise RuntimeError(f"Pager HTTP request failed with status {req.status}.")
