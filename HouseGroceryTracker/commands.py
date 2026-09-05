from __future__ import annotations

import os
from typing import Any

from categories import guess_category
from dialogue_utils import STALE_STEP, mobile_blocks, parse_stale_response, stale_prompt_text
from image_recognition import fetch_incoming_image, save_item_image
from item_parse import parse_add_text, strip_command_prefix
from storage import Storage


SIGNAL_API_URL = os.getenv("SIGNAL_API_URL", "http://localhost:8080").strip()


def text_for(storage: Storage, scope_id: str, key: str, **kwargs) -> str:
    language = storage.get_language(scope_id)
    template = TEXT.get(language, TEXT["en"]).get(key) or TEXT["en"].get(key, key)
    return template.format(**kwargs) if kwargs else template


TEXT = {
    "en": {
        "help": (
            "🛒 Grocery List Bot:\n\n"
            "➕ add — guided add (step by step)\n"
            "➕ + milk / add 2x eggs @ dairy # rewe — quick add\n"
            "✅ done — pick what you bought (dialogue)\n"
            "✅ done milk — quick check-off\n"
            "📋 list · 🧹 clear checked\n"
            "🏷️ categories · 🏪 shops\n"
            "📝 lists · ⭐ frequent · 🔍 search milk\n"
            "📷 Photo + optional caption → guided add\n"
            "↩️ cancel — stop current dialogue\n"
            "🔧 Admin: admin help"
        ),
        "setup_choose_language": (
            "👋 Welcome / Willkommen. Choose language:\n"
            "- language en\n"
            "- sprache deutsch"
        ),
        "setup_complete": (
            "🎉 Grocery list ready.\n"
            "Try: add (guided) or + milk (quick).\n"
            "Mark bought with: done"
        ),
        "dlg_add_name": "What should I add?\nReply with the item name, or cancel.",
        "dlg_add_quantity": "How many? (e.g. 2)\nReply: skip for one item.",
        "dlg_add_category": "Category?\n{options}\nReply with number, name, or skip.",
        "dlg_add_shop": "Which shop?\n{options}\nReply with number, name, or skip.",
        "dlg_add_confirm": (
            "Add this item?\n"
            "• {name}{qty}\n"
            "• {category}\n"
            "• {shop}\n"
            "Reply: yes, no, or cancel."
        ),
        "dlg_check_pick": "What did you buy?\n{options}\nReply with number or name, or cancel.",
        "dlg_invalid_pick": "Pick a number or name from the list, or cancel.",
        "list_header": "📋 {list_name}{shop_suffix}",
        "list_empty": "List is empty. Try: add",
        "list_section": "🏷️ {category}",
        "list_line": "{mark} {qty}{name}{shop}",
        "list_checked_header": "✅ Checked:",
        "added": "➕ Added: {name}{extra}",
        "already_on_list": "Already on list: {name}",
        "checked": "✅ Got it: {name}",
        "unchecked": "↩️ Back on list: {name}",
        "removed": "🗑️ Removed: {name}",
        "not_found": "⚠️ Not found: {name}",
        "cleared": "🧹 Removed {count} checked item(s).",
        "categories_header": "🏷️ Categories:",
        "categories_line": "• {name}",
        "shops_header": "🏪 Shops:",
        "shops_line": "• {name}",
        "category_added": "🏷️ Category added: {name}",
        "category_removed": "🏷️ Category removed: {name}",
        "shop_added": "🏪 Shop added: {name}",
        "shop_removed": "🏪 Shop removed: {name}",
        "lists_header": "📝 Lists:",
        "list_created": "📝 List created: {name}",
        "list_exists": "List already exists: {name}",
        "list_active": "📝 Active list: {name}",
        "list_unknown": "Unknown list: {name}",
        "frequent_header": "⭐ Often bought:",
        "frequent_line": "• {name} ({count}×)",
        "search_header": "🔍 Matches:",
        "search_empty": "No matches for: {query}",
        "search_line": "{mark} {name}{meta}",
        "photo_saved": "📷 Photo saved. What item is this?",
        "photo_no_image": "No image found. Try: add",
        "cancelled": "↩️ Cancelled.",
        "confirm_expected": "Reply: yes, no, or cancel.",
        "language_set_en": "Language set to English.",
        "language_set_de": "Language set to German.",
        "admin_help": "🔧 Admin:\n- admin reset\n- admin category add <name>\n- admin shop add <name>",
        "admin_only": "Admin only. Use: admin <action>",
        "reset_done": "✅ List data reset.",
        "unexpected_error": "⚠️ Something went wrong.",
        "usage_add": "Usage: add (guided) or + milk",
        "skip": "skip",
        "none": "none",
        "any_shop": "any shop",
        "any_category": "auto",
    },
    "de": {
        "help": (
            "🛒 Einkaufslisten-Bot:\n\n"
            "➕ hinzufügen / add — Schritt für Schritt\n"
            "➕ + milch / add 2x eier @ milchprodukte # rewe — Schnell\n"
            "✅ erledigt / done — Dialog: was gekauft?\n"
            "✅ erledigt milch — Schnell abhaken\n"
            "📋 liste · 🧹 erledigt löschen\n"
            "🏷️ kategorien · 🏪 geschäfte\n"
            "📝 listen · ⭐ häufig · 🔍 suche milch\n"
            "📷 Foto + optional Text → Dialog\n"
            "↩️ abbrechen — Dialog beenden\n"
            "🔧 Admin: admin hilfe"
        ),
        "setup_choose_language": (
            "👋 Welcome / Willkommen. Sprache wählen:\n"
            "- language en\n"
            "- sprache deutsch"
        ),
        "setup_complete": (
            "🎉 Einkaufsliste bereit.\n"
            "Probiere: hinzufügen (Dialog) oder + milch (Schnell).\n"
            "Abhaken mit: erledigt"
        ),
        "dlg_add_name": "Was soll ich hinzufügen?\nAntworte mit dem Namen, oder abbrechen.",
        "dlg_add_quantity": "Wie viele? (z.B. 2)\nAntworte: überspringen für ein Stück.",
        "dlg_add_category": "Kategorie?\n{options}\nNummer, Name, oder überspringen.",
        "dlg_add_shop": "Welcher Laden?\n{options}\nNummer, Name, oder überspringen.",
        "dlg_add_confirm": (
            "Artikel hinzufügen?\n"
            "• {name}{qty}\n"
            "• {category}\n"
            "• {shop}\n"
            "Antworte: ja, nein, oder abbrechen."
        ),
        "dlg_check_pick": "Was hast du gekauft?\n{options}\nNummer oder Name, oder abbrechen.",
        "dlg_invalid_pick": "Wähle Nummer oder Name aus der Liste, oder abbrechen.",
        "list_header": "📋 {list_name}{shop_suffix}",
        "list_empty": "Liste leer. Probiere: hinzufügen",
        "list_section": "🏷️ {category}",
        "list_line": "{mark} {qty}{name}{shop}",
        "list_checked_header": "✅ Erledigt:",
        "added": "➕ Hinzugefügt: {name}{extra}",
        "already_on_list": "Schon auf der Liste: {name}",
        "checked": "✅ Erledigt: {name}",
        "unchecked": "↩️ Wieder auf Liste: {name}",
        "removed": "🗑️ Entfernt: {name}",
        "not_found": "⚠️ Nicht gefunden: {name}",
        "cleared": "🧹 {count} erledigte Artikel entfernt.",
        "categories_header": "🏷️ Kategorien:",
        "categories_line": "• {name}",
        "shops_header": "🏪 Geschäfte:",
        "shops_line": "• {name}",
        "category_added": "🏷️ Kategorie hinzugefügt: {name}",
        "category_removed": "🏷️ Kategorie entfernt: {name}",
        "shop_added": "🏪 Geschäft hinzugefügt: {name}",
        "shop_removed": "🏪 Geschäft entfernt: {name}",
        "lists_header": "📝 Listen:",
        "list_created": "📝 Liste erstellt: {name}",
        "list_exists": "Liste existiert schon: {name}",
        "list_active": "📝 Aktive Liste: {name}",
        "list_unknown": "Unbekannte Liste: {name}",
        "frequent_header": "⭐ Oft gekauft:",
        "frequent_line": "• {name} ({count}×)",
        "search_header": "🔍 Treffer:",
        "search_empty": "Keine Treffer für: {query}",
        "search_line": "{mark} {name}{meta}",
        "photo_saved": "📷 Foto gespeichert. Welcher Artikel ist das?",
        "photo_no_image": "Kein Bild gefunden. Probiere: hinzufügen",
        "cancelled": "↩️ Abgebrochen.",
        "confirm_expected": "Antworte: ja, nein, oder abbrechen.",
        "language_set_en": "Language set to English.",
        "language_set_de": "Sprache auf Deutsch gesetzt.",
        "admin_help": "🔧 Admin:\n- admin reset\n- admin kategorie add <name>\n- admin laden add <name>",
        "admin_only": "Nur Admin. Nutze: admin <aktion>",
        "reset_done": "✅ Listendaten zurückgesetzt.",
        "unexpected_error": "⚠️ Etwas ist schiefgelaufen.",
        "usage_add": "So geht's: hinzufügen (Dialog) oder + milch",
        "skip": "überspringen",
        "none": "keins",
        "any_shop": "egal",
        "any_category": "auto",
    },
}


