from urllib.parse import quote

import requests

SEND_TIMEOUT_SECONDS = 300
LOOKUP_TIMEOUT_SECONDS = 10


def is_whatsapp_target(target: str) -> bool:
    # WhatsApp chat ids always carry a server suffix (@c.us, @g.us, @lid).
    # Signal numbers, UUIDs and group ids never contain "@".
    return "@" in target


def _parse_attachment(attachment: str) -> dict:
    # Bots emit "data:image/png;filename=chart.png;base64,<data>".
    mimetype = "image/png"
    filename = "image.png"
    data = attachment
    if attachment.startswith("data:") and "," in attachment:
        header, data = attachment[len("data:") :].split(",", 1)
        for index, part in enumerate(header.split(";")):
            if index == 0 and part:
                mimetype = part
            elif part.startswith("filename="):
                filename = part[len("filename=") :]
    return {"mimetype": mimetype, "filename": filename, "data": data}


class WhatsAppClient:
    def __init__(self, api_url: str, api_key: str, session: str = "default") -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.session = session

    def _post(self, path: str, payload: dict) -> None:
        response = requests.post(
            f"{self.api_url}{path}",
            json={"session": self.session, **payload},
            headers={"X-Api-Key": self.api_key},
            timeout=SEND_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

    def send_message(self, chat_id: str, message: str, attachments: list[str] | None = None) -> None:
        # Groups and direct chats share one endpoint; the chat id says which.
        if message or not attachments:
            self._post("/api/sendText", {"chatId": chat_id, "text": message})
        for attachment in attachments or []:
            self._post("/api/sendImage", {"chatId": chat_id, "file": _parse_attachment(attachment)})

    def phone_for_lid(self, lid: str) -> str | None:
        # WAHA answers {"lid": "...@lid", "pn": "491701234567@c.us"}, pn null if unknown.
        try:
            response = requests.get(
                f"{self.api_url}/api/{self.session}/lids/{quote(lid, safe='')}",
                headers={"X-Api-Key": self.api_key},
                timeout=LOOKUP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            pn = response.json().get("pn") or ""
        except (requests.RequestException, ValueError):
            return None
        local = pn.partition("@")[0]
        return f"+{local}" if local.isdigit() else None
