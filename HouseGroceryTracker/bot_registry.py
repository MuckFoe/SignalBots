from __future__ import annotations



import os





def load_bot_registry() -> dict[str, str]:

    raw = os.getenv("BOT_REGISTRY", "").strip()

    if raw:

        bots: dict[str, str] = {}

        for part in raw.split(","):

            part = part.strip()

            if not part or ":" not in part:

                continue

            bot_id, name = part.split(":", 1)

            bot_id = bot_id.strip()

            name = name.strip()

            if bot_id and name:

                bots[bot_id] = name

        if bots:

            return bots



    bot_id = os.getenv("BOT_INSTANCE_ID", "grocery").strip() or "grocery"

    bot_name = os.getenv("BOT_INSTANCE_NAME", "Grocery List Bot").strip() or "Grocery List Bot"

    return {bot_id: bot_name}





def runtime_bot_id() -> str:

    return os.getenv("BOT_INSTANCE_ID", "grocery").strip() or "grocery"