def _language_from_command(text: str) -> str | None:
    cleaned = text.strip().lower()
    if cleaned in {"language en", "english", "en", "lang en"}:
        return "en"
    if cleaned in {"sprache deutsch", "language de", "german", "deutsch", "de", "lang de"}:
        return "de"
    return None


def _is_cancel(text: str) -> bool:
    return text.strip().lower() in {"cancel", "abbrechen", "stop", "exit"}


def _is_skip(text: str, language: str) -> bool:
    cleaned = text.strip().lower()
    skip_words = {"skip", "none", "-", "0"}
    if language == "de":
        skip_words |= {"überspringen", "ueberspringen", "keins", "leer"}
    return cleaned in skip_words


def _confirmation_answer(text: str) -> bool | None:
    cleaned = text.strip().lower()
    if cleaned in {"yes", "y", "ja", "j", "ok", "add", "do it"}:
        return True
    if cleaned in {"no", "n", "nein", "cancel", "abbrechen"}:
        return False
    return None


def _numbered_options(rows: list, language: str) -> str:
    skip_label = "0. skip" if language == "en" else "0. überspringen"
    lines = [skip_label]
    lines.extend(f"{idx}. {row['name']}" for idx, row in enumerate(rows, start=1))
    return "\n".join(lines)


def _pick_from_list(text: str, rows: list, language: str):
    cleaned = text.strip()
    if _is_skip(cleaned, language):
        return None
    if cleaned.isdigit():
        idx = int(cleaned)
        if idx == 0:
            return None
        if 1 <= idx <= len(rows):
            return rows[idx - 1]
        return "invalid"
    lowered = cleaned.lower()
    for row in rows:
        if row["name"].lower() == lowered:
            return row
    for row in rows:
        if lowered in row["name"].lower():
            return row
    return "invalid"


