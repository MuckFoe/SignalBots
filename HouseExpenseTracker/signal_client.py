import base64

import requests

SEND_TIMEOUT_SECONDS = 300


class SignalClient:
    def __init__(self, api_url: str, from_number: str) -> None:
        self.api_url = api_url.rstrip("/")
        self.from_number = from_number

    def send_message(self, to_number: str, message: str) -> None:
        url = f"{self.api_url}/v2/send"
        payload = {
            "message": message,
            "number": self.from_number,
            "recipients": [to_number],
        }
        response = requests.post(url, json=payload, timeout=SEND_TIMEOUT_SECONDS)
        response.raise_for_status()

    def send_group_message(self, group_id: str, message: str) -> None:
        url = f"{self.api_url}/v2/send"
        if group_id.startswith("group."):
            recipient = group_id
        else:
            encoded_group_id = base64.b64encode(group_id.encode("utf-8")).decode("ascii")
            recipient = f"group.{encoded_group_id}"
        payload = {
            "message": message,
            "number": self.from_number,
            "recipients": [recipient],
        }
        response = requests.post(url, json=payload, timeout=SEND_TIMEOUT_SECONDS)
        response.raise_for_status()