def _format_list(
    storage: Storage,
    scope_id: str,
    list_id: int,
    shop_filter: str | None = None,
) -> str:
    language = storage.get_language(scope_id)
    list_name = storage.get_list_name(list_id)
    shop_id = None
    shop_suffix = ""
    if shop_filter:
        shop_row = storage.find_shop(scope_id, shop_filter)
        if shop_row:
            shop_id = shop_row["id"]
            shop_suffix = f" @ {shop_row['name']}"

    open_rows = storage.list_items(scope_id, list_id, shop_id=shop_id, include_checked=False)
    checked_rows = [r for r in storage.list_items(scope_id, list_id, shop_id=shop_id, include_checked=True) if r["checked"]]

    if not open_rows and not checked_rows:
        return text_for(storage, scope_id, "list_empty")

    blocks = [text_for(storage, scope_id, "list_header", list_name=list_name, shop_suffix=shop_suffix)]
    uncategorized = "Other" if language == "en" else "Sonstiges"
    current_cat = None
    for row in open_rows:
        cat = row["category_name"] or uncategorized
        if cat != current_cat:
            current_cat = cat
            blocks.append(text_for(storage, scope_id, "list_section", category=cat))
        qty = f"{row['quantity']}× " if row["quantity"] else ""
        shop = f" (#{row['shop_name']})" if row["shop_name"] and not shop_filter else ""
        blocks.append(text_for(storage, scope_id, "list_line", mark="•", qty=qty, name=row["name"], shop=shop))

    if checked_rows:
        blocks.append(text_for(storage, scope_id, "list_checked_header"))
        for row in checked_rows[:8]:
            blocks.append(text_for(storage, scope_id, "list_line", mark="✓", qty="", name=row["name"], shop=""))
    return mobile_blocks(*blocks)


def _commit_pending_add(storage: Storage, scope_id: str, sender: str, pending) -> str:
    language = storage.get_language(scope_id)
    list_id = int(pending["list_id"])
    name = pending["name"]
    category_id = pending["category_id"]
    shop_id = pending["shop_id"]
    image_path = pending["image_path"] or None

    if category_id is None:
        cat_names = [r["name"] for r in storage.list_categories(scope_id)]
        guessed = guess_category(name, cat_names, language)
        if guessed:
            row = storage.find_category(scope_id, guessed)
            category_id = row["id"] if row else None

    ok, normalized = storage.add_item(
        scope_id,
        list_id,
        name,
        quantity=pending["quantity"] or "",
        category_id=category_id,
        shop_id=shop_id,
        added_by=sender,
        image_path=image_path,
        language=language,
    )
    storage.clear_pending_add(scope_id, sender)

    if ok and image_path and normalized:
        item = storage.find_open_item(scope_id, list_id, normalized)
        if item:
            import shutil
            from pathlib import Path

            src = Path(image_path)
            if src.exists() and item["id"]:
                ext = src.suffix or ".jpg"
                dest = src.parent / f"{src.stem.rsplit('_', 1)[0]}_{item['id']}{ext}"
                if src != dest:
                    shutil.move(str(src), str(dest))
                    with storage._connect() as conn:
                        conn.execute("UPDATE list_items SET image_path = ? WHERE id = ?", (str(dest), item["id"]))
                        conn.commit()

    if not ok:
        return text_for(storage, scope_id, "already_on_list", name=normalized or name)
    return text_for(storage, scope_id, "added", name=normalized, extra="")


def _add_confirm_text(storage: Storage, scope_id: str, pending) -> str:
    language = storage.get_language(scope_id)
    qty = f" ×{pending['quantity']}" if pending["quantity"] else ""
    category = text_for(storage, scope_id, "any_category")
    shop = text_for(storage, scope_id, "any_shop")
    if pending["category_id"]:
        for row in storage.list_categories(scope_id):
            if row["id"] == pending["category_id"]:
                category = row["name"]
                break
    if pending["shop_id"]:
        for row in storage.list_shops(scope_id):
            if row["id"] == pending["shop_id"]:
                shop = row["name"]
                break
    return text_for(
        storage,
        scope_id,
        "dlg_add_confirm",
        name=pending["name"],
        qty=qty,
        category=category,
        shop=shop,
    )


def _start_add_dialogue(
    storage: Storage,
    scope_id: str,
    sender: str,
    list_id: int,
    *,
    name: str = "",
    image_path: str = "",
) -> str:
    if name:
        storage.start_pending_add(scope_id, sender, list_id, step="quantity", name=name, image_path=image_path)
        return text_for(storage, scope_id, "dlg_add_quantity")
    storage.start_pending_add(scope_id, sender, list_id, step="name", image_path=image_path)
    prompt = text_for(storage, scope_id, "dlg_add_name")
    if image_path:
        prompt = text_for(storage, scope_id, "photo_saved") + "\n\n" + prompt
    return prompt


def _handle_pending_add(storage: Storage, text: str, sender: str, scope_id: str) -> str | None:
    pending = storage.get_pending_add(scope_id, sender)
    if pending is None:
        return None
    language = storage.get_language(scope_id)

    if pending["step"] == STALE_STEP:
        action = parse_stale_response(text)
        if action == "discard":
            storage.clear_pending_add(scope_id, sender)
            return text_for(storage, scope_id, "cancelled")
        if action == "continue":
            storage.restore_dialogue_step("pending_adds", scope_id, sender)
            pending = storage.get_pending_add(scope_id, sender)
            if pending and pending["step"] == "quantity":
                return text_for(storage, scope_id, "dlg_add_quantity")
            if pending and pending["step"] == "category":
                cats = storage.list_categories(scope_id)
                return text_for(storage, scope_id, "dlg_add_category", options=_numbered_options(cats, language))
            if pending and pending["step"] == "shop":
                shops = storage.list_shops(scope_id)
                return text_for(storage, scope_id, "dlg_add_shop", options=_numbered_options(shops, language))
            if pending and pending["step"] == "confirm":
                return _add_confirm_text(storage, scope_id, pending)
            return text_for(storage, scope_id, "dlg_add_name")
        return stale_prompt_text(language, "add" if language == "en" else "Hinzufügen")

    if _is_cancel(text):
        storage.clear_pending_add(scope_id, sender)
        return text_for(storage, scope_id, "cancelled")

    step = pending["step"]
    if step == "name":
        name = text.strip()
        if not name:
            return text_for(storage, scope_id, "dlg_add_name")
        storage.update_pending_add(scope_id, sender, "quantity", name=name)
        return text_for(storage, scope_id, "dlg_add_quantity")

    if step == "quantity":
        if _is_skip(text, language):
            storage.update_pending_add(scope_id, sender, "category", quantity="")
        else:
            qty = text.strip().rstrip("x×").strip()
            if not qty.isdigit():
                return text_for(storage, scope_id, "dlg_add_quantity")
            storage.update_pending_add(scope_id, sender, "category", quantity=qty)
        cats = storage.list_categories(scope_id)
        return text_for(storage, scope_id, "dlg_add_category", options=_numbered_options(cats, language))

    if step == "category":
        cats = storage.list_categories(scope_id)
        picked = _pick_from_list(text, cats, language)
        if picked == "invalid":
            return text_for(storage, scope_id, "dlg_invalid_pick")
        cat_id = picked["id"] if picked is not None else None
        storage.update_pending_add(scope_id, sender, "shop", category_id=cat_id)
        shops = storage.list_shops(scope_id)
        if not shops:
            storage.update_pending_add(scope_id, sender, "confirm", shop_id=None)
            pending = storage.get_pending_add(scope_id, sender)
            return _add_confirm_text(storage, scope_id, pending)
        return text_for(storage, scope_id, "dlg_add_shop", options=_numbered_options(shops, language))

    if step == "shop":
        shops = storage.list_shops(scope_id)
        picked = _pick_from_list(text, shops, language)
        if picked == "invalid":
            return text_for(storage, scope_id, "dlg_invalid_pick")
        shop_id = picked["id"] if picked is not None else None
        storage.update_pending_add(scope_id, sender, "confirm", shop_id=shop_id)
        pending = storage.get_pending_add(scope_id, sender)
        return _add_confirm_text(storage, scope_id, pending)

    if step == "confirm":
        answer = _confirmation_answer(text)
        if answer is None:
            return text_for(storage, scope_id, "confirm_expected")
        if not answer:
            storage.clear_pending_add(scope_id, sender)
            return text_for(storage, scope_id, "cancelled")
        pending = storage.get_pending_add(scope_id, sender)
        return _commit_pending_add(storage, scope_id, sender, pending)

    return None


def _open_items_pick_list(storage: Storage, scope_id: str, list_id: int) -> str:
    language = storage.get_language(scope_id)
    rows = storage.list_items(scope_id, list_id, include_checked=False)
    if not rows:
        return text_for(storage, scope_id, "list_empty")
    options = "\n".join(f"{idx}. {row['name']}" for idx, row in enumerate(rows[:15], start=1))
    return text_for(storage, scope_id, "dlg_check_pick", options=options)


def _handle_pending_check(storage: Storage, text: str, sender: str, scope_id: str) -> str | None:
    pending = storage.get_pending_check(scope_id, sender)
    if pending is None:
        return None
    language = storage.get_language(scope_id)
    list_id = int(pending["list_id"])

    if pending["step"] == STALE_STEP:
        action = parse_stale_response(text)
        if action == "discard":
            storage.clear_pending_check(scope_id, sender)
            return text_for(storage, scope_id, "cancelled")
        if action == "continue":
            storage.restore_dialogue_step("pending_checks", scope_id, sender)
            return _open_items_pick_list(storage, scope_id, list_id)
        return stale_prompt_text(language, "check" if language == "en" else "Abhaken")

    if _is_cancel(text):
        storage.clear_pending_check(scope_id, sender)
        return text_for(storage, scope_id, "cancelled")

    rows = storage.list_items(scope_id, list_id, include_checked=False)[:15]
    if not rows:
        storage.clear_pending_check(scope_id, sender)
        return text_for(storage, scope_id, "list_empty")

    picked = _pick_from_list(text, rows, language)
    if picked == "invalid":
        return text_for(storage, scope_id, "dlg_invalid_pick")
    if picked is None:
        return text_for(storage, scope_id, "dlg_invalid_pick")

    name = picked["name"]
    storage.clear_pending_check(scope_id, sender)
    ok = storage.check_item(scope_id, list_id, name)
    return text_for(storage, scope_id, "checked" if ok else "not_found", name=name)


def _resolve_category_shop(
    storage: Storage,
    scope_id: str,
    category_hint: str | None,
    shop_hint: str | None,
    item_name: str,
    language: str,
) -> tuple[int | None, int | None]:
    category_id = None
    shop_id = None
    if category_hint:
        row = storage.find_category(scope_id, category_hint)
        if row:
            category_id = row["id"]
    if shop_hint:
        row = storage.find_shop(scope_id, shop_hint)
        if row:
            shop_id = row["id"]
    if category_id is None:
        cat_names = [r["name"] for r in storage.list_categories(scope_id)]
        guessed = guess_category(item_name, cat_names, language)
        if guessed:
            row = storage.find_category(scope_id, guessed)
            category_id = row["id"] if row else None
    return category_id, shop_id


def _add_item_from_text(
    storage: Storage,
    scope_id: str,
    list_id: int,
    sender: str,
    raw: str,
    language: str,
    image_path: str | None = None,
) -> str:
    name, quantity, cat_hint, shop_hint = parse_add_text(raw)
    if not name:
        return text_for(storage, scope_id, "usage_add")
    category_id, shop_id = _resolve_category_shop(storage, scope_id, cat_hint, shop_hint, name, language)
    ok, normalized = storage.add_item(
        scope_id,
        list_id,
        name,
        quantity=quantity,
        category_id=category_id,
        shop_id=shop_id,
        added_by=sender,
        image_path=image_path,
        language=language,
    )
    if not ok:
        return text_for(storage, scope_id, "already_on_list", name=normalized or name)
    extra_parts = []
    if cat_hint:
        extra_parts.append(f"@{cat_hint}")
    if shop_hint:
        extra_parts.append(f"#{shop_hint}")
    extra = f" ({' '.join(extra_parts)})" if extra_parts else ""
    return text_for(storage, scope_id, "added", name=normalized, extra=extra)


def _handle_photo(
    storage: Storage,
    scope_id: str,
    sender: str,
    list_id: int,
    attachments: list[dict[str, Any]],
    caption: str,
) -> str:
    image_attachments = [
        a for a in attachments
        if str(a.get("contentType", "")).startswith("image/") or not a.get("contentType")
    ]
    if not image_attachments:
        return text_for(storage, scope_id, "photo_no_image")

    image_path = ""
    fetched = fetch_incoming_image(SIGNAL_API_URL, image_attachments[0])
    if fetched:
        data, content_type = fetched
        image_path = save_item_image(scope_id, 0, data, content_type)

    name = caption.strip()
    return _start_add_dialogue(storage, scope_id, sender, list_id, name=name, image_path=image_path)


def handle_command(
    storage: Storage,
    command_text: str,
    *,
    sender: str,
    scope_id: str,
    group_id: str | None,
    attachments: list[dict[str, Any]] | None = None,
) -> str | dict:
    language = storage.get_language(scope_id) if storage.has_language(scope_id) else "en"
    command_lowered = command_text.strip().lower()
    attachments = attachments or []

    if not storage.has_language(scope_id):
        picked = _language_from_command(command_text)
        if picked:
            storage.set_language(scope_id, picked)
            storage.add_admin(scope_id, sender)
            storage.seed_defaults(scope_id, picked)
            return text_for(storage, scope_id, "setup_complete")
        return text_for(storage, scope_id, "setup_choose_language")

    list_id = storage.get_active_list_id(scope_id)
    if list_id is None:
        storage.seed_defaults(scope_id, language)
        list_id = storage.get_active_list_id(scope_id)

    if _is_cancel(command_text):
        storage.clear_pending_add(scope_id, sender)
        storage.clear_pending_check(scope_id, sender)
        return text_for(storage, scope_id, "cancelled")

    pending_add = _handle_pending_add(storage, command_text, sender, scope_id)
    if pending_add is not None:
        return pending_add

    pending_check = _handle_pending_check(storage, command_text, sender, scope_id)
    if pending_check is not None:
        return pending_check

    if attachments and list_id:
        return _handle_photo(storage, scope_id, sender, list_id, attachments, command_text)

    if command_lowered in {"help", "hilfe", "?"}:
        return text_for(storage, scope_id, "help")

    lang_cmd = _language_from_command(command_text)
    if lang_cmd and group_id:
        if not storage.is_admin(scope_id, sender):
            return text_for(storage, scope_id, "admin_only")
        storage.set_language(scope_id, lang_cmd)
        return text_for(storage, scope_id, "language_set_de" if lang_cmd == "de" else "language_set_en")

    # --- list display ---
    if command_lowered in {"list", "liste", "show", "anzeigen"} and list_id:
        return _format_list(storage, scope_id, list_id)
    for prefix in ("list ", "liste ", "shop ", "laden "):
        if command_lowered.startswith(prefix) and list_id:
            shop_filter = command_text.strip().split(maxsplit=1)[1].strip()
            return _format_list(storage, scope_id, list_id, shop_filter=shop_filter)

    # --- guided add ---
    if command_lowered in {"add", "hinzufügen", "hinzufuegen"} and list_id:
        return _start_add_dialogue(storage, scope_id, sender, list_id)

    # --- guided check ---
    if command_lowered in {"done", "check", "got", "gekauft", "erledigt"} and list_id:
        storage.start_pending_check(scope_id, sender, list_id)
        return _open_items_pick_list(storage, scope_id, list_id)

    # --- quick add ---
    add_payload = None
    if command_lowered.startswith("+"):
        add_payload = command_text.strip()[1:].strip()
    else:
        for prefix in ("add ", "hinzufügen ", "hinzufuegen "):
            rest = strip_command_prefix(command_text, (prefix.strip(),))
            if rest is not None and command_lowered.startswith(prefix.strip()) and rest:
                add_payload = rest
                break
    if add_payload is not None and list_id:
        return _add_item_from_text(storage, scope_id, list_id, sender, add_payload, language)

    # --- quick check/remove ---
    for prefixes, action in (
        (("done ", "check ", "got ", "gekauft ", "erledigt "), "check"),
        (("uncheck ", "undo ", "zurück ", "zurueck "), "uncheck"),
        (("remove ", "delete ", "entfernen ", "löschen ", "loeschen "), "remove"),
    ):
        for prefix in prefixes:
            rest = strip_command_prefix(command_text, (prefix.strip(),))
            if rest is not None and command_lowered.startswith(prefix.strip()) and list_id:
                if action == "check":
                    ok = storage.check_item(scope_id, list_id, rest)
                    return text_for(storage, scope_id, "checked" if ok else "not_found", name=rest)
                if action == "uncheck":
                    ok = storage.uncheck_item(scope_id, list_id, rest)
                    return text_for(storage, scope_id, "unchecked" if ok else "not_found", name=rest)
                ok = storage.remove_item(scope_id, list_id, rest)
                return text_for(storage, scope_id, "removed" if ok else "not_found", name=rest)

    if command_lowered in {"clear checked", "clear", "erledigt löschen", "erledigt loeschen"}:
        count = storage.clear_checked(scope_id, list_id) if list_id else 0
        return text_for(storage, scope_id, "cleared", count=count)

    if command_lowered in {"categories", "kategorien"}:
        rows = storage.list_categories(scope_id)
        lines = [text_for(storage, scope_id, "categories_header")]
        lines.extend(text_for(storage, scope_id, "categories_line", name=r["name"]) for r in rows)
        return mobile_blocks(*lines)

    if command_lowered.startswith("category add ") or command_lowered.startswith("kategorie add "):
        name = command_text.split(maxsplit=2)[-1].strip()
        if storage.add_category(scope_id, name):
            return text_for(storage, scope_id, "category_added", name=name)
        return text_for(storage, scope_id, "list_exists", name=name)

    if command_lowered in {"shops", "geschäfte", "geschaefte", "stores"}:
        rows = storage.list_shops(scope_id)
        if not rows:
            tip = "Add with: shop add Rewe" if language == "en" else "Hinzufügen mit: laden add Rewe"
            return text_for(storage, scope_id, "shops_header") + "\n\n💡 " + tip
        lines = [text_for(storage, scope_id, "shops_header")]
        lines.extend(text_for(storage, scope_id, "shops_line", name=r["name"]) for r in rows)
        return mobile_blocks(*lines)

    if command_lowered.startswith("shop add ") or command_lowered.startswith("laden add "):
        name = command_text.split(maxsplit=2)[-1].strip()
        if storage.add_shop(scope_id, name):
            return text_for(storage, scope_id, "shop_added", name=name)
        return text_for(storage, scope_id, "list_exists", name=name)

    if command_lowered in {"lists", "listen"}:
        active_id = storage.get_active_list_id(scope_id)
        rows = storage.list_shopping_lists(scope_id)
        lines = [text_for(storage, scope_id, "lists_header")]
        for row in rows:
            active = "👉" if row["id"] == active_id else "  "
            open_label = "open" if language == "en" else "offen"
            lines.append(f"{active} {row['name']} ({row['open_count']} {open_label})")
        return mobile_blocks(*lines)

    if command_lowered.startswith("list use ") or command_lowered.startswith("liste nutze "):
        name = command_text.split(maxsplit=2)[-1].strip()
        if storage.set_active_list(scope_id, name):
            return text_for(storage, scope_id, "list_active", name=name)
        return text_for(storage, scope_id, "list_unknown", name=name)

    if command_lowered.startswith("list new ") or command_lowered.startswith("liste neu "):
        name = command_text.split(maxsplit=2)[-1].strip()
        if storage.create_list(scope_id, name):
            storage.set_active_list(scope_id, name)
            return text_for(storage, scope_id, "list_created", name=name)
        return text_for(storage, scope_id, "list_exists", name=name)

    if command_lowered in {"frequent", "usual", "häufig", "haeufig", "oft"}:
        rows = storage.frequent_items(scope_id)
        if not rows:
            return text_for(storage, scope_id, "list_empty")
        lines = [text_for(storage, scope_id, "frequent_header")]
        lines.extend(text_for(storage, scope_id, "frequent_line", name=r["name"], count=r["use_count"]) for r in rows)
        lines.append("💡 " + ("Re-add with: add or + name" if language == "en" else "Wieder: hinzufügen oder + name"))
        return mobile_blocks(*lines)

    if command_lowered.startswith("search ") or command_lowered.startswith("suche "):
        query = command_text.split(maxsplit=1)[1].strip() if " " in command_text else ""
        if not query or not list_id:
            return text_for(storage, scope_id, "search_empty", query=query or "?")
        rows = storage.search_items(scope_id, list_id, query)
        if not rows:
            return text_for(storage, scope_id, "search_empty", query=query)
        lines = [text_for(storage, scope_id, "search_header")]
        for row in rows:
            mark = "✓" if row["checked"] else "•"
            meta = f" ({row['category_name']})" if row["category_name"] else ""
            lines.append(text_for(storage, scope_id, "search_line", mark=mark, name=row["name"], meta=meta))
        return mobile_blocks(*lines)

    if command_lowered.startswith("admin"):
        if command_lowered in {"admin", "administrator", "admin help", "admin hilfe"}:
            return text_for(storage, scope_id, "admin_help")
        if not storage.is_admin(scope_id, sender):
            return text_for(storage, scope_id, "admin_only")
        if command_lowered == "admin reset":
            storage.admin_reset(scope_id)
            return text_for(storage, scope_id, "reset_done")

    return text_for(storage, scope_id, "help")
