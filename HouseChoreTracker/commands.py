from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from schedule_utils import (
    format_local_timestamp,
    format_reminder_time_label,
    format_schedule_delay,
    format_schedule_frequency,
    humanize_schedule,
    is_one_shot_schedule,
    next_due_at,
    normalize_timezone_name,
    one_shot_stats_label,
    ONE_SHOT_STATS_KEY,
    parse_db_datetime,
    parse_reminder_time_answer,
    parse_schedule,
    reminder_time_applies,
    effective_reminder_at_minutes,
    schedule_from_storage,
    schedule_to_storage,
)
from storage import Storage
from bot_registry import load_bot_registry, runtime_bot_id
from display_names import is_valid_display_name
from chart_parse import parse_chart_command
from dialogue_utils import STALE_STEP, append_usage_tip, mobile_blocks, parse_stale_response, stale_prompt_text
from stats_charts import group_chart_kinds, group_stats_chart, user_stats_chart
from vacation_utils import format_duration, parse_duration, parse_vacation_plan
from tutorial import parse_tutorial_command, tutorial_text


SUPPORTED_LANGUAGES = {"en", "de"}

USAGE_TIPS = {
    "en": {
        "list": "Mark a chore as done with: done <chore>",
        "done": "See all chores anytime with: list",
        "add": "Quick add: add <name> <schedule>, e.g. add bins every Wednesday",
        "undo": "Undo the last completion with: undo done <chore>",
        "history": "See all chores with: list",
        "name": "Your name is shown when you mark chores as done.",
        "stats": "my stats · group stats · group stats chore <name>",
    },
    "de": {
        "list": "Abhaken mit: erledigt <Aufgabe>",
        "done": "Alle Aufgaben anzeigen: liste",
        "add": "Schnell anlegen: aufgabe <Name> <Zeitplan>, z.B. aufgabe Müll jeden Mittwoch",
        "undo": "Letzte Erledigung rückgängig machen: rückgängig <Aufgabe>",
        "history": "Alle Aufgaben anzeigen: liste",
        "name": "Dein Name wird angezeigt, wenn du Aufgaben abhakst.",
        "stats": "meine statistik · gruppen statistik · gruppen statistik aufgabe <Name>",
    },
}

TEXT = {
    "en": {
        "help": (
            "🧹 Chore bot – commands\n\n"
            "Everyday:\n"
            "- 📋 list · list extend\n"
            "- ✅ done <chore> [for <person>]\n"
            "- ↩️ undo done <chore>\n"
            "- 👤 name <your name>\n\n"
            "Manage chores:\n"
            "- ➕ add  (step by step)\n"
            "- ➕ add <name> <schedule>, e.g. add bins every Wednesday\n"
            "- 📝 todo <name>  (no schedule)\n"
            "- 📝 once  (one-time chore, step by step)\n"
            "- ✏️ edit <chore>  (change or delete)\n"
            "More: chore help · edit help\n\n"
            "Also:\n"
            "- 📊 my stats · group stats\n"
            "- 🏖️ vacation · vacation help\n"
            "- 🕐 history\n"
            "- 🎓 tutorial  (how everything works, step by step)\n"
            "🔧 Admin: admin help"
        ),
        "chore_help": (
            "➕ Adding chores:\n"
            "- add – step by step (name → schedule → time if needed → confirmation)\n"
            "- add bins every Wednesday\n"
            "- add clean bathroom every week\n"
            "- todo buy vacuum  (open task without a due date)\n"
            "- once – step by step (name → when → time → count in stats? → confirmation)\n"
            "- once IKEA  (the bot asks for the rest)\n"
            "One-time chores disappear once they are done or deleted. Counting them in stats is optional."
        ),
        "edit_help": (
            "✏️ Change a chore with: edit <chore>\n"
            "Then choose: name, schedule, reminder time, confirmation, overdue reminder or delete.\n"
            "Cancel anytime with: cancel"
        ),
        "setup_choose_language": (
            "👋 Welcome! First, choose the language for this group:\n"
            "- english\n"
            "- deutsch"
        ),
        "setup_choose_bot": (
            "Which bot should manage this group?\n"
            "{options}\n"
            "Reply with: bot <number>"
        ),
        "setup_bot_set": "✅ This group is now managed by {name} (bot {bot_id}).",
        "setup_complete": "🎉 All set! Try for example: add dishes every day · list · help\n🎓 New here? The tutorial explains everything: tutorial",
        "setup_bot_invalid": "Unknown bot. Reply with: bot <number>",
        "setup_bot_usage": "Usage: bot <number>",
        "admin_usage": "🔧 Show admin commands with: admin help",
        "admin_help": (
            "🔧 Admin commands:\n"
            "- 🌐 admin language de\n"
            "- 🕒 admin timezone Europe/Berlin\n"
            "- 📊 admin stats\n"
            "- 🔕 admin quiet hours 00:00-08:00\n"
            "- 🔗 admin auth reminder on/off\n"
            "- 🗑️ admin reset group"
        ),
        "admin_only": "In groups, put admin in front of this command, e.g.: admin language de",
        "admin_status": "Group status: {chore_count} chore(s), language: {chat_language}.",
        "stats_header": "📊 Group statistics:",
        "stats_summary": "- chores: {chore_count}\n- completions: {done_count}",
        "stats_actions_header": "Actions:",
        "stats_top_done_header": "Most completed chores:",
        "stats_recent_header": "Recent actions:",
        "stats_none": "No data yet.",
        "user_stats_header": "📊 Your chore stats:",
        "user_stats_line": "- completions: {total}\n- different chores: {unique}\n- most frequent: {favorite}\n- last done: {last_done}",
        "user_stats_by_chore_header": "How often you did each chore:",
        "user_stats_by_chore_line": "- {name}: {count}x",
        "user_stats_empty": "You have not completed any chores yet. Try: done <chore>",
        "task_stats_header": "📊 Chore stats:",
        "task_stats_line": "- {name}: {count}x in total (last: {last_done} by {who})",
        "task_stats_by_person_none": "   nobody yet",
        "task_stats_empty": "No chores yet. Try: add",
        "group_stats_header": "📊 Group chore statistics:",
        "group_stats_summary": "- chores: {chore_count}\n- total completions: {done_count}",
        "group_stats_users_header": "Who did how much (all chores):",
        "group_stats_users_line": "- {name}: {count}x",
        "group_stats_users_none": "- no completions yet",
        "group_stats_chores_header": "Per chore:",
        "group_chore_stats_header": "📊 Group stats for '{name}':",
        "group_chore_stats_summary": "- total completions: {count}",
        "group_chore_stats_users_header": "Who did it:",
        "group_chore_stats_user_line": "- {name}: {count}x",
        "group_chore_stats_none": "- nobody yet",
        "user_chore_stats_header": "📊 Your stats for '{name}':",
        "user_chore_stats_line": "- completions: {count}\n- last done: {last_done}",
        "user_chore_stats_none": "You have not completed '{name}' yet.",
        "stats_usage": (
            "💡 Statistics:\n"
            "• my stats\n"
            "• group stats\n"
            "• group stats chore <name>\n"
            "• group stats people / chores / matrix\n"
            "• group stats all  (all charts in one image)\n"
            "• my stats chart"
        ),
        "stats_chart_empty": "📈 Not enough data for a chart yet.",
        "stats_chart_unknown": (
            "📈 Unknown chart. Try:\n"
            "• group stats people\n"
            "• group stats chores\n"
            "• group stats matrix\n"
            "• group stats all"
        ),
        "stats_chart_suggest_group": "💡 Also: group stats chores · matrix · all",
        "stats_chore_usage": "Usage: group stats chore <name>",
        "stats_all_charts_header": "📈 All group charts:",
        "confirm_add": "Add '{name}' ({interval})?\nReply: yes, no or cancel",
        "edit_options": (
            "What do you want to change for '{name}'?\n"
            "- name\n"
            "- schedule\n"
            "- reminder time\n"
            "- confirmation\n"
            "- overdue reminder\n"
            "- delete\n"
            "Reply with one option, or cancel."
        ),
        "edit_choose_option": "Please choose one of the options above, or cancel.",
        "edit_new_name": "What should '{name}' be called from now on?\nReply with the new name, or cancel.",
        "edit_new_schedule": (
            "How often is '{name}' due?\n"
            "Examples: every day, every 2 weeks, every Wednesday, no schedule.\n"
            "Reply with the schedule, or cancel."
        ),
        "edit_new_remind_time": (
            "At what time should the bot remind you about '{name}'?\n"
            "Examples: 08:00, 19:45 – or anytime (then 08:00).\n"
            "Reply with a time, or cancel."
        ),
        "edit_new_confirmation": "Does '{name}' have to be marked as done?\nReply: yes, no or cancel",
        "edit_new_repeat": (
            "How often should the bot remind you again while '{name}' is overdue?\n"
            "Examples: 1 hour, 8 hours.\n"
            "Reply with an interval, or cancel."
        ),
        "edit_confirm_delete": "Delete '{name}' including its history?\nReply: yes, no or cancel",
        "edit_delete_cancelled": "Deletion cancelled. '{name}' was kept.",
        "usage_edit": "Usage: edit <chore>",
        "no_pending_add": "No new chore is waiting for confirmation.",
        "cancelled": "↩️ Cancelled.",
        "confirm_expected": "Please reply with yes, no or cancel.",
        "setup_chore_name": "What is the chore called?\nReply with the name, or cancel.",
        "setup_chore_schedule": (
            "How often is '{name}' due?\n"
            "Examples: every day, every 2 weeks, every Wednesday.\n"
            "For an open task without a due date, reply: no schedule\n"
            "Reply with the schedule, or cancel."
        ),
        "setup_chore_remind_time": (
            "At what time should the bot remind you about '{name}' (group's local time)?\n"
            "Examples: 08:00, 19:45 – or anytime (then 08:00).\n"
            "Reply with a time, or cancel."
        ),
        "setup_chore_confirmation": (
            "Does '{name}' have to be marked as done?\n"
            "If yes, the bot keeps reminding you while it is overdue.\n"
            "Reply: yes, no or cancel"
        ),
        "setup_chore_repeat": (
            "How often should the bot remind you again while '{name}' is overdue?\n"
            "Reply with an interval (e.g. 1 hour), default ({default_interval}), or cancel."
        ),
        "no_chores": "📋 No chores yet. Add one, e.g.: add dishes every day · or without a schedule: todo buy milk",
        "chores_header": "📋 Chores:",
        "chores_header_extended": "📋 Chores (details):",
        "list_extend_tip": "Details: list extend",
        "open_task_short": "open",
        "reminder_label": "reminder",
        "reminder_time_label": "reminder time",
        "open_task_label": "open task · no schedule · can be marked done anytime",
        "confirmation_required": "must be marked as done: yes",
        "repeat_reminder_label": "reminder while overdue",
        "confirmation_required_no_reminder": "can still be marked as done",
        "confirmation_not_required": "must be marked as done: no",
        "confirmation_set_on": "'{name}' now has to be marked as done.",
        "confirmation_set_off": "'{name}' no longer has to be marked as done.",
        "usage_confirmation": "Usage: confirmation <chore> on/off",
        "schedule_set": "New schedule for '{name}': {interval}. The history was kept.",
        "usage_schedule": "Usage: schedule <chore> <schedule>, e.g. schedule dishes every day",
        "repeat_set": "Reminder while '{name}' is overdue: {interval}.",
        "usage_repeat": "Usage: reminder <chore> <interval>, e.g. reminder dishes 1 hour",
        "reminder_time_set": "Reminder time for '{name}': {time}.",
        "usage_reminder_time": "Usage: reminder time <chore> <HH:MM>, e.g. reminder time dishes 08:00",
        "quiet_hours_current": "Quiet hours: {start}-{end} ({timezone}). No reminders are sent during that time.",
        "quiet_hours_set": "Quiet hours set to {start}-{end} ({timezone}). No reminders are sent during that time.",
        "usage_quiet_hours": "Usage: admin quiet hours 00:00-08:00",
        "auth_reminder_current": "Signal link reminders are {state}.",
        "auth_reminder_set_on": "Signal link reminders enabled. The bot will remind this group roughly every 25 days.",
        "auth_reminder_set_off": "Signal link reminders disabled.",
        "usage_auth_reminder": "Usage: admin auth reminder on/off",
        "disabled": "disabled",
        "enabled": "enabled",
        "no_groups": "No groups registered yet.",
        "groups_header": "Registered groups:",
        "current_language": "Current language: English. Change it with: admin language de",
        "language_set_en": "This chat's language is now English.",
        "language_set_de": "This chat's language is now German.",
        "language_usage": "Usage: admin language en or admin language de",
        "current_timezone": "Current timezone: {timezone}. Change it with: admin timezone Europe/Berlin",
        "timezone_set": "Timezone set to {timezone}. Reminder times and quiet hours use this timezone.",
        "timezone_usage": "Usage: admin timezone Europe/Berlin (also: berlin, utc, london, paris, …)",
        "usage_done": "Usage: done <chore> [for <person>]",
        "usage_undo_done": "Usage: undo done <chore>",
        "undo_done_saved": "↩️ Undid the last completion of '{name}'.",
        "undo_done_missing": "There is no completion of '{name}' to undo.",
        "usage_add": "Usage: add <name> <schedule>, e.g. add dishes every day · without a schedule: todo buy milk",
        "usage_task": (
            "Usage: todo <name>, e.g. todo buy new vacuum\n"
            "This creates an open task without a schedule that you can mark as done anytime."
        ),
        "added": "✅ Added chore: {name} ({interval}).",
        "added_open_task": "✅ Added open task: {name}. No schedule – mark it as done anytime with: done {name}",
        "added_one_shot": (
            "✅ Added one-time chore: {name} ({interval}). It disappears once it is done. "
            "Counted in stats: {stats}. Delete it with: delete {name}"
        ),
        "usage_once": (
            "Usage: once  (step by step)\n"
            "Or: once <name> [today|tomorrow|<weekday>]\n"
            "The bot then asks for the time and whether it counts in stats."
        ),
        "setup_once_schedule": (
            "When should the one-time chore '{name}' be done?\n"
            "Examples: today, tomorrow, Friday.\n"
            "Reply with when, or cancel."
        ),
        "setup_once_remind_time": (
            "At what time should the bot remind you about '{name}' (group's local time)?\n"
            "Examples: 08:00, 19:45 – or anytime (then 08:00).\n"
            "Reply with a time, or cancel."
        ),
        "setup_once_count_stats": (
            "Should '{name}' count in the stats (under one-time chores)?\n"
            "Reply: yes, no or cancel"
        ),
        "once_short": "once",
        "once_stats_yes": "yes",
        "once_stats_no": "no",
        "count_in_stats_label": "counts in stats",
        "count_in_stats_yes": "yes (one-time chores)",
        "count_in_stats_no": "no",
        "already_exists": "The chore '{name}' already exists. See all chores with: list",
        "could_not_add": "Could not add '{name}'. Usage: add <name> <schedule> or todo <name>",
        "usage_delete": "Usage: delete <chore>",
        "deleted": "🗑️ Deleted chore: {name}",
        "not_found": "⚠️ The chore '{name}' was not found.",
        "usage_change": "Usage: rename <old name> -> <new name>",
        "no_history": "No chores have been completed yet.",
        "history_header": "🕐 Recently completed:",
        "history_line": "{idx}. {name} – {sender}, {done_at}",
        "group_only": "This command only works in group chats.",
        "reset_requested": (
            "⚠️ Reset requested. This deletes all chores and the entire history of this group.\n"
            "To confirm within 10 minutes, send: admin reset group confirm {token}\n"
            "To cancel, send: admin reset group cancel"
        ),
        "usage_reset_confirm": "Usage: admin reset group confirm <code>",
        "reset_failed": (
            "Reset not confirmed. The code must be correct and not expired, "
            "and it must be sent by the same person who requested the reset."
        ),
        "reset_done": "✅ This group's chores, history and reminders have been reset.",
        "did_you_mean": "Did you mean: {command}?",
        "unexpected_error": "⚠️ Something went wrong while handling your command.",
        "mark_done_missing": (
            "⚠️ The chore '{name}' was not found. Create it first with add or todo. "
            "See all chores with: list"
        ),
        "mark_done_saved": "✅ Done: {name} – by {sender} ({done_at}).\nUndo: undo done {name}",
        "mark_done_one_shot": "✅ {name} done by {sender} ({done_at}) and removed from the list.\nCounted under one-time chores.",
        "mark_done_one_shot_no_stats": "✅ {name} done by {sender} ({done_at}) and removed from the list.\nNot counted in stats.",
        "done_member_not_found": (
            "⚠️ I don't know a group member called '{name}'. "
            "That person needs to set a name first with: name <name>"
        ),
        "ask_display_name": (
            "Which name should I show for your completed chores?\n"
            "Reply with your name, or cancel."
        ),
        "display_name_invalid": "Please use 2-24 characters: letters, numbers, spaces or hyphens.",
        "display_name_saved": "👤 Your name is now: {name}",
        "usage_name": "Usage: name <your name>",
        "renamed": "✏️ '{old}' is now called '{new}'.",
        "new_name_empty": "The new name cannot be empty.",
        "rename_missing": "The chore '{name}' does not exist.",
        "rename_exists": "The chore '{name}' already exists.",
        "reminder": (
            "🔔 Reminder: '{name}' is due.\n"
            "Done? Then send: done {name}\n"
            "💡 All commands: help"
        ),
        "reminder_no_confirmation": (
            "🔔 Reminder: '{name}' is due.\n"
            "💡 All commands: help"
        ),
        "auth_reminder": (
            "🔗 Signal link reminder: linked devices can be disconnected after a long period of inactivity.\n"
            "If the bot stops replying, it has to be re-linked: http://127.0.0.1:8080/v1/qrcodelink?device_name=signal-api"
        ),
        "vacation_help": (
            "🏖️ Vacation mode:\n"
            "- vacation – step by step (start now or in X days, then the duration)\n"
            "- vacation 14 days – starts now, lasts 14 days\n"
            "- vacation in 3 days for 14 days – plan ahead\n"
            "- vacation status – show your vacation\n"
            "- vacation cancel – cancel a planned or active vacation\n"
            "- vacation add – add a task to do before leaving\n"
            "- vacation add empty fridge\n"
            "- vacation list – show tasks to do before leaving\n"
            "- vacation delete <name>\n"
            "- vacation done <name> – check off a task before leaving\n"
            "- vacation skip prep – skip the remaining tasks before leaving\n"
            "During the vacation, chore reminders are paused. Afterwards, the normal schedule continues – "
            "e.g. a weekly Friday chore reminds you on the first Friday after the vacation, not on the day you return."
        ),
        "vacation_setup_when": (
            "🏖️ Vacation – when does it start?\n"
            "Reply: now, in 3 days, or cancel"
        ),
        "vacation_setup_duration": (
            "🏖️ How long is the vacation?\n"
            "Reply with a duration, e.g. 14 days or 2 weeks – or cancel"
        ),
        "vacation_setup_chore_name": (
            "🏖️ What is the task to do before leaving called?\n"
            "Reply with the name, or cancel"
        ),
        "vacation_usage": "🏖️ Try: vacation, vacation 14 days or vacation help",
        "vacation_duration_invalid": "I could not understand that duration. Example: 14 days or 2 weeks",
        "vacation_when_invalid": "Please reply with now, in 3 days, or cancel",
        "vacation_chore_added": "Task before leaving added: {name}",
        "vacation_chore_exists": "The task before leaving '{name}' already exists.",
        "vacation_chore_deleted": "Task before leaving deleted: {name}",
        "vacation_chore_not_found": "Task before leaving not found: {name}",
        "vacation_chore_list_empty": "No tasks before leaving yet. Add one with: vacation add",
        "vacation_chore_list": "Tasks before leaving:\n{items}",
        "vacation_none": "You have no planned or active vacation.",
        "vacation_cancelled": "Vacation cancelled. Chores continue as usual.",
        "vacation_nothing_to_cancel": "You have no vacation to cancel.",
        "vacation_prep_done": "Task before leaving done: {name}",
        "vacation_prep_not_found": "Task before leaving not found, or the vacation is not in preparation: {name}",
        "vacation_prep_skipped": "Preparation skipped. The vacation is now active and reminders are paused.",
        "vacation_prep_skip_unavailable": "There is no preparation to skip.",
        "vacation_scheduled": (
            "🏖️ Vacation planned.\n"
            "Starts: {starts}\n"
            "Ends: {ends}\n"
            "Duration: {duration}\n"
            "Reminders are paused once it starts."
        ),
        "vacation_started_active": (
            "🏖️ Vacation started.\n"
            "Ends: {ends}\n"
            "Duration: {duration}\n"
            "Until then, there are no chore reminders. Afterwards, the normal schedule continues."
        ),
        "vacation_started_prep": (
            "🏖️ Vacation starts – please finish these tasks before leaving:\n"
            "{items}\n\n"
            "Check them off with: vacation done <name>\n"
            "Or skip them all with: vacation skip prep\n\n"
            "Chore reminders are paused until the vacation ends."
        ),
        "vacation_status_scheduled": (
            "🏖️ Planned vacation\n"
            "Starts: {starts}\n"
            "Ends: {ends}\n"
            "Duration: {duration}"
        ),
        "vacation_status_prep": (
            "🏖️ Vacation (preparation)\n"
            "Ends: {ends}\n"
            "Still to do:\n{items}"
        ),
        "vacation_status_active": (
            "🏖️ Vacation in progress\n"
            "Ends: {ends}\n"
            "No chore reminders until then; afterwards, the normal schedule continues."
        ),
        "vacation_ended_notice": (
            "🏖️ {name}'s vacation is over. Chore reminders follow the normal schedule again."
        ),
        "vacation_started_notice": (
            "🏖️ {name}'s vacation has started. No reminders until {ends}; "
            "afterwards, the normal schedule continues."
        ),
        "vacation_started_prep_notice": (
            "🏖️ {name}'s vacation has started. Still to do before leaving:\n{items}"
        ),
    },
    "de": {
        "help": (
            "🧹 Haushalts-Bot – Befehle\n\n"
            "Im Alltag:\n"
            "- 📋 liste · liste erweitert\n"
            "- ✅ erledigt <Aufgabe> [für <Person>]\n"
            "- ↩️ rückgängig <Aufgabe>\n"
            "- 👤 name <dein Name>\n\n"
            "Aufgaben verwalten:\n"
            "- ➕ aufgabe  (Schritt für Schritt)\n"
            "- ➕ aufgabe <Name> <Zeitplan>, z.B. aufgabe Müll jeden Mittwoch\n"
            "- 📝 todo <Name>  (ohne Zeitplan)\n"
            "- 📝 einmal  (einmalige Aufgabe, Schritt für Schritt)\n"
            "- ✏️ bearbeite <Aufgabe>  (ändern oder löschen)\n"
            "Mehr: aufgabe hilfe · bearbeite hilfe\n\n"
            "Außerdem:\n"
            "- 📊 meine statistik · gruppen statistik\n"
            "- 🏖️ urlaub · urlaub hilfe\n"
            "- 🕐 verlauf\n"
            "- 🎓 anleitung  (alle Abläufe Schritt für Schritt erklärt)\n"
            "🔧 Admin: admin hilfe"
        ),
        "chore_help": (
            "➕ Aufgabe anlegen:\n"
            "- aufgabe – Schritt für Schritt (Name → Zeitplan → ggf. Uhrzeit → Bestätigung)\n"
            "- aufgabe Müll jeden Mittwoch\n"
            "- aufgabe Bad putzen jede Woche\n"
            "- todo Staubsauger kaufen  (offene Aufgabe ohne Termin)\n"
            "- einmal – Schritt für Schritt (Name → wann → Uhrzeit → Statistik? → Bestätigung)\n"
            "- einmal IKEA  (der Bot fragt den Rest nach)\n"
            "Einmalige Aufgaben verschwinden, sobald sie erledigt oder gelöscht sind. "
            "Ob sie in der Statistik zählen, entscheidest du."
        ),
        "edit_help": (
            "✏️ Aufgabe ändern mit: bearbeite <Aufgabe>\n"
            "Danach wählst du: name, zeitplan, erinnerungszeit, bestätigung, wiederholung oder löschen.\n"
            "Abbrechen jederzeit mit: abbrechen"
        ),
        "setup_choose_language": (
            "👋 Willkommen! Wähle zuerst die Sprache für diese Gruppe:\n"
            "- deutsch\n"
            "- english"
        ),
        "setup_choose_bot": (
            "Welcher Bot soll diese Gruppe betreuen?\n"
            "{options}\n"
            "Antworte mit: bot <Nummer>"
        ),
        "setup_bot_set": "✅ Diese Gruppe wird jetzt von {name} betreut (bot {bot_id}).",
        "setup_complete": "🎉 Alles eingerichtet! Probier zum Beispiel: aufgabe Müll jeden Mittwoch · liste · hilfe\n🎓 Neu hier? Die Anleitung erklärt alles: anleitung",
        "setup_bot_invalid": "Diesen Bot gibt es nicht. Antworte mit: bot <Nummer>",
        "setup_bot_usage": "So geht's: bot <Nummer>",
        "admin_usage": "🔧 Admin-Befehle anzeigen: admin hilfe",
        "admin_help": (
            "🔧 Admin-Befehle:\n"
            "- 🌐 admin sprache englisch\n"
            "- 🕒 admin zeitzone Europe/Berlin\n"
            "- 📊 admin statistik\n"
            "- 🔕 admin ruhezeit 00:00-08:00\n"
            "- 🔗 admin signal erinnerung an/aus\n"
            "- 🗑️ admin zurücksetzen"
        ),
        "admin_only": "In Gruppen bitte admin vor diesen Befehl schreiben, z.B.: admin sprache englisch",
        "admin_status": "Gruppenstatus: {chore_count} Aufgabe(n), Sprache: {chat_language}.",
        "stats_header": "📊 Gruppenstatistik:",
        "stats_summary": "- Aufgaben: {chore_count}\n- Erledigungen: {done_count}",
        "stats_actions_header": "Aktionen:",
        "stats_top_done_header": "Am häufigsten erledigt:",
        "stats_recent_header": "Letzte Aktionen:",
        "stats_none": "Noch keine Daten.",
        "user_stats_header": "📊 Deine Statistik:",
        "user_stats_line": "- Erledigungen: {total}\n- verschiedene Aufgaben: {unique}\n- am häufigsten: {favorite}\n- zuletzt: {last_done}",
        "user_stats_by_chore_header": "So oft hast du die einzelnen Aufgaben erledigt:",
        "user_stats_by_chore_line": "- {name}: {count}x",
        "user_stats_empty": "Du hast noch keine Aufgabe erledigt. Probier: erledigt <Aufgabe>",
        "task_stats_header": "📊 Aufgabenstatistik:",
        "task_stats_line": "- {name}: {count}x insgesamt (zuletzt: {last_done} von {who})",
        "task_stats_by_person_none": "   noch niemand",
        "task_stats_empty": "Noch keine Aufgaben. Probier: aufgabe",
        "group_stats_header": "📊 Gruppenstatistik:",
        "group_stats_summary": "- Aufgaben: {chore_count}\n- Erledigungen insgesamt: {done_count}",
        "group_stats_users_header": "Wer wie viel erledigt hat (alle Aufgaben):",
        "group_stats_users_line": "- {name}: {count}x",
        "group_stats_users_none": "- noch keine Erledigungen",
        "group_stats_chores_header": "Pro Aufgabe:",
        "group_chore_stats_header": "📊 Gruppenstatistik für '{name}':",
        "group_chore_stats_summary": "- Erledigungen insgesamt: {count}",
        "group_chore_stats_users_header": "Wer sie erledigt hat:",
        "group_chore_stats_user_line": "- {name}: {count}x",
        "group_chore_stats_none": "- noch niemand",
        "user_chore_stats_header": "📊 Deine Statistik für '{name}':",
        "user_chore_stats_line": "- Erledigungen: {count}\n- zuletzt: {last_done}",
        "user_chore_stats_none": "Du hast '{name}' noch nicht erledigt.",
        "stats_usage": (
            "💡 Statistik:\n"
            "• meine statistik\n"
            "• gruppen statistik\n"
            "• gruppen statistik aufgabe <Name>\n"
            "• gruppen statistik leute / aufgaben / matrix\n"
            "• gruppen statistik alle  (alle Diagramme in einem Bild)\n"
            "• meine statistik diagramm"
        ),
        "stats_chart_empty": "📈 Für ein Diagramm gibt es noch nicht genug Daten.",
        "stats_chart_unknown": (
            "📈 Dieses Diagramm gibt es nicht. Probier:\n"
            "• gruppen statistik leute\n"
            "• gruppen statistik aufgaben\n"
            "• gruppen statistik matrix\n"
            "• gruppen statistik alle"
        ),
        "stats_chart_suggest_group": "💡 Außerdem: gruppen statistik aufgaben · matrix · alle",
        "stats_chore_usage": "So geht's: gruppen statistik aufgabe <Name>",
        "stats_all_charts_header": "📈 Alle Gruppendiagramme:",
        "confirm_add": "'{name}' ({interval}) anlegen?\nAntworte: ja, nein oder abbrechen",
        "edit_options": (
            "Was möchtest du bei '{name}' ändern?\n"
            "- name\n"
            "- zeitplan\n"
            "- erinnerungszeit\n"
            "- bestätigung\n"
            "- wiederholung\n"
            "- löschen\n"
            "Antworte mit einer Option oder mit abbrechen."
        ),
        "edit_choose_option": "Bitte wähle eine der Optionen oben oder antworte mit abbrechen.",
        "edit_new_name": "Wie soll '{name}' künftig heißen?\nAntworte mit dem neuen Namen oder mit abbrechen.",
        "edit_new_schedule": (
            "Wie oft ist '{name}' fällig?\n"
            "Beispiele: jeden Tag, alle 2 Wochen, jeden Mittwoch, ohne zeitplan.\n"
            "Antworte mit dem Zeitplan oder mit abbrechen."
        ),
        "edit_new_remind_time": (
            "Um wie viel Uhr soll der Bot an '{name}' erinnern?\n"
            "Beispiele: 08:00, 19:45 – oder egal (dann 08:00).\n"
            "Antworte mit einer Uhrzeit oder mit abbrechen."
        ),
        "edit_new_confirmation": "Muss '{name}' als erledigt abgehakt werden?\nAntworte: ja, nein oder abbrechen",
        "edit_new_repeat": (
            "Wie oft soll der Bot erneut erinnern, solange '{name}' überfällig ist?\n"
            "Beispiele: 1 Stunde, 8 Stunden.\n"
            "Antworte mit einem Abstand oder mit abbrechen."
        ),
        "edit_confirm_delete": "'{name}' samt Verlauf löschen?\nAntworte: ja, nein oder abbrechen",
        "edit_delete_cancelled": "Löschen abgebrochen. '{name}' bleibt bestehen.",
        "usage_edit": "So geht's: bearbeite <Aufgabe>",
        "no_pending_add": "Es wartet keine neue Aufgabe auf Bestätigung.",
        "cancelled": "↩️ Abgebrochen.",
        "confirm_expected": "Bitte antworte mit ja, nein oder abbrechen.",
        "setup_chore_name": "Wie heißt die Aufgabe?\nAntworte mit dem Namen oder mit abbrechen.",
        "setup_chore_schedule": (
            "Wie oft ist '{name}' fällig?\n"
            "Beispiele: jeden Tag, alle 2 Wochen, jeden Mittwoch.\n"
            "Für eine offene Aufgabe ohne festen Termin antworte: ohne zeitplan\n"
            "Antworte mit dem Zeitplan oder mit abbrechen."
        ),
        "setup_chore_remind_time": (
            "Um wie viel Uhr soll der Bot an '{name}' erinnern (Ortszeit der Gruppe)?\n"
            "Beispiele: 08:00, 19:45 – oder egal (dann 08:00).\n"
            "Antworte mit einer Uhrzeit oder mit abbrechen."
        ),
        "setup_chore_confirmation": (
            "Muss '{name}' als erledigt abgehakt werden?\n"
            "Wenn ja, erinnert der Bot erneut, solange die Aufgabe überfällig ist.\n"
            "Antworte: ja, nein oder abbrechen"
        ),
        "setup_chore_repeat": (
            "Wie oft soll der Bot erneut erinnern, solange '{name}' überfällig ist?\n"
            "Antworte mit einem Abstand (z.B. 1 Stunde), mit standard ({default_interval}) oder mit abbrechen."
        ),
        "no_chores": "📋 Noch keine Aufgaben. Leg eine an, z.B.: aufgabe Geschirr jeden Tag · oder ohne Termin: todo Milch kaufen",
        "chores_header": "📋 Aufgaben:",
        "chores_header_extended": "📋 Aufgaben (Details):",
        "list_extend_tip": "Details: liste erweitert",
        "open_task_short": "offen",
        "reminder_label": "Erinnerung",
        "reminder_time_label": "Erinnerungszeit",
        "open_task_label": "offene Aufgabe · kein Zeitplan · jederzeit abhakbar",
        "confirmation_required": "muss abgehakt werden: ja",
        "repeat_reminder_label": "erneute Erinnerung bei Überfälligkeit",
        "confirmation_required_no_reminder": "kann trotzdem abgehakt werden",
        "confirmation_not_required": "muss abgehakt werden: nein",
        "confirmation_set_on": "'{name}' muss jetzt als erledigt abgehakt werden.",
        "confirmation_set_off": "'{name}' muss nicht mehr als erledigt abgehakt werden.",
        "usage_confirmation": "So geht's: bestätigung <Aufgabe> an/aus",
        "schedule_set": "Neuer Zeitplan für '{name}': {interval}. Der Verlauf bleibt erhalten.",
        "usage_schedule": "So geht's: zeitplan <Aufgabe> <Zeitplan>, z.B. zeitplan Geschirr jeden Tag",
        "repeat_set": "Erneute Erinnerung, solange '{name}' überfällig ist: {interval}.",
        "usage_repeat": "So geht's: erinnerung <Aufgabe> <Abstand>, z.B. erinnerung Geschirr 1 Stunde",
        "reminder_time_set": "Erinnerungszeit für '{name}': {time}.",
        "usage_reminder_time": "So geht's: erinnerungszeit <Aufgabe> <HH:MM>, z.B. erinnerungszeit Geschirr 08:00",
        "quiet_hours_current": "Ruhezeit: {start}-{end} Uhr ({timezone}). In dieser Zeit verschickt der Bot keine Erinnerungen.",
        "quiet_hours_set": "Ruhezeit auf {start}-{end} Uhr ({timezone}) gestellt. In dieser Zeit verschickt der Bot keine Erinnerungen.",
        "usage_quiet_hours": "So geht's: admin ruhezeit 00:00-08:00",
        "auth_reminder_current": "Erinnerungen an die Signal-Verknüpfung sind {state}.",
        "auth_reminder_set_on": "Erinnerungen an die Signal-Verknüpfung sind jetzt aktiviert. Der Bot erinnert diese Gruppe etwa alle 25 Tage.",
        "auth_reminder_set_off": "Erinnerungen an die Signal-Verknüpfung sind jetzt deaktiviert.",
        "usage_auth_reminder": "So geht's: admin signal erinnerung an/aus",
        "disabled": "deaktiviert",
        "enabled": "aktiviert",
        "no_groups": "Noch keine Gruppen registriert.",
        "groups_header": "Registrierte Gruppen:",
        "current_language": "Aktuelle Sprache: Deutsch. Ändern mit: admin sprache englisch",
        "language_set_en": "Die Sprache für diesen Chat ist jetzt Englisch.",
        "language_set_de": "Die Sprache für diesen Chat ist jetzt Deutsch.",
        "language_usage": "So geht's: admin sprache deutsch oder admin sprache englisch",
        "current_timezone": "Aktuelle Zeitzone: {timezone}. Ändern mit: admin zeitzone Europe/Berlin",
        "timezone_set": "Zeitzone auf {timezone} gestellt. Erinnerungszeiten und Ruhezeit richten sich danach.",
        "timezone_usage": "So geht's: admin zeitzone Europe/Berlin (auch möglich: berlin, utc, london, paris, …)",
        "usage_done": "So geht's: erledigt <Aufgabe> [für <Person>]",
        "usage_undo_done": "So geht's: rückgängig <Aufgabe>",
        "undo_done_saved": "↩️ Letzte Erledigung von '{name}' rückgängig gemacht.",
        "undo_done_missing": "Für '{name}' gibt es keine Erledigung, die rückgängig gemacht werden kann.",
        "usage_add": "So geht's: aufgabe <Name> <Zeitplan>, z.B. aufgabe Geschirr jeden Tag · ohne Termin: todo Milch kaufen",
        "usage_task": (
            "So geht's: todo <Name>, z.B. todo Staubsauger kaufen\n"
            "Damit legst du eine offene Aufgabe ohne Zeitplan an, die du jederzeit abhaken kannst."
        ),
        "added": "✅ Aufgabe angelegt: {name} ({interval}).",
        "added_open_task": "✅ Offene Aufgabe angelegt: {name}. Ohne Zeitplan – abhaken jederzeit mit: erledigt {name}",
        "added_one_shot": (
            "✅ Einmalaufgabe angelegt: {name} ({interval}). Sie verschwindet, sobald sie erledigt ist. "
            "Zählt in der Statistik: {stats}. Löschen mit: lösche {name}"
        ),
        "usage_once": (
            "So geht's: einmal  (Schritt für Schritt)\n"
            "Oder: einmal <Name> [heute|morgen|<Wochentag>]\n"
            "Uhrzeit und Statistik fragt der Bot danach ab."
        ),
        "setup_once_schedule": (
            "Wann soll die einmalige Aufgabe '{name}' erledigt werden?\n"
            "Beispiele: heute, morgen, Freitag.\n"
            "Antworte mit dem Tag oder mit abbrechen."
        ),
        "setup_once_remind_time": (
            "Um wie viel Uhr soll der Bot an '{name}' erinnern (Ortszeit der Gruppe)?\n"
            "Beispiele: 08:00, 19:45 – oder egal (dann 08:00).\n"
            "Antworte mit einer Uhrzeit oder mit abbrechen."
        ),
        "setup_once_count_stats": (
            "Soll '{name}' in der Statistik zählen (unter Einmalaufgaben)?\n"
            "Antworte: ja, nein oder abbrechen"
        ),
        "once_short": "einmal",
        "once_stats_yes": "ja",
        "once_stats_no": "nein",
        "count_in_stats_label": "zählt in der Statistik",
        "count_in_stats_yes": "ja (Einmalaufgaben)",
        "count_in_stats_no": "nein",
        "already_exists": "Die Aufgabe '{name}' gibt es schon. Alle Aufgaben siehst du mit: liste",
        "could_not_add": "'{name}' konnte nicht angelegt werden. So geht's: aufgabe <Name> <Zeitplan> oder todo <Name>",
        "usage_delete": "So geht's: lösche <Aufgabe>",
        "deleted": "🗑️ Aufgabe gelöscht: {name}",
        "not_found": "⚠️ Die Aufgabe '{name}' wurde nicht gefunden.",
        "usage_change": "So geht's: umbenennen <alter Name> -> <neuer Name>",
        "no_history": "Es wurde noch keine Aufgabe erledigt.",
        "history_header": "🕐 Zuletzt erledigt:",
        "history_line": "{idx}. {name} – {sender}, {done_at}",
        "group_only": "Dieser Befehl funktioniert nur in Gruppen.",
        "reset_requested": (
            "⚠️ Zurücksetzen angefordert. Dabei werden alle Aufgaben und der gesamte Verlauf dieser Gruppe gelöscht.\n"
            "Zum Bestätigen innerhalb von 10 Minuten senden: admin zurücksetzen bestätigen {token}\n"
            "Zum Abbrechen senden: admin zurücksetzen abbrechen"
        ),
        "usage_reset_confirm": "So geht's: admin zurücksetzen bestätigen <Code>",
        "reset_failed": (
            "Zurücksetzen nicht bestätigt. Der Code muss stimmen, darf nicht abgelaufen sein "
            "und muss von derselben Person kommen, die das Zurücksetzen angefordert hat."
        ),
        "reset_done": "✅ Aufgaben, Verlauf und Erinnerungen dieser Gruppe wurden zurückgesetzt.",
        "did_you_mean": "Meintest du: {command}?",
        "unexpected_error": "⚠️ Beim Verarbeiten deines Befehls ist etwas schiefgelaufen.",
        "mark_done_missing": (
            "⚠️ Die Aufgabe '{name}' wurde nicht gefunden. Leg sie zuerst mit aufgabe oder todo an. "
            "Alle Aufgaben siehst du mit: liste"
        ),
        "mark_done_saved": "✅ Erledigt: {name} – von {sender} ({done_at}).\nRückgängig: rückgängig {name}",
        "mark_done_one_shot": "✅ {name} erledigt von {sender} ({done_at}) und von der Liste entfernt.\nZählt in der Statistik unter Einmalaufgaben.",
        "mark_done_one_shot_no_stats": "✅ {name} erledigt von {sender} ({done_at}) und von der Liste entfernt.\nZählt nicht in der Statistik.",
        "done_member_not_found": (
            "⚠️ Ich kenne kein Gruppenmitglied namens '{name}'. "
            "Die Person muss zuerst ihren Namen festlegen mit: name <Name>"
        ),
        "ask_display_name": (
            "Unter welchem Namen soll ich deine erledigten Aufgaben anzeigen?\n"
            "Antworte mit deinem Namen oder mit abbrechen."
        ),
        "display_name_invalid": "Bitte 2-24 Zeichen verwenden: Buchstaben, Zahlen, Leerzeichen oder Bindestriche.",
        "display_name_saved": "👤 Dein Name ist jetzt: {name}",
        "usage_name": "So geht's: name <dein Name>",
        "renamed": "✏️ '{old}' heißt jetzt '{new}'.",
        "new_name_empty": "Der neue Name darf nicht leer sein.",
        "rename_missing": "Die Aufgabe '{name}' gibt es nicht.",
        "rename_exists": "Die Aufgabe '{name}' gibt es schon.",
        "reminder": (
            "🔔 Erinnerung: '{name}' ist fällig.\n"
            "Erledigt? Dann schreib: erledigt {name}\n"
            "💡 Alle Befehle: hilfe"
        ),
        "reminder_no_confirmation": (
            "🔔 Erinnerung: '{name}' ist fällig.\n"
            "💡 Alle Befehle: hilfe"
        ),
        "auth_reminder": (
            "🔗 Hinweis zur Signal-Verknüpfung: Verknüpfte Geräte können nach längerer Inaktivität getrennt werden.\n"
            "Falls der Bot nicht mehr antwortet, muss er neu verknüpft werden: http://127.0.0.1:8080/v1/qrcodelink?device_name=signal-api"
        ),
        "vacation_help": (
            "🏖️ Urlaubsmodus:\n"
            "- urlaub – Schritt für Schritt (ab jetzt oder in X Tagen, dann die Dauer)\n"
            "- urlaub 14 tage – ab sofort für 14 Tage\n"
            "- urlaub in 3 tagen für 14 tage – im Voraus planen\n"
            "- urlaub status – deinen Urlaub anzeigen\n"
            "- urlaub abbrechen – geplanten oder laufenden Urlaub beenden\n"
            "- urlaub aufgabe – Vorbereitungsaufgabe hinzufügen\n"
            "- urlaub aufgabe Kühlschrank leeren\n"
            "- urlaub liste – Vorbereitungsaufgaben anzeigen\n"
            "- urlaub lösche <Name>\n"
            "- urlaub erledigt <Name> – Vorbereitungsaufgabe abhaken\n"
            "- urlaub überspringen – restliche Vorbereitungsaufgaben überspringen\n"
            "Während des Urlaubs gibt es keine Aufgaben-Erinnerungen. Danach läuft der normale Zeitplan weiter – "
            "eine wöchentliche Freitagsaufgabe meldet sich z.B. erst am ersten Freitag nach dem Urlaub, "
            "nicht am Tag der Rückkehr."
        ),
        "vacation_setup_when": (
            "🏖️ Urlaub – wann geht es los?\n"
            "Antworte: jetzt, in 3 tagen oder abbrechen"
        ),
        "vacation_setup_duration": (
            "🏖️ Wie lange dauert der Urlaub?\n"
            "Antworte mit einer Dauer, z.B. 14 tage oder 2 wochen – oder mit abbrechen"
        ),
        "vacation_setup_chore_name": (
            "🏖️ Wie heißt die Vorbereitungsaufgabe?\n"
            "Antworte mit dem Namen oder mit abbrechen"
        ),
        "vacation_usage": "🏖️ Probier: urlaub, urlaub 14 tage oder urlaub hilfe",
        "vacation_duration_invalid": "Diese Dauer verstehe ich nicht. Beispiel: 14 tage oder 2 wochen",
        "vacation_when_invalid": "Bitte antworte mit jetzt, in 3 tagen oder abbrechen",
        "vacation_chore_added": "Vorbereitungsaufgabe hinzugefügt: {name}",
        "vacation_chore_exists": "Die Vorbereitungsaufgabe '{name}' gibt es schon.",
        "vacation_chore_deleted": "Vorbereitungsaufgabe gelöscht: {name}",
        "vacation_chore_not_found": "Vorbereitungsaufgabe nicht gefunden: {name}",
        "vacation_chore_list_empty": "Noch keine Vorbereitungsaufgaben. Hinzufügen mit: urlaub aufgabe",
        "vacation_chore_list": "Vorbereitungsaufgaben:\n{items}",
        "vacation_none": "Du hast keinen geplanten oder laufenden Urlaub.",
        "vacation_cancelled": "Urlaub abgebrochen. Die Aufgaben laufen wie gewohnt weiter.",
        "vacation_nothing_to_cancel": "Du hast keinen Urlaub, der abgebrochen werden kann.",
        "vacation_prep_done": "Vorbereitungsaufgabe erledigt: {name}",
        "vacation_prep_not_found": "Vorbereitungsaufgabe nicht gefunden oder der Urlaub ist nicht in der Vorbereitung: {name}",
        "vacation_prep_skipped": "Vorbereitung übersprungen. Der Urlaub läuft, die Erinnerungen sind pausiert.",
        "vacation_prep_skip_unavailable": "Es gibt keine Vorbereitung, die übersprungen werden kann.",
        "vacation_scheduled": (
            "🏖️ Urlaub geplant.\n"
            "Beginn: {starts}\n"
            "Ende: {ends}\n"
            "Dauer: {duration}\n"
            "Ab Beginn sind die Erinnerungen pausiert."
        ),
        "vacation_started_active": (
            "🏖️ Der Urlaub hat begonnen.\n"
            "Ende: {ends}\n"
            "Dauer: {duration}\n"
            "Bis dahin gibt es keine Aufgaben-Erinnerungen. Danach läuft der normale Zeitplan weiter."
        ),
        "vacation_started_prep": (
            "🏖️ Der Urlaub beginnt – erledige vorher noch diese Aufgaben:\n"
            "{items}\n\n"
            "Abhaken mit: urlaub erledigt <Name>\n"
            "Oder alle überspringen mit: urlaub überspringen\n\n"
            "Bis zum Ende des Urlaubs sind die Aufgaben-Erinnerungen pausiert."
        ),
        "vacation_status_scheduled": (
            "🏖️ Geplanter Urlaub\n"
            "Beginn: {starts}\n"
            "Ende: {ends}\n"
            "Dauer: {duration}"
        ),
        "vacation_status_prep": (
            "🏖️ Urlaub (Vorbereitung)\n"
            "Ende: {ends}\n"
            "Noch offen:\n{items}"
        ),
        "vacation_status_active": (
            "🏖️ Urlaub läuft\n"
            "Ende: {ends}\n"
            "Bis dahin keine Aufgaben-Erinnerungen, danach läuft der normale Zeitplan weiter."
        ),
        "vacation_ended_notice": (
            "🏖️ Der Urlaub von {name} ist vorbei. Die Aufgaben-Erinnerungen laufen wieder nach dem normalen Zeitplan."
        ),
        "vacation_started_notice": (
            "🏖️ Der Urlaub von {name} hat begonnen. Bis {ends} gibt es keine Erinnerungen, "
            "danach läuft der normale Zeitplan weiter."
        ),
        "vacation_started_prep_notice": (
            "🏖️ Der Urlaub von {name} hat begonnen. Vorher noch zu erledigen:\n{items}"
        ),
    },
}


def text_for(storage: Storage, scope_id: str, key: str, **kwargs: object) -> str:
    language = storage.get_language(scope_id)
    template = TEXT.get(language, TEXT["en"])[key]
    return template.format(**kwargs)


def format_reminder(storage: Storage, scope_id: str, chore_name: str, requires_confirmation: bool = True) -> str:
    key = "reminder" if requires_confirmation else "reminder_no_confirmation"
    return text_for(storage, scope_id, key, name=chore_name)


def _text(language: str, key: str, **kwargs: object) -> str:
    template = TEXT.get(language, TEXT["en"])[key]
    return template.format(**kwargs)


def _with_usage_tip(
    storage: Storage,
    scope_id: str,
    sender: str,
    language: str,
    command_key: str,
    reply: str,
) -> str:
    count = storage.bump_command_usage(scope_id, sender, command_key)
    tip = USAGE_TIPS.get(language, USAGE_TIPS["en"]).get(command_key)
    return append_usage_tip(reply, tip, count)


def _strip_chart_suffix(command_lowered: str) -> tuple[str, bool]:
    base, wants_chart, _ = parse_chart_command(command_lowered)
    return base, wants_chart


def _stats_reply(reply: str, attachments: list[str] | None = None) -> str | dict:
    if attachments:
        return {"reply": reply, "attachments": attachments}
    return reply


def _stats_time(storage: Storage, scope_id: str, value: str | None, language: str) -> str:
    if not value:
        return "never" if language == "en" else "nie"
    return _format_list_timestamp(value, storage.get_timezone(scope_id))


def _format_user_stats(storage: Storage, scope_id: str, sender: str, language: str) -> str:
    stats = storage.user_stats(scope_id, sender)
    if stats["total_completions"] == 0:
        return _text(language, "user_stats_empty")
    favorite = _stats_display_name(stats["top_chore"]["name"], language) if stats["top_chore"] else ("n/a" if language == "en" else "k.A.")
    last_done = _stats_time(storage, scope_id, stats["last_done_at"], language)
    summary = _text(
        language,
        "user_stats_line",
        total=stats["total_completions"],
        unique=stats["unique_chores"],
        favorite=favorite,
        last_done=last_done,
    )
    by_chore_lines = [
        _text(language, "user_stats_by_chore_line", name=_stats_display_name(row["name"], language), count=row["count"])
        for row in stats["by_chore"]
    ]
    return mobile_blocks(
        _text(language, "user_stats_header"),
        summary,
        _text(language, "user_stats_by_chore_header"),
        "\n".join(by_chore_lines),
    )


def _format_group_stats(storage: Storage, scope_id: str, language: str) -> str:
    summary = storage.action_stats(scope_id)
    rows = storage.task_stats(scope_id)
    if summary["chore_count"] == 0 and summary["done_count"] == 0:
        return _text(language, "task_stats_empty")
    blocks = [
        _text(language, "group_stats_header"),
        _text(
            language,
            "group_stats_summary",
            chore_count=summary["chore_count"],
            done_count=summary["done_count"],
        ),
        _text(language, "group_stats_users_header"),
    ]
    user_totals = storage.group_completion_totals(scope_id)
    if user_totals:
        blocks.append(
            "\n".join(
                _text(
                    language,
                    "group_stats_users_line",
                    name=storage.display_name(scope_id, row["sender"]),
                    count=row["count"],
                )
                for row in user_totals
            )
        )
    else:
        blocks.append(_text(language, "group_stats_users_none"))
    blocks.append(_text(language, "group_stats_chores_header"))
    chore_blocks: list[str] = []
    for row in rows:
        who = (
            storage.display_name(scope_id, row["last_done_by"])
            if row["last_done_by"]
            else ("nobody" if language == "en" else "niemand")
        )
        last_done = _stats_time(storage, scope_id, row["last_done_at"], language)
        lines = [
            _text(
                language,
                "task_stats_line",
                name=_stats_display_name(row["name"], language),
                count=row["completions"],
                last_done=last_done,
                who=who,
            )
        ]
        if row["by_person"]:
            parts = ", ".join(
                f"{storage.display_name(scope_id, person['sender'])}: {person['count']}x"
                for person in row["by_person"]
            )
            lines.append(f"   {parts}")
        elif int(row["completions"] or 0) == 0:
            lines.append(_text(language, "task_stats_by_person_none"))
        chore_blocks.append("\n".join(lines))
    blocks.append("\n\n".join(chore_blocks))
    return mobile_blocks(*blocks)


def _format_group_chore_stats(storage: Storage, scope_id: str, language: str, chore_name: str) -> str:
    row = next(
        (
            item
            for item in storage.task_stats(scope_id)
            if _matches_stats_chore(item["name"], chore_name, language)
        ),
        None,
    )
    if row is None:
        return _text(language, "not_found", name=chore_name)
    blocks = [
        _text(language, "group_chore_stats_header", name=_stats_display_name(row["name"], language)),
        _text(language, "group_chore_stats_summary", count=row["completions"]),
        _text(language, "group_chore_stats_users_header"),
    ]
    if row["by_person"]:
        blocks.append(
            "\n".join(
                _text(
                    language,
                    "group_chore_stats_user_line",
                    name=storage.display_name(scope_id, person["sender"]),
                    count=person["count"],
                )
                for person in row["by_person"]
            )
        )
    else:
        blocks.append(_text(language, "group_chore_stats_none"))
    return mobile_blocks(*blocks)


def _format_user_chore_stats(storage: Storage, scope_id: str, sender: str, language: str, chore_name: str) -> str:
    if _is_one_shot_stats_query(chore_name, language):
        stats = storage.user_stats(scope_id, sender)
        match = next((row for row in stats["by_chore"] if row["name"] == ONE_SHOT_STATS_KEY), None)
        label = one_shot_stats_label(language)
        if match is None:
            return _text(language, "user_chore_stats_none", name=label)
        return mobile_blocks(
            _text(language, "user_chore_stats_header", name=label),
            _text(language, "user_chore_stats_line", count=match["count"], last_done=_stats_time(storage, scope_id, stats["last_done_at"], language)),
        )
    canonical = storage._find_chore_case_insensitive(scope_id, chore_name)
    if canonical is None:
        return _text(language, "not_found", name=chore_name)
    stats = storage.user_stats(scope_id, sender)
    match = next((row for row in stats["by_chore"] if row["name"].lower() == canonical["name"].lower()), None)
    if match is None:
        return _text(language, "user_chore_stats_none", name=canonical["name"])
    last_done = _stats_time(storage, scope_id, stats["last_done_at"], language)
    # Prefer last done for this chore if available from task_stats
    task_row = next((item for item in storage.task_stats(scope_id) if item["name"] == canonical["name"]), None)
    if task_row and task_row.get("last_done_by") == sender and task_row.get("last_done_at"):
        last_done = _stats_time(storage, scope_id, task_row["last_done_at"], language)
    return mobile_blocks(
        _text(language, "user_chore_stats_header", name=canonical["name"]),
        _text(language, "user_chore_stats_line", count=match["count"], last_done=last_done),
    )


def _parse_stats_command(command_lowered: str) -> dict | None:
    user_prefixes = (
        "my stats",
        "meine statistik",
        "stats me",
        "statistik ich",
        "personal stats",
        "persönliche statistik",
        "persoenliche statistik",
    )
    group_prefixes = (
        "group stats",
        "gruppen statistik",
        "stats group",
        "statistik gruppe",
        "task stats",
        "chore stats",
        "aufgaben statistik",
        "aufgabe statistik",
    )
    scope = None
    prefix = None
    for candidate in user_prefixes:
        if command_lowered == candidate or command_lowered.startswith(candidate + " "):
            scope, prefix = "user", candidate
            break
    if scope is None:
        for candidate in group_prefixes:
            if command_lowered == candidate or command_lowered.startswith(candidate + " "):
                scope, prefix = "group", candidate
                break
    if scope is None:
        return None

    base, wants_chart, chart_kind = parse_chart_command(command_lowered)
    if not base.startswith(prefix):
        return None
    filter_rest = base[len(prefix) :].strip()
    chore_name = None
    for marker in ("aufgabe ", "chore ", "task "):
        if filter_rest.startswith(marker):
            chore_name = filter_rest[len(marker) :].strip()
            filter_rest = ""
            break
    if filter_rest:
        tokens = filter_rest.split()
        if len(tokens) == 1 and tokens[0] in group_chart_kinds(None):
            wants_chart = True
            chart_kind = tokens[0]
            filter_rest = ""
        else:
            return {"invalid": True, "scope": scope}
    if chore_name == "":
        return {"invalid": True, "scope": scope, "needs_chore": True}
    return {
        "scope": scope,
        "chore_name": chore_name,
        "wants_chart": wants_chart,
        "chart_kind": chart_kind,
    }


def _format_task_stats(storage: Storage, scope_id: str, language: str) -> str:
    return _format_group_stats(storage, scope_id, language)


def _chore_setup_prompt(storage: Storage, scope_id: str, sender: str, language: str) -> str:
    pending = storage.get_pending_chore_setup(scope_id, sender)
    if pending is None:
        return _text(language, "cancelled")
    step = pending["step"]
    chore_name = pending["name"]
    if step == "name":
        return _text(language, "setup_chore_name")
    if step == "schedule":
        if _pending_is_one_shot(pending):
            return _text(language, "setup_once_schedule", name=chore_name)
        return _text(language, "setup_chore_schedule", name=chore_name)
    if step == "remind_time":
        return _text(
            language,
            "setup_once_remind_time" if _pending_is_one_shot(pending) else "setup_chore_remind_time",
            name=chore_name,
        )
    if step == "count_stats":
        return _text(language, "setup_once_count_stats", name=chore_name)
    if step == "confirmation":
        return _text(language, "setup_chore_confirmation", name=chore_name)
    if step == "repeat":
        schedule = schedule_from_storage(pending["reminder_schedule"])
        repeat_schedule = _default_repeat_schedule(schedule)
        return _text(
            language,
            "setup_chore_repeat",
            name=chore_name,
            default_interval=format_schedule_delay(repeat_schedule, language),
        )
    return _text(language, "setup_chore_name")


def _edit_continue_prompt(storage: Storage, scope_id: str, sender: str, language: str) -> str:
    pending = storage.get_pending_chore_edit(scope_id, sender)
    if pending is None:
        return _text(language, "cancelled")
    chore_name = pending["chore_name"]
    field = pending["field"]
    if not field:
        return _text(language, "edit_options", name=chore_name)
    if field == "name":
        return _text(language, "edit_new_name", name=chore_name)
    if field == "schedule":
        return _text(language, "edit_new_schedule", name=chore_name)
    if field == "confirmation":
        return _text(language, "edit_new_confirmation", name=chore_name)
    if field == "remind_time":
        return _text(language, "edit_new_remind_time", name=chore_name)
    if field == "repeat":
        return _text(language, "edit_new_repeat", name=chore_name)
    return _text(language, "edit_confirm_delete", name=chore_name)


def _default_repeat_schedule(schedule: dict | None) -> dict | None:
    if schedule is None or schedule["type"] == "none":
        return None
    if schedule["type"] == "once":
        if schedule.get("unit") in {"minutes", "hours"}:
            return {"type": "interval", "value": 5, "unit": "minutes"}
        return {"type": "interval", "value": 8, "unit": "hours"}
    if schedule["type"] == "weekday":
        return {"type": "interval", "value": 8, "unit": "hours"}
    if schedule["type"] != "interval":
        return None

    unit = schedule["unit"]
    value = schedule["value"]
    if unit in {"minutes", "hours"}:
        return {"type": "interval", "value": 5, "unit": "minutes"}
    if unit == "days" and value < 7:
        return {"type": "interval", "value": 1, "unit": "hours"}
    if unit == "days" and value >= 7:
        return {"type": "interval", "value": 8, "unit": "hours"}
    if unit == "weeks":
        return {"type": "interval", "value": 8, "unit": "hours"}
    return {"type": "interval", "value": 8, "unit": "hours"}


def _parse_repeat_or_default(text: str, base_schedule: dict | None) -> dict | None:
    cleaned = text.strip().lower()
    if cleaned in {"default", "standard", "recommended", "vorschlag", "standardwert"}:
        return _default_repeat_schedule(base_schedule)
    return parse_schedule(text)


def _format_time(minutes: int) -> str:
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def _parse_time_token(token: str) -> int | None:
    cleaned = token.strip().replace(".", ":")
    if not cleaned:
        return None
    if ":" in cleaned:
        hour_text, minute_text = cleaned.split(":", 1)
    elif cleaned.isdigit() and len(cleaned) in {1, 2}:
        hour_text, minute_text = cleaned, "0"
    elif cleaned.isdigit() and len(cleaned) == 4:
        hour_text, minute_text = cleaned[:2], cleaned[2:]
    else:
        return None
    if not hour_text.isdigit() or not minute_text.isdigit():
        return None
    hours = int(hour_text)
    minutes = int(minute_text)
    if hours == 24 and minutes == 0:
        return 0
    if not 0 <= hours < 24 or not 0 <= minutes < 60:
        return None
    return hours * 60 + minutes


def _format_bot_options(language: str) -> str:
    bots = load_bot_registry()
    lines = []
    for idx, (bot_id, name) in enumerate(bots.items(), start=1):
        lines.append(f"{idx}. {name} (bot {bot_id})")
    return "\n".join(lines)


def _parse_bot_command(text: str) -> str | None:
    lowered = text.strip().lower()
    if lowered in {"bot", "bot help", "bot hilfe"}:
        return ""
    if not lowered.startswith("bot "):
        return None
    bot_id = text.strip()[4:].strip()
    if not bot_id:
        return ""
    bots = load_bot_registry()
    if bot_id in bots:
        return bot_id
    if bot_id.isdigit():
        keys = list(bots.keys())
        index = int(bot_id) - 1
        if 0 <= index < len(keys):
            return keys[index]
    return "invalid"


def _complete_bot_setup(storage: Storage, scope_id: str, sender: str, language: str, bot_id: str) -> list[str]:
    bots = load_bot_registry()
    name = bots[bot_id]
    storage.set_bot_id(scope_id, bot_id)
    if not storage.is_admin(scope_id, sender):
        storage.add_admin(scope_id, sender)
    storage.log_action(scope_id, sender, "set_bot", details=bot_id)
    return [
        _text(language, "setup_bot_set", name=name, bot_id=bot_id),
        _text(language, "setup_complete"),
    ]


def _parse_reminder_time_command(text: str) -> tuple[str, int | None] | str | None:
    lowered = text.strip().lower()
    prefixes = ("reminder time ", "remind time ", "erinnerungszeit ")
    for prefix in prefixes:
        if lowered.startswith(prefix):
            payload = text[len(prefix):].strip()
            if not payload or " " not in payload:
                return "invalid"
            chore_name, time_text = payload.rsplit(" ", 1)
            chore_name = chore_name.strip()
            if not chore_name:
                return "invalid"
            parsed = parse_reminder_time_answer(time_text)
            if parsed == "invalid":
                return "invalid"
            return chore_name, parsed
    return None


def _finalize_chore_creation(
    storage: Storage,
    scope_id: str,
    sender: str,
    language: str,
    chore_name: str,
    schedule: dict,
    reminder_at_minutes: int | None,
    requires_confirmation: bool,
    repeat_schedule: dict | None = None,
    count_in_stats: bool = True,
) -> str:
    if not storage.add_chore(
        scope_id,
        chore_name,
        schedule,
        reminder_at_minutes,
        count_in_stats=count_in_stats,
    ):
        existing_names = [row["name"].lower() for row in storage.list_chores(scope_id)]
        if chore_name.lower() in existing_names:
            return _text(language, "already_exists", name=chore_name)
        return _text(language, "could_not_add", name=chore_name)
    storage.set_chore_confirmation(scope_id, chore_name, requires_confirmation)
    if repeat_schedule is not None:
        storage.set_chore_repeat_reminder(scope_id, chore_name, repeat_schedule)
    storage.log_action(scope_id, sender, "add_chore", chore_name, humanize_schedule(schedule, language))
    storage.log_action(
        scope_id,
        sender,
        "set_confirmation",
        chore_name,
        "on" if requires_confirmation else "off",
    )
    if repeat_schedule is not None:
        storage.log_action(
            scope_id,
            sender,
            "set_repeat_reminder",
            chore_name,
            humanize_schedule(repeat_schedule, language),
        )
    if schedule.get("type") == "none":
        return _text(language, "added_open_task", name=chore_name, interval=format_schedule_frequency(schedule, language))
    if is_one_shot_schedule(schedule):
        return _text(
            language,
            "added_one_shot",
            name=chore_name,
            interval=format_schedule_frequency(schedule, language),
            stats=_text(language, "once_stats_yes" if count_in_stats else "once_stats_no"),
        )
    return _text(
        language,
        "added",
        name=chore_name,
        interval=format_schedule_frequency(schedule, language),
    )


def _parse_quiet_hours_command(text: str) -> tuple[str, int | None, int | None] | None:
    lowered = text.strip().lower()
    prefixes = ("quiet hours", "quiet", "ruhezeit", "erinnerungspause")
    matched_prefix = ""
    for prefix in prefixes:
        if lowered == prefix or lowered.startswith(prefix + " "):
            matched_prefix = prefix
            break
    if not matched_prefix:
        return None
    payload = text[len(matched_prefix):].strip()
    if not payload:
        return "show", None, None
    if "-" in payload:
        parts = [part.strip() for part in payload.split("-", 1)]
    else:
        parts = payload.split()
    if len(parts) != 2:
        return "invalid", None, None
    start_minutes = _parse_time_token(parts[0])
    end_minutes = _parse_time_token(parts[1])
    if start_minutes is None or end_minutes is None:
        return "invalid", None, None
    return "set", start_minutes, end_minutes


def _parse_auth_reminder_command(text: str) -> str | None:
    lowered = text.strip().lower()
    prefixes = (
        "auth reminder",
        "reauth reminder",
        "signal auth reminder",
        "signal link reminder",
        "auth erinnerung",
        "reauth erinnerung",
        "signal erinnerung",
        "signal-link-erinnerung",
        "verknuepfungs-erinnerung",
        "verknüpfungs-erinnerung",
    )
    matched_prefix = ""
    for prefix in prefixes:
        if lowered == prefix or lowered.startswith(prefix + " "):
            matched_prefix = prefix
            break
    if not matched_prefix:
        return None
    payload = lowered[len(matched_prefix):].strip()
    if not payload:
        return "show"
    if payload in {"on", "yes", "true", "enable", "enabled", "an", "ja", "aktivieren", "aktiviert"}:
        return "on"
    if payload in {"off", "no", "false", "disable", "disabled", "aus", "nein", "deaktivieren", "deaktiviert"}:
        return "off"
    return "invalid"


def _language_from_command(text: str) -> str | None:
    cleaned = text.strip().lower()
    if cleaned in {"language", "sprache"}:
        return ""
    if cleaned in {"en", "eng", "english", "englisch"}:
        return "en"
    if cleaned in {"de", "ger", "german", "deutsch"}:
        return "de"
    parts = cleaned.replace("=", " ").split()
    if not parts or parts[0] not in {"language", "lang", "sprache"}:
        return None
    if len(parts) < 2:
        return ""
    requested = parts[-1]
    if requested in {"en", "eng", "english", "englisch"}:
        return "en"
    if requested in {"de", "ger", "german", "deutsch"}:
        return "de"
    return "invalid"


def _timezone_from_command(text: str) -> str | None:
    cleaned = text.strip()
    lowered = cleaned.lower()
    if lowered in {"timezone", "time zone", "zeitzone", "uhrzeit zone", "zeit zone"}:
        return ""
    prefixes = ("timezone ", "time zone ", "zeitzone ", "uhrzeit zone ", "zeit zone ")
    for prefix in prefixes:
        if lowered.startswith(prefix):
            value = cleaned[len(prefix) :].strip()
            if not value:
                return ""
            normalized = normalize_timezone_name(value)
            if normalized is None:
                return "invalid"
            return normalized
    return None


def _message_language_hint(text: str) -> str | None:
    lowered = text.strip().lower()
    german_tokens = {
        "hilfe",
        "aufgabe",
        "aufgaben",
        "bearbeite",
        "aendere",
        "ändere",
        "sprache",
        "deutsch",
    }
    if any(token in lowered.split() for token in german_tokens):
        return "de"
    if lowered in {"admin hilfe", "aufgabe hilfe", "bearbeite hilfe"}:
        return "de"
    return None


def _help_language(storage: Storage, scope_id: str, text: str, current_language: str) -> str:
    if storage.has_language(scope_id):
        return current_language
    return _message_language_hint(text) or current_language


def _admin_action(text: str) -> tuple[bool, str]:
    parts = text.strip().split(maxsplit=1)
    if not parts or parts[0].lower() != "admin":
        return False, ""
    action = parts[1].strip() if len(parts) == 2 else "help"
    return True, action


def _confirmation_answer(text: str) -> bool | None:
    cleaned = text.strip().lower()
    if cleaned in {"yes", "y", "ja", "j", "ok", "okay", "confirm", "bestaetigen", "bestätigen"}:
        return True
    if cleaned in {"no", "n", "nein", "cancel", "abbrechen", "stop"}:
        return False
    return None


def _is_cancel(text: str) -> bool:
    return text.strip().lower() in {"cancel", "abbrechen", "stop"}


def _stats_display_name(name: str, language: str) -> str:
    if name == ONE_SHOT_STATS_KEY:
        return one_shot_stats_label(language)
    return name


def _is_one_shot_stats_query(chore_name: str, language: str) -> bool:
    cleaned = chore_name.strip().lower()
    return cleaned in {
        ONE_SHOT_STATS_KEY.lower(),
        one_shot_stats_label("en").lower(),
        one_shot_stats_label("de").lower(),
        "einmalaufgaben",
        "einmalaufgabe",
        "one-time",
        "one time",
        "onetime",
        "once",
        "einmal",
    }


def _matches_stats_chore(row_name: str, query: str, language: str) -> bool:
    if row_name.lower() == query.lower():
        return True
    if row_name == ONE_SHOT_STATS_KEY:
        return _is_one_shot_stats_query(query, language)
    return False


def _labeled_chore_rows(rows: list[dict], language: str) -> list[dict]:
    labeled = []
    for row in rows:
        item = dict(row)
        item["name"] = _stats_display_name(item.get("name", ""), language)
        labeled.append(item)
    return labeled


def _pending_is_one_shot(pending) -> bool:
    try:
        return int(pending["one_shot"] or 0) == 1
    except (KeyError, IndexError, TypeError):
        return False


def _as_once_schedule(schedule: dict | None, raw: str = "") -> dict | None:
    cleaned = raw.strip().lower()
    if cleaned in {"today", "heute"}:
        return {"type": "once", "when": "today"}
    if cleaned in {"tomorrow", "morgen"}:
        return {"type": "once", "when": "tomorrow"}
    if schedule is None:
        return None
    if schedule["type"] == "once":
        return schedule
    if schedule["type"] == "weekday":
        return {"type": "once", "weekday": schedule["weekday"]}
    if schedule["type"] == "interval":
        return {"type": "once", "value": schedule["value"], "unit": schedule["unit"]}
    return None


def _split_trailing_reminder_time(payload: str) -> tuple[str, int | None]:
    parts = payload.rsplit(maxsplit=1)
    if len(parts) != 2:
        return payload, None
    token = parts[1].strip().replace(".", ":")
    if ":" not in token and not (token.isdigit() and len(token) == 4):
        return payload, None
    parsed = parse_reminder_time_answer(parts[1])
    if not isinstance(parsed, int):
        return payload, None
    return parts[0].strip(), parsed


def _parse_once_name_and_when(payload: str) -> tuple[str, dict | None]:
    if not payload.strip():
        return "", None
    name, schedule = _parse_name_and_schedule(payload)
    if schedule is not None:
        wrapped = _as_once_schedule(schedule)
        if wrapped is None:
            return name, None
        return name, wrapped
    parts = payload.split()
    if len(parts) >= 2:
        maybe_when = parts[-1]
        wrapped = _as_once_schedule(parse_schedule(maybe_when), maybe_when)
        if wrapped is not None:
            return " ".join(parts[:-1]).strip(), wrapped
    return payload.strip(), {"type": "once", "when": "today"}


def _parse_once_command(text: str) -> tuple[str, dict | None, int | None] | str | None:
    lowered = text.strip().lower()
    if lowered in {"once", "one-time", "onetime", "einmal", "einmalig"}:
        return "guided"
    payload = None
    for prefix in ("once ", "one-time ", "onetime ", "one time ", "einmal ", "einmalig "):
        if lowered.startswith(prefix):
            payload = text.strip()[len(prefix) :].strip()
            break
    if payload is None:
        return None
    if not payload:
        return "guided"
    rest, reminder_at = _split_trailing_reminder_time(payload)
    name, schedule = _parse_once_name_and_when(rest)
    return name, schedule, reminder_at


def _parse_add_command(text: str) -> tuple[str, dict | None, int | None] | None:
    lowered = text.lower()
    prefixes = (
        ("add chore ", 10),
        ("new chore ", 10),
        ("neue aufgabe ", 13),
        ("add ", 4),
        ("aufgabe ", 8),
    )
    for prefix, length in prefixes:
        if lowered.startswith(prefix):
            payload = text[length:].strip()
            rest, reminder_at = _split_trailing_reminder_time(payload)
            name, schedule = _parse_name_and_schedule(rest)
            return name, schedule, reminder_at
    return None


def _add_command_payload(text: str) -> str:
    return _strip_prefixed_value(
        text,
        ("add chore ", "new chore ", "add ", "aufgabe ", "neue aufgabe "),
    )


def _parse_name_and_schedule(payload: str) -> tuple[str, dict | None]:
    lowered = payload.lower()
    marker_idx = -1
    for marker in (
        " every ",
        " alle ",
        " jede ",
        " jeden ",
        " jedes ",
        " einmal ",
        " einmalig ",
        " once ",
        " one-time ",
        " one time ",
    ):
        current_idx = lowered.rfind(marker)
        if current_idx > marker_idx:
            marker_idx = current_idx
    if marker_idx != -1:
        chore_name = payload[:marker_idx].strip()
        schedule_text = payload[marker_idx + 1:].strip()
    else:
        for suffix in (
            " no reminder",
            " no schedule",
            " without reminder",
            " without schedule",
            " open",
            " open task",
            " todo",
            " keine erinnerung",
            " kein plan",
            " kein zeitplan",
            " ohne erinnerung",
            " ohne plan",
            " ohne zeitplan",
            " offen",
        ):
            if lowered.endswith(suffix):
                return payload[: -len(suffix)].strip(), parse_schedule(suffix.strip())
        parts = payload.split()
        if len(parts) < 2:
            return "", None
        if len(parts) >= 3 and parts[-2].isdigit():
            chore_name = " ".join(parts[:-2]).strip()
            schedule_text = " ".join(parts[-2:]).strip()
        else:
            chore_name = " ".join(parts[:-1]).strip()
            schedule_text = parts[-1].strip()
    return chore_name, parse_schedule(schedule_text)


def _parse_open_task_command(text: str) -> str | None:
    lowered = text.strip().lower()
    for prefix in (
        "task ",
        "todo ",
        "open task ",
        "open ",
        "offen ",
        "offene aufgabe ",
    ):
        if lowered.startswith(prefix):
            return text.strip()[len(prefix) :].strip()
    return None


def _parse_confirmation_command(text: str) -> tuple[str, bool] | None:
    payload = _strip_prefixed_value(
        text,
        ("confirmation ", "confirm ", "bestaetigung ", "bestätigung "),
    )
    if not payload:
        return None
    parts = payload.rsplit(maxsplit=1)
    if len(parts) != 2:
        return "", False
    chore_name, state = parts[0].strip(), parts[1].strip().lower()
    if state in {"on", "yes", "true", "an", "ja"}:
        return chore_name, True
    if state in {"off", "no", "false", "aus", "nein"}:
        return chore_name, False
    return "", False


def _parse_repeat_command(text: str) -> tuple[str, dict | None] | None:
    payload = _strip_prefixed_value(
        text,
        ("reminder ", "repeat ", "remind ", "erinnerung ", "wiederholen "),
    )
    if not payload:
        return None
    return _parse_name_and_schedule(payload)


def _parse_schedule_command(text: str) -> tuple[str, dict | None] | None:
    payload = _strip_prefixed_value(
        text,
        ("schedule ", "due ", "faelligkeit ", "fälligkeit ", "zeitplan ", "plan "),
    )
    if not payload:
        return None
    return _parse_name_and_schedule(payload)


def _edit_command_name(text: str) -> str:
    return _strip_prefixed_value(
        text,
        ("edit ", "bearbeite ", "aendere ", "ändere "),
    )


def _canonical_chore_name(storage: Storage, scope_id: str, chore_name: str) -> str | None:
    normalized = chore_name.strip().lower()
    for row in storage.list_chores(scope_id):
        if row["name"].lower() == normalized:
            return row["name"]
    return None


def _edit_field_from_text(text: str) -> str | None:
    cleaned = text.strip().lower()
    if cleaned in {"name", "rename", "umbenennen"}:
        return "name"
    if cleaned in {"schedule", "due", "faelligkeit", "fälligkeit", "zeitplan", "plan"}:
        return "schedule"
    if cleaned in {"confirmation", "confirm", "done confirmation", "bestaetigung", "bestätigung", "erledigt-bestaetigung", "erledigt-bestätigung"}:
        return "confirmation"
    if cleaned in {
        "reminder time",
        "remind time",
        "reminder-time",
        "erinnerungszeit",
        "uhrzeit",
    }:
        return "remind_time"
    if cleaned in {
        "reminder",
        "repeat",
        "overdue reminder",
        "erneute erinnerung",
        "erinnerung",
        "wiederholung",
        "wiederholung bei ueberfaelligkeit",
        "wiederholung bei überfälligkeit",
        "ueberfaelligkeit",
        "überfälligkeit",
    }:
        return "repeat"
    if cleaned in {"delete", "remove", "loeschen", "löschen"}:
        return "delete"
    return None


def _strip_prefixed_value(text: str, prefixes: tuple[str, ...]) -> str:
    lowered = text.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return text[len(prefix):].strip()
    return ""


def _parse_done_target(
    storage: Storage,
    scope_id: str,
    payload: str,
    sender: str,
    language: str,
) -> tuple[str, str | None, str | None]:
    value = payload.strip()
    if not value:
        return "", None, None
    lowered = value.lower()
    marker_index = -1
    marker_length = 0
    # Attribute completion to another member: "done bins by/for Anna", "erledigt Müll von/für Max"
    for marker in (" by ", " for ", " von ", " fuer ", " für "):
        idx = lowered.rfind(marker)
        if idx > marker_index:
            marker_index = idx
            marker_length = len(marker)
    if marker_index == -1:
        return value, sender, None

    chore_name = value[:marker_index].strip()
    member_name = value[marker_index + marker_length :].strip()
    if not chore_name or not member_name:
        return value, sender, None
    target_sender = storage.sender_by_display_name(scope_id, member_name)
    if target_sender is None:
        return "", None, _text(language, "done_member_not_found", name=member_name)
    return chore_name, target_sender, None


def _format_duration(total_seconds: float, language: str) -> str:
    seconds = max(0, int(total_seconds))
    minutes = seconds // 60
    if minutes < 1:
        return "less than 1 minute" if language == "en" else "unter 1 Minute"

    days = minutes // (24 * 60)
    hours = (minutes % (24 * 60)) // 60
    mins = minutes % 60

    parts = []
    if language == "de":
        if days:
            parts.append(f"{days} {'Tag' if days == 1 else 'Tagen'}")
        if hours:
            parts.append(f"{hours} {'Stunde' if hours == 1 else 'Stunden'}")
        if mins and not days:
            parts.append(f"{mins} {'Minute' if mins == 1 else 'Minuten'}")
    else:
        if days:
            parts.append(f"{days} {'day' if days == 1 else 'days'}")
        if hours:
            parts.append(f"{hours} {'hour' if hours == 1 else 'hours'}")
        if mins and not days:
            parts.append(f"{mins} {'minute' if mins == 1 else 'minutes'}")
    return " ".join(parts[:2])


def _format_list_timestamp(value: str | datetime, tz_name: str | None = None) -> str:
    return format_local_timestamp(value, tz_name)


def _format_last_done(
    storage: Storage,
    scope_id: str,
    last_done_at: str | None,
    last_done_by: str | None,
    language: str,
) -> str:
    if not last_done_at:
        return "last done: never" if language == "en" else "zuletzt erledigt: nie"
    timestamp = _format_list_timestamp(last_done_at, storage.get_timezone(scope_id))
    if last_done_by:
        who = storage.display_name(scope_id, last_done_by)
        if language == "de":
            return f"zuletzt erledigt: {timestamp} von {who}"
        return f"last done: {timestamp} by {who}"
    if language == "de":
        return f"zuletzt erledigt: {timestamp}"
    return f"last done: {timestamp}"


def _format_due_status(
    storage: Storage,
    scope_id: str,
    row: object,
    schedule: dict | None,
    language: str,
    now: datetime,
) -> str:
    if schedule is None or schedule["type"] == "none":
        return _text(language, "open_task_label")

    requires_confirmation = row["requires_confirmation"] == 1
    base_timestamp = row["last_done_at"] or row["created_at"]
    tz_name = storage.get_timezone(scope_id)
    due_at = next_due_at(
        parse_db_datetime(base_timestamp),
        schedule,
        row["reminder_at_minutes"] if "reminder_at_minutes" in row.keys() else None,
        tz_name=tz_name,
    )
    if due_at <= now:
        duration = _format_duration((now - due_at).total_seconds(), language)
        if language == "de":
            return f"überfällig seit {duration} (fällig war {_format_list_timestamp(due_at, tz_name)})"
        return f"overdue by {duration} (was due {_format_list_timestamp(due_at, tz_name)})"

    duration = _format_duration((due_at - now).total_seconds(), language)
    if language == "de":
        return f"nächste Fälligkeit: {_format_list_timestamp(due_at, tz_name)} (in {duration})"
    return f"next due: {_format_list_timestamp(due_at, tz_name)} (in {duration})"


def _format_chores_short(storage: Storage, scope_id: str, chores: list, language: str) -> str:
    if not chores:
        return _text(language, "no_chores")
    lines = [_text(language, "chores_header")]
    for idx, row in enumerate(chores, start=1):
        schedule = schedule_from_storage(row["reminder_schedule"], row["reminder_interval_minutes"])
        if schedule is None or schedule["type"] == "none":
            tag = _text(language, "open_task_short")
        else:
            tag = format_schedule_frequency(schedule, language)
        lines.append(f"{idx}. {row['name']} ({tag})")
    lines.append(f"💡 {_text(language, 'list_extend_tip')}")
    return "\n".join(lines)


def _format_chores_extended(storage: Storage, scope_id: str, chores: list, language: str) -> str:
    if not chores:
        return _text(language, "no_chores")
    blocks = [_text(language, "chores_header_extended")]
    now = datetime.utcnow()
    for idx, row in enumerate(chores, start=1):
        schedule = schedule_from_storage(row["reminder_schedule"], row["reminder_interval_minutes"])
        reminder_text = format_schedule_frequency(schedule, language)
        lines = [f"{idx}. {row['name']}"]
        if schedule and schedule["type"] == "none":
            lines.append(f"   • {_text(language, 'open_task_label')}")
        else:
            lines.append(f"   • {_text(language, 'reminder_label')}: {reminder_text}")
            if schedule and reminder_time_applies(schedule):
                lines.append(
                    f"   • {_text(language, 'reminder_time_label')}: "
                    f"{format_reminder_time_label(effective_reminder_at_minutes(schedule, row['reminder_at_minutes']), language)}"
                )
            if schedule and schedule.get("type") == "once":
                counts = True
                if "count_in_stats" in row.keys():
                    counts = int(row["count_in_stats"] or 0) == 1
                lines.append(
                    f"   • {_text(language, 'count_in_stats_label')}: "
                    f"{_text(language, 'count_in_stats_yes' if counts else 'count_in_stats_no')}"
                )
                delete_cmd = "delete" if language == "en" else "lösche"
                lines.append(f"   • {delete_cmd} {row['name']}")
            if row["requires_confirmation"] == 1:
                repeat_schedule = schedule_from_storage(
                    row["repeat_reminder_schedule"],
                    row["repeat_reminder_minutes"],
                )
                lines.append(f"   • {_text(language, 'confirmation_required')}")
                lines.append(
                    f"   • {_text(language, 'repeat_reminder_label')}: "
                    f"{format_schedule_delay(repeat_schedule, language)}"
                )
            else:
                lines.append(f"   • {_text(language, 'confirmation_not_required')}")
            lines.append(f"   • {_format_due_status(storage, scope_id, row, schedule, language, now)}")
        lines.append(f"   • {_format_last_done(storage, scope_id, row['last_done_at'], row['last_done_by'], language)}")
        blocks.append("\n".join(lines))
    return mobile_blocks(*blocks)


def _format_chores(storage: Storage, scope_id: str, chores: list, language: str, extended: bool = False) -> str:
    if extended:
        return _format_chores_extended(storage, scope_id, chores, language)
    return _format_chores_short(storage, scope_id, chores, language)


def _parse_history_limit(raw: str) -> int:
    parts = raw.strip().split(maxsplit=1)
    if len(parts) == 1:
        return 20
    try:
        return int(parts[1])
    except ValueError:
        return 20


def _format_mark_done_message(
    ok: bool, msg: str, chore_name: str, language: str, tz_name: str | None = None
) -> str:
    if ok:
        for prefix, key in (
            ("One-shot no-stats saved: ", "mark_done_one_shot_no_stats"),
            ("One-shot saved: ", "mark_done_one_shot"),
            ("Saved: ", "mark_done_saved"),
        ):
            if msg.startswith(prefix) and " at " in msg and " by " in msg:
                body = msg[len(prefix):]
                name_part, rest = body.split(" at ", 1)
                done_at, sender = rest.split(" by ", 1)
                done_at = done_at.removesuffix(" UTC")
                sender = sender.rstrip(".")
                return _text(
                    language,
                    key,
                    name=name_part.strip(),
                    done_at=_format_list_timestamp(done_at.strip(), tz_name),
                    sender=sender.strip(),
                )
        if language == "en":
            return msg
    return _text(language, "mark_done_missing", name=chore_name)


def _format_rename_message(ok: bool, msg: str, old_name: str, new_name: str, language: str) -> str:
    if language == "en":
        return msg
    if ok:
        return _text(language, "renamed", old=old_name, new=new_name)
    if "does not exist" in msg:
        return _text(language, "rename_missing", name=old_name)
    if "already exists" in msg:
        return _text(language, "rename_exists", name=new_name)
    return _text(language, "new_name_empty")


def _action_label(action_type: str, language: str) -> str:
    labels = {
        "en": {
            "add_chore": "added chore",
            "delete_chore": "deleted chore",
            "done": "marked done",
            "rename_chore": "renamed chore",
            "reset_group": "reset group",
            "set_confirmation": "changed done confirmation",
            "set_auth_reminder": "changed Signal link reminder",
            "set_language": "changed language",
            "set_timezone": "changed timezone",
            "set_quiet_hours": "changed quiet hours",
            "set_repeat_reminder": "changed overdue reminder",
            "set_reminder_time": "changed reminder time",
            "set_schedule": "changed schedule",
            "undo_done": "undid completion",
        },
        "de": {
            "add_chore": "Aufgabe hinzugefügt",
            "delete_chore": "Aufgabe gelöscht",
            "done": "als erledigt gespeichert",
            "rename_chore": "Aufgabe umbenannt",
            "reset_group": "Gruppe zurückgesetzt",
            "set_confirmation": "Erledigt-Bestätigung geändert",
            "set_auth_reminder": "Signal-Link-Erinnerung geändert",
            "set_language": "Sprache geändert",
            "set_timezone": "Zeitzone geändert",
            "set_quiet_hours": "Ruhezeit geändert",
            "set_repeat_reminder": "erneute Erinnerung geändert",
            "set_reminder_time": "Erinnerungszeit geändert",
            "set_schedule": "Zeitplan geändert",
            "undo_done": "Erledigung rückgängig gemacht",
        },
    }
    return labels.get(language, labels["en"]).get(action_type, action_type)


def _format_stats(storage: Storage, scope_id: str, language: str) -> str:
    stats = storage.action_stats(scope_id)
    lines = [
        _text(language, "stats_header"),
        _text(
            language,
            "stats_summary",
            chore_count=stats["chore_count"],
            done_count=stats["done_count"],
        ),
    ]

    actions = stats["actions"]
    lines.append(_text(language, "stats_actions_header"))
    if actions:
        lines.extend(f"- {_action_label(action, language)}: {count}" for action, count in sorted(actions.items()))
    else:
        lines.append(f"- {_text(language, 'stats_none')}")

    lines.append(_text(language, "stats_top_done_header"))
    if stats["top_done"]:
        lines.extend(
            f"- {_stats_display_name(row['name'], language)}: {row['count']}"
            for row in stats["top_done"]
        )
    else:
        lines.append(f"- {_text(language, 'stats_none')}")

    lines.append(_text(language, "stats_recent_header"))
    if stats["recent_actions"]:
        lines.extend(
            f"- {row['created_at']}: {_action_label(row['action_type'], language)} {row['chore_name'] or ''}".strip()
            for row in stats["recent_actions"]
        )
    else:
        lines.append(f"- {_text(language, 'stats_none')}")
    return "\n".join(lines)


def _handle_pending_member_name(storage: Storage, text: str, sender: str, scope_id: str, language: str) -> str | None:
    pending = storage.get_pending_member_name(scope_id, sender)
    if pending is None:
        return None
    if pending["step"] == STALE_STEP:
        action = parse_stale_response(text)
        if action == "discard":
            storage.clear_pending_member_name(scope_id, sender)
            return _text(language, "cancelled")
        if action == "continue":
            storage.restore_dialogue_step("pending_member_names", scope_id, sender)
            return _text(language, "ask_display_name")
        return stale_prompt_text(language, "name")
    if _is_cancel(text):
        storage.clear_pending_member_name(scope_id, sender)
        return _text(language, "cancelled")
    display_name = text.strip()
    if not is_valid_display_name(display_name):
        return _text(language, "display_name_invalid")
    storage.set_display_name(scope_id, sender, display_name)
    chore_name = pending["chore_name"]
    storage.clear_pending_member_name(scope_id, sender)
    ok, msg = storage.mark_done(scope_id, chore_name, sender)
    if ok:
        storage.log_action(scope_id, sender, "done", chore_name)
    return _format_mark_done_message(ok, msg, chore_name, language, storage.get_timezone(scope_id))


def _handle_pending_chore_edit(storage: Storage, text: str, sender: str, scope_id: str, language: str) -> str | None:
    pending_edit = storage.get_pending_chore_edit(scope_id, sender)
    if pending_edit is None:
        return None
    if pending_edit["step"] == STALE_STEP:
        action = parse_stale_response(text)
        if action == "discard":
            storage.clear_pending_chore_edit(scope_id, sender)
            return _text(language, "cancelled")
        if action == "continue":
            storage.restore_dialogue_step("pending_chore_edits", scope_id, sender)
            return _edit_continue_prompt(storage, scope_id, sender, language)
        return stale_prompt_text(language, "edit")
    if _is_cancel(text):
        storage.clear_pending_chore_edit(scope_id, sender)
        return _text(language, "cancelled")

    chore_name = pending_edit["chore_name"]
    field = pending_edit["field"]
    if not field:
        selected_field = _edit_field_from_text(text)
        if selected_field is None:
            return _text(language, "edit_choose_option")
        storage.update_pending_chore_edit(scope_id, sender, selected_field)
        if selected_field == "name":
            return _text(language, "edit_new_name", name=chore_name)
        if selected_field == "schedule":
            return _text(language, "edit_new_schedule", name=chore_name)
        if selected_field == "confirmation":
            return _text(language, "edit_new_confirmation", name=chore_name)
        if selected_field == "remind_time":
            return _text(language, "edit_new_remind_time", name=chore_name)
        if selected_field == "repeat":
            return _text(language, "edit_new_repeat", name=chore_name)
        return _text(language, "edit_confirm_delete", name=chore_name)

    if field == "name":
        new_name = text.strip()
        if not new_name:
            return _text(language, "new_name_empty")
        storage.clear_pending_chore_edit(scope_id, sender)
        ok, msg = storage.rename_chore(scope_id, chore_name, new_name)
        if ok:
            storage.log_action(scope_id, sender, "rename_chore", chore_name, new_name)
        return _format_rename_message(ok, msg, chore_name, new_name, language)

    if field == "schedule":
        schedule = parse_schedule(text)
        if schedule is None:
            return _text(language, "usage_schedule")
        storage.clear_pending_chore_edit(scope_id, sender)
        if not storage.set_chore_schedule(scope_id, chore_name, schedule):
            return _text(language, "not_found", name=chore_name)
        storage.log_action(scope_id, sender, "set_schedule", chore_name, humanize_schedule(schedule, language))
        return _text(
            language,
            "schedule_set",
            name=chore_name,
            interval=format_schedule_frequency(schedule, language),
        )

    if field == "remind_time":
        parsed = parse_reminder_time_answer(text)
        if parsed == "invalid":
            return _text(language, "usage_reminder_time")
        storage.clear_pending_chore_edit(scope_id, sender)
        if not storage.set_chore_reminder_time(scope_id, chore_name, parsed):
            return _text(language, "not_found", name=chore_name)
        storage.log_action(
            scope_id,
            sender,
            "set_reminder_time",
            chore_name,
            format_reminder_time_label(parsed, language),
        )
        return _text(
            language,
            "reminder_time_set",
            name=chore_name,
            time=format_reminder_time_label(parsed, language),
        )

    if field == "confirmation":
        requires_confirmation = _confirmation_answer(text)
        if requires_confirmation is None:
            return _text(language, "confirm_expected")
        storage.clear_pending_chore_edit(scope_id, sender)
        if not storage.set_chore_confirmation(scope_id, chore_name, requires_confirmation):
            return _text(language, "not_found", name=chore_name)
        storage.log_action(
            scope_id,
            sender,
            "set_confirmation",
            chore_name,
            "on" if requires_confirmation else "off",
        )
        return _text(
            language,
            "confirmation_set_on" if requires_confirmation else "confirmation_set_off",
            name=chore_name,
        )

    if field == "repeat":
        schedule = parse_schedule(text)
        if schedule is None or schedule["type"] == "none":
            return _text(language, "usage_repeat")
        storage.clear_pending_chore_edit(scope_id, sender)
        if not storage.set_chore_repeat_reminder(scope_id, chore_name, schedule):
            return _text(language, "not_found", name=chore_name)
        storage.log_action(scope_id, sender, "set_repeat_reminder", chore_name, humanize_schedule(schedule, language))
        return _text(
            language,
            "repeat_set",
            name=chore_name,
            interval=format_schedule_delay(schedule, language),
        )

    delete_confirmed = _confirmation_answer(text)
    if delete_confirmed is None:
        return _text(language, "confirm_expected")
    storage.clear_pending_chore_edit(scope_id, sender)
    if not delete_confirmed:
        return _text(language, "edit_delete_cancelled", name=chore_name)
    if storage.delete_chore(scope_id, chore_name):
        storage.log_action(scope_id, sender, "delete_chore", chore_name)
        return _text(language, "deleted", name=chore_name)
    return _text(language, "not_found", name=chore_name)


def _handle_pending_chore_setup(storage: Storage, text: str, sender: str, scope_id: str, language: str) -> str | None:
    pending_setup = storage.get_pending_chore_setup(scope_id, sender)
    if pending_setup is None:
        return None
    if _is_cancel(text):
        storage.clear_pending_chore_setup(scope_id, sender)
        return _text(language, "cancelled")

    step = pending_setup["step"]
    if step == STALE_STEP:
        action = parse_stale_response(text)
        if action == "discard":
            storage.clear_pending_chore_setup(scope_id, sender)
            return _text(language, "cancelled")
        if action == "continue":
            storage.restore_dialogue_step("pending_chore_setups", scope_id, sender)
            return _chore_setup_prompt(storage, scope_id, sender, language)
        return stale_prompt_text(language, "add chore")
    if step == "name":
        chore_name = text.strip()
        if not chore_name:
            return _text(language, "setup_chore_name")
        storage.update_pending_chore_setup(scope_id, sender, "schedule", chore_name, "", None)
        if _pending_is_one_shot(pending_setup):
            return _text(language, "setup_once_schedule", name=chore_name)
        return _text(language, "setup_chore_schedule", name=chore_name)

    if step == "schedule":
        schedule = parse_schedule(text)
        if _pending_is_one_shot(pending_setup):
            schedule = _as_once_schedule(schedule, text)
        if schedule is None:
            return _text(language, "usage_once" if _pending_is_one_shot(pending_setup) else "usage_add")
        stored = schedule_to_storage(schedule)
        chore_name = pending_setup["name"]
        if schedule["type"] == "none":
            if _pending_is_one_shot(pending_setup):
                return _text(language, "usage_once")
            storage.clear_pending_chore_setup(scope_id, sender)
            return _finalize_chore_creation(
                storage,
                scope_id,
                sender,
                language,
                chore_name,
                schedule,
                None,
                True,
                None,
            )
        if reminder_time_applies(schedule):
            storage.update_pending_chore_setup(
                scope_id,
                sender,
                "remind_time",
                chore_name,
                stored,
                None,
            )
            return _text(
                language,
                "setup_once_remind_time" if _pending_is_one_shot(pending_setup) else "setup_chore_remind_time",
                name=chore_name,
            )
        if _pending_is_one_shot(pending_setup):
            storage.update_pending_chore_setup(
                scope_id,
                sender,
                "count_stats",
                chore_name,
                stored,
                None,
            )
            return _text(language, "setup_once_count_stats", name=chore_name)
        storage.update_pending_chore_setup(
            scope_id,
            sender,
            "confirmation",
            chore_name,
            stored,
            None,
        )
        return _text(language, "setup_chore_confirmation", name=chore_name)

    if step == "remind_time":
        parsed = parse_reminder_time_answer(text)
        if parsed == "invalid":
            return _text(language, "usage_reminder_time")
        next_step = "count_stats" if _pending_is_one_shot(pending_setup) else "confirmation"
        storage.update_pending_chore_setup(
            scope_id,
            sender,
            next_step,
            pending_setup["name"],
            pending_setup["reminder_schedule"],
            parsed,
            pending_setup["count_in_stats"] if "count_in_stats" in pending_setup.keys() else None,
        )
        if next_step == "count_stats":
            return _text(language, "setup_once_count_stats", name=pending_setup["name"])
        return _text(language, "setup_chore_confirmation", name=pending_setup["name"])

    if step == "count_stats":
        answer = _confirmation_answer(text)
        if answer is None:
            return _text(language, "confirm_expected")
        storage.update_pending_chore_setup(
            scope_id,
            sender,
            "confirmation",
            pending_setup["name"],
            pending_setup["reminder_schedule"],
            pending_setup["reminder_at_minutes"],
            1 if answer else 0,
        )
        return _text(language, "setup_chore_confirmation", name=pending_setup["name"])

    if step == "confirmation":
        answer = _confirmation_answer(text)
        if answer is None:
            return _text(language, "confirm_expected")
        schedule = schedule_from_storage(pending_setup["reminder_schedule"])
        chore_name = pending_setup["name"]
        reminder_at_minutes = pending_setup["reminder_at_minutes"]
        if schedule is None:
            storage.clear_pending_chore_setup(scope_id, sender)
            return _text(language, "usage_add")
        if answer and schedule["type"] != "none":
            repeat_schedule = _default_repeat_schedule(schedule)
        else:
            repeat_schedule = None
        count_in_stats = True
        if _pending_is_one_shot(pending_setup):
            raw_count = pending_setup["count_in_stats"] if "count_in_stats" in pending_setup.keys() else None
            count_in_stats = True if raw_count is None else int(raw_count) == 1
        storage.clear_pending_chore_setup(scope_id, sender)
        return _finalize_chore_creation(
            storage,
            scope_id,
            sender,
            language,
            chore_name,
            schedule,
            reminder_at_minutes,
            answer,
            repeat_schedule,
            count_in_stats=count_in_stats,
        )

    if step == "repeat":
        schedule = schedule_from_storage(pending_setup["reminder_schedule"])
        chore_name = pending_setup["name"]
        reminder_at_minutes = pending_setup["reminder_at_minutes"]
        repeat_schedule = _parse_repeat_or_default(text, schedule)
        if schedule is None or repeat_schedule is None or repeat_schedule["type"] == "none":
            return _text(language, "usage_repeat")
        storage.clear_pending_chore_setup(scope_id, sender)
        return _finalize_chore_creation(
            storage,
            scope_id,
            sender,
            language,
            chore_name,
            schedule,
            reminder_at_minutes,
            True,
            repeat_schedule,
        )

    storage.clear_pending_chore_setup(scope_id, sender)
    return _text(language, "cancelled")


def _continue_once_interview(
    storage: Storage,
    scope_id: str,
    sender: str,
    language: str,
    chore_name: str,
    schedule: dict | None,
    reminder_at_minutes: int | None,
) -> str:
    existing_names = [row["name"].lower() for row in storage.list_chores(scope_id)]
    if chore_name.lower() in existing_names:
        return _text(language, "already_exists", name=chore_name)
    storage.start_pending_chore_setup(scope_id, sender, one_shot=True)
    if schedule is None:
        storage.update_pending_chore_setup(scope_id, sender, "schedule", chore_name, "", None)
        return _text(language, "setup_once_schedule", name=chore_name)
    stored = schedule_to_storage(schedule)
    if reminder_time_applies(schedule) and reminder_at_minutes is None:
        storage.update_pending_chore_setup(scope_id, sender, "remind_time", chore_name, stored, None)
        return _text(language, "setup_once_remind_time", name=chore_name)
    storage.update_pending_chore_setup(
        scope_id,
        sender,
        "count_stats",
        chore_name,
        stored,
        reminder_at_minutes,
    )
    return _text(language, "setup_once_count_stats", name=chore_name)


def _format_vacation_datetime(value: str) -> str:
    parsed = parse_db_datetime(value)
    if parsed is None:
        return value
    return parsed.strftime("%Y-%m-%d %H:%M")


def _format_vacation_prep_items(rows: list, language: str) -> str:
    if not rows:
        return _text(language, "vacation_chore_list_empty")
    return "\n".join(f"{index}. {row['name']}" for index, row in enumerate(rows, 1))


def _vacation_start_reply(
    storage: Storage,
    scope_id: str,
    sender: str,
    language: str,
    vacation_row,
) -> str:
    ends = _format_vacation_datetime(vacation_row["ends_at"])
    duration = format_duration(
        parse_db_datetime(vacation_row["ends_at"]) - parse_db_datetime(vacation_row["starts_at"]),
        language,
    )
    if vacation_row["status"] == "scheduled":
        return _text(
            language,
            "vacation_scheduled",
            starts=_format_vacation_datetime(vacation_row["starts_at"]),
            ends=ends,
            duration=duration,
        )
    if vacation_row["status"] == "prep":
        pending = storage.list_vacation_prep_pending(vacation_row["id"])
        return _text(
            language,
            "vacation_started_prep",
            items=_format_vacation_prep_items(pending, language),
            ends=ends,
            duration=duration,
        )
    return _text(language, "vacation_started_active", ends=ends, duration=duration)


def _start_vacation_from_plan(
    storage: Storage,
    scope_id: str,
    sender: str,
    language: str,
    plan: dict,
) -> str:
    vacation_row = storage.create_member_vacation(scope_id, sender, plan["delay"], plan["duration"])
    storage.log_action(
        scope_id,
        sender,
        "vacation_start",
        details=f"{plan['delay'].days}d delay, {plan['duration'].days}d duration",
    )
    return _vacation_start_reply(storage, scope_id, sender, language, vacation_row)


def _parse_vacation_when(text: str) -> timedelta | None:
    cleaned = text.strip().lower()
    if cleaned in {"now", "jetzt", "sofort", "immediately"}:
        return timedelta(0)
    if cleaned.startswith("in "):
        return parse_duration(cleaned[3:].strip())
    return parse_duration(cleaned)


def _strip_vacation_prefix(text: str) -> str | None:
    cleaned = text.strip()
    lowered = cleaned.lower()
    for prefix in ("vacation", "urlaub"):
        if lowered == prefix:
            return ""
        if lowered.startswith(prefix + " "):
            return cleaned[len(prefix) + 1 :].strip()
    return None


def _handle_pending_vacation_chore_add(
    storage: Storage,
    text: str,
    sender: str,
    scope_id: str,
    language: str,
) -> str | None:
    pending = storage.get_pending_vacation_chore_add(scope_id, sender)
    if pending is None:
        return None
    if _is_cancel(text):
        storage.clear_pending_vacation_chore_add(scope_id, sender)
        return _text(language, "cancelled")
    if pending["step"] == STALE_STEP:
        action = parse_stale_response(text)
        if action == "discard":
            storage.clear_pending_vacation_chore_add(scope_id, sender)
            return _text(language, "cancelled")
        if action == "continue":
            storage.restore_dialogue_step("pending_vacation_chore_adds", scope_id, sender)
            return _text(language, "vacation_setup_chore_name")
        return stale_prompt_text(language, "vacation task")
    chore_name = text.strip()
    if not chore_name:
        return _text(language, "vacation_setup_chore_name")
    storage.clear_pending_vacation_chore_add(scope_id, sender)
    if storage.add_vacation_chore(scope_id, chore_name):
        storage.log_action(scope_id, sender, "vacation_chore_add", chore_name)
        return _text(language, "vacation_chore_added", name=chore_name)
    return _text(language, "vacation_chore_exists", name=chore_name)


def _handle_pending_vacation_setup(
    storage: Storage,
    text: str,
    sender: str,
    scope_id: str,
    language: str,
) -> str | None:
    pending = storage.get_pending_vacation_setup(scope_id, sender)
    if pending is None:
        return None
    if _is_cancel(text):
        storage.clear_pending_vacation_setup(scope_id, sender)
        return _text(language, "cancelled")
    if pending["step"] == STALE_STEP:
        action = parse_stale_response(text)
        if action == "discard":
            storage.clear_pending_vacation_setup(scope_id, sender)
            return _text(language, "cancelled")
        if action == "continue":
            storage.restore_dialogue_step("pending_vacation_setups", scope_id, sender)
            pending = storage.get_pending_vacation_setup(scope_id, sender)
            if pending and pending["step"] == "duration":
                return _text(language, "vacation_setup_duration")
            return _text(language, "vacation_setup_when")
        return stale_prompt_text(language, "vacation")
    if pending["step"] == "when":
        delay = _parse_vacation_when(text)
        if delay is None:
            return _text(language, "vacation_when_invalid")
        storage.update_pending_vacation_setup(scope_id, sender, "duration", int(delay.total_seconds() // 86400))
        return _text(language, "vacation_setup_duration")
    if pending["step"] == "duration":
        duration = parse_duration(text)
        if duration is None:
            return _text(language, "vacation_duration_invalid")
        delay_days = pending["delay_days"]
        storage.clear_pending_vacation_setup(scope_id, sender)
        return _start_vacation_from_plan(
            storage,
            scope_id,
            sender,
            language,
            {"delay": timedelta(days=delay_days), "duration": duration},
        )
    storage.clear_pending_vacation_setup(scope_id, sender)
    return _text(language, "cancelled")


def _handle_vacation_command(
    storage: Storage,
    command_text: str,
    sender: str,
    scope_id: str,
    language: str,
) -> str | None:
    payload = _strip_vacation_prefix(command_text)
    if payload is None:
        return None
    lowered = payload.lower()

    if lowered in {"help", "hilfe", "?"}:
        return _text(language, "vacation_help")

    if lowered in {"status", "info"}:
        vacation = storage.get_member_vacation(scope_id, sender)
        if vacation is None:
            return _text(language, "vacation_none")
        duration = format_duration(
            parse_db_datetime(vacation["ends_at"]) - parse_db_datetime(vacation["starts_at"]),
            language,
        )
        if vacation["status"] == "scheduled":
            return _text(
                language,
                "vacation_status_scheduled",
                starts=_format_vacation_datetime(vacation["starts_at"]),
                ends=_format_vacation_datetime(vacation["ends_at"]),
                duration=duration,
            )
        if vacation["status"] == "prep":
            pending = storage.list_vacation_prep_pending(vacation["id"])
            return _text(
                language,
                "vacation_status_prep",
                ends=_format_vacation_datetime(vacation["ends_at"]),
                items=_format_vacation_prep_items(pending, language),
            )
        return _text(
            language,
            "vacation_status_active",
            ends=_format_vacation_datetime(vacation["ends_at"]),
        )

    if lowered in {"cancel", "stop", "end", "abbrechen", "beenden", "stopp"}:
        if storage.cancel_member_vacation(scope_id, sender):
            storage.log_action(scope_id, sender, "vacation_cancel")
            return _text(language, "vacation_cancelled")
        return _text(language, "vacation_nothing_to_cancel")

    if lowered in {"list", "liste", "tasks", "aufgaben"}:
        rows = storage.list_vacation_chores(scope_id)
        if not rows:
            return _text(language, "vacation_chore_list_empty")
        items = "\n".join(f"- {row['name']}" for row in rows)
        return _text(language, "vacation_chore_list", items=items)

    if (
        lowered.startswith("add ")
        or lowered == "add"
        or lowered.startswith("aufgabe ")
        or lowered == "aufgabe"
    ):
        if lowered.startswith("add "):
            name = payload[4:].strip()
        elif lowered.startswith("aufgabe "):
            name = payload[8:].strip()
        else:
            name = ""
        if not name:
            storage.start_pending_vacation_chore_add(scope_id, sender)
            return _text(language, "vacation_setup_chore_name")
        if storage.add_vacation_chore(scope_id, name):
            storage.log_action(scope_id, sender, "vacation_chore_add", name)
            return _text(language, "vacation_chore_added", name=name)
        return _text(language, "vacation_chore_exists", name=name)

    delete_prefixes = ("delete ", "remove ", "lösche ", "loesche ")
    for prefix in delete_prefixes:
        if lowered.startswith(prefix):
            name = payload[len(prefix) :].strip()
            if storage.delete_vacation_chore(scope_id, name):
                storage.log_action(scope_id, sender, "vacation_chore_delete", name)
                return _text(language, "vacation_chore_deleted", name=name)
            return _text(language, "vacation_chore_not_found", name=name)

    done_prefixes = ("done ", "erledigt ")
    for prefix in done_prefixes:
        if lowered.startswith(prefix):
            name = payload[len(prefix) :].strip()
            vacation = storage.get_member_vacation(scope_id, sender)
            if vacation is None or vacation["status"] != "prep":
                return _text(language, "vacation_prep_not_found", name=name)
            if storage.mark_vacation_prep_done(scope_id, vacation["id"], name, sender):
                storage.log_action(scope_id, sender, "vacation_prep_done", name)
                remaining = storage.list_vacation_prep_pending(vacation["id"])
                if remaining:
                    return mobile_blocks(
                        _text(language, "vacation_prep_done", name=name),
                        _text(
                            language,
                            "vacation_status_prep",
                            ends=_format_vacation_datetime(vacation["ends_at"]),
                            items=_format_vacation_prep_items(remaining, language),
                        ),
                    )
                return mobile_blocks(
                    _text(language, "vacation_prep_done", name=name),
                    _text(
                        language,
                        "vacation_status_active",
                        ends=_format_vacation_datetime(vacation["ends_at"]),
                    ),
                )
            return _text(language, "vacation_prep_not_found", name=name)

    if lowered in {"skip prep", "skip", "überspringen", "ueberspringen"}:
        vacation = storage.get_member_vacation(scope_id, sender)
        if vacation is None or vacation["status"] != "prep":
            return _text(language, "vacation_prep_skip_unavailable")
        if storage.skip_vacation_prep(scope_id, vacation["id"], sender):
            storage.log_action(scope_id, sender, "vacation_prep_skip")
            return _text(language, "vacation_prep_skipped")
        return _text(language, "vacation_prep_skip_unavailable")

    if not payload:
        storage.start_pending_vacation_setup(scope_id, sender)
        return _text(language, "vacation_setup_when")

    plan = parse_vacation_plan(payload)
    if plan is not None:
        return _start_vacation_from_plan(storage, scope_id, sender, language, plan)

    return _text(language, "vacation_usage")


def format_vacation_event(storage: Storage, event: dict) -> str:
    scope_id = event["scope_id"]
    language = storage.get_language(scope_id)
    display_name = storage.display_name(scope_id, event["sender"])
    if event["type"] == "ended":
        return _text(language, "vacation_ended_notice", name=display_name)
    ends = _format_vacation_datetime(event["ends_at"])
    if event.get("status") == "prep":
        pending = storage.list_vacation_prep_pending(event["vacation_id"])
        return _text(
            language,
            "vacation_started_prep_notice",
            name=display_name,
            items=_format_vacation_prep_items(pending, language),
        )
    return _text(language, "vacation_started_notice", name=display_name, ends=ends)


COMMAND_HINTS = {
    "en": (
        "help",
        "list",
        "list extend",
        "done",
        "undo",
        "name",
        "add",
        "todo",
        "once",
        "edit",
        "my stats",
        "group stats",
        "vacation",
        "vacation help",
        "history",
        "tutorial",
        "chore help",
        "edit help",
        "delete",
        "cancel",
        "stats",
        "admin help",
    ),
    "de": (
        "hilfe",
        "liste",
        "liste erweitert",
        "erledigt",
        "rückgängig",
        "name",
        "aufgabe",
        "todo",
        "einmal",
        "bearbeite",
        "meine statistik",
        "gruppen statistik",
        "urlaub",
        "urlaub hilfe",
        "verlauf",
        "anleitung",
        "aufgabe hilfe",
        "bearbeite hilfe",
        "lösche",
        "abbrechen",
        "statistik",
        "admin hilfe",
    ),
}

# A command word sent on its own gets its usage line instead of silence or a
# misparse (e.g. "undo done" read as undoing a chore called "done").
_BARE_COMMAND_USAGE = {
    **dict.fromkeys(("done", "erledigt"), "usage_done"),
    **dict.fromkeys(("undo", "undo done", "revoke", "revoke done", "rueckgaengig", "rückgängig"), "usage_undo_done"),
    **dict.fromkeys(("rename", "change chore", "umbenennen"), "usage_change"),
    **dict.fromkeys(("schedule", "due", "zeitplan", "faelligkeit", "fälligkeit"), "usage_schedule"),
    **dict.fromkeys(("reminder", "repeat", "remind", "erinnerung", "wiederholen"), "usage_repeat"),
    **dict.fromkeys(("reminder time", "remind time", "erinnerungszeit"), "usage_reminder_time"),
    **dict.fromkeys(("confirmation", "bestaetigung", "bestätigung"), "usage_confirmation"),
    **dict.fromkeys(
        ("reset group confirm", "zuruecksetzen bestaetigen", "zurücksetzen bestätigen"),
        "usage_reset_confirm",
    ),
}

_COMMAND_FOLD = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _fold_command(text: str) -> str:
    return text.lower().translate(_COMMAND_FOLD)


def _command_similarity(probe: str, hint: str) -> float:
    folded_probe = _fold_command(probe)
    folded_hint = _fold_command(hint)
    if not folded_probe:
        return 0.0
    if folded_probe == folded_hint:
        return 1.0
    if folded_hint.startswith(folded_probe) and len(folded_probe) >= 3:
        return 0.92
    return SequenceMatcher(None, folded_probe, folded_hint).ratio()


def _guess_command(text: str, language: str) -> str | None:
    cleaned = " ".join(text.strip().lower().split())
    if not cleaned:
        return None
    tokens = cleaned.split()
    primary = COMMAND_HINTS.get(language, COMMAND_HINTS["en"])
    secondary = COMMAND_HINTS["de"] if language == "en" else COMMAND_HINTS["en"]
    head_words = {hint.split()[0] for hint in primary + secondary}

    best_hint = None
    best_ratio = 0.0
    for hint in (*primary, *secondary):
        probe = " ".join(tokens[: len(hint.split())])
        ratio = _command_similarity(probe, hint)
        if ratio > best_ratio:
            best_ratio = ratio
            best_hint = hint

    first = tokens[0]
    first_is_head = _fold_command(first) in {_fold_command(word) for word in head_words}
    if first_is_head and best_hint:
        return best_hint
    if len(tokens) >= 8 and not first_is_head:
        return None
    if best_hint is None:
        return None
    threshold = 0.8 if len(tokens[0]) <= 3 else 0.72
    if best_ratio >= threshold:
        return best_hint
    return None


def handle_command(storage: Storage, message_text: str, sender: str, scope_id: str, group_id: str | None = None) -> str | list[str] | dict:
    text = message_text.strip()
    language = storage.get_language(scope_id)
    is_group = group_id is not None
    setup_complete = storage.is_group_ready(scope_id) if is_group else True

    if is_group and storage.has_admins(scope_id) and not storage.has_bot(scope_id):
        storage.set_bot_id(scope_id, runtime_bot_id())

    if not text:
        return ""

    if is_group and not setup_complete:
        language_request = _language_from_command(text)
        if not storage.has_language(scope_id):
            if language_request in SUPPORTED_LANGUAGES:
                storage.set_language(scope_id, language_request)
                storage.add_admin(scope_id, sender)
                storage.log_action(scope_id, sender, "set_language", details=language_request)
                bots = load_bot_registry()
                if len(bots) == 1:
                    bot_id = next(iter(bots))
                    storage.set_bot_id(scope_id, bot_id)
                    storage.log_action(scope_id, sender, "set_bot", details=bot_id)
                    return [
                        _text(language_request, f"language_set_{language_request}"),
                        _text(language_request, "setup_complete"),
                    ]
                return [
                    _text(language_request, f"language_set_{language_request}"),
                    _text(
                        language_request,
                        "setup_choose_bot",
                        options=_format_bot_options(language_request),
                    ),
                ]
            return _text(_help_language(storage, scope_id, text, language), "setup_choose_language")

        if not storage.has_bot(scope_id):
            language = storage.get_language(scope_id)
            bot_choice = _parse_bot_command(text)
            if bot_choice == "":
                return _text(
                    language,
                    "setup_choose_bot",
                    options=_format_bot_options(language),
                )
            if bot_choice == "invalid":
                return _text(language, "setup_bot_invalid")
            if bot_choice:
                return _complete_bot_setup(storage, scope_id, sender, language, bot_choice)
            return _text(
                language,
                "setup_choose_bot",
                options=_format_bot_options(language),
            )

        language = storage.get_language(scope_id)
        storage.add_admin(scope_id, sender)
        return _text(language, "setup_complete")

    admin_seen, admin_text = _admin_action(text) if is_group else (False, "")
    if admin_seen and not admin_text:
        return _text(language, "admin_help")
    command_text = admin_text if admin_text else text
    command_lowered = command_text.lower()

    language_request = _language_from_command(command_text)
    if language_request == "":
        return _text(language, "current_language")
    if language_request in SUPPORTED_LANGUAGES:
        if is_group and not admin_text:
            return _text(language, "admin_only")
        storage.set_language(scope_id, language_request)
        storage.log_action(scope_id, sender, "set_language", details=language_request)
        return _text(language_request, f"language_set_{language_request}")
    if language_request == "invalid":
        return _text(language, "language_usage")

    timezone_request = _timezone_from_command(command_text)
    if timezone_request == "":
        return _text(language, "current_timezone", timezone=storage.get_timezone(scope_id))
    if timezone_request == "invalid":
        return _text(language, "timezone_usage")
    if timezone_request is not None:
        if is_group and not admin_text:
            return _text(language, "admin_only")
        storage.set_timezone(scope_id, timezone_request)
        storage.log_action(scope_id, sender, "set_timezone", details=timezone_request)
        return _text(language, "timezone_set", timezone=timezone_request)

    if admin_seen and command_lowered in {"help", "hilfe", "admin", "admin help", "adminhilfe"}:
        return _text(_help_language(storage, scope_id, text, language), "admin_help")

    if command_lowered in {"help", "hilfe", "?"}:
        return _text(_help_language(storage, scope_id, text, language), "help")

    tutorial_topic = parse_tutorial_command(command_lowered)
    if tutorial_topic is not None:
        return tutorial_text(_help_language(storage, scope_id, text, language), tutorial_topic)

    if command_lowered in {
        "chore help",
        "chores help",
        "help chore",
        "help chores",
        "aufgabe hilfe",
        "aufgaben hilfe",
        "hilfe aufgabe",
        "hilfe aufgaben",
    }:
        return _text(_help_language(storage, scope_id, text, language), "chore_help")

    if command_lowered in {
        "edit help",
        "help edit",
        "bearbeite hilfe",
        "aendere hilfe",
        "ändere hilfe",
        "hilfe bearbeiten",
        "hilfe bearbeite",
    }:
        return _text(_help_language(storage, scope_id, text, language), "edit_help")

    if admin_seen and command_lowered in {"status", "stats", "statistik"}:
        return _format_stats(storage, scope_id, language)

    auth_reminder_command = _parse_auth_reminder_command(command_text)
    if auth_reminder_command is not None:
        if is_group and not admin_text:
            return _text(language, "admin_only")
        if not group_id:
            return _text(language, "group_only")
        if auth_reminder_command == "show":
            state_key = "enabled" if storage.get_auth_reminder_enabled(scope_id) else "disabled"
            return _text(language, "auth_reminder_current", state=_text(language, state_key))
        if auth_reminder_command == "invalid":
            return _text(language, "usage_auth_reminder")
        enabled = auth_reminder_command == "on"
        storage.set_auth_reminder_enabled(scope_id, enabled)
        storage.log_action(scope_id, sender, "set_auth_reminder", details="on" if enabled else "off")
        return _text(language, "auth_reminder_set_on" if enabled else "auth_reminder_set_off")

    quiet_hours_command = _parse_quiet_hours_command(command_text)
    if quiet_hours_command is not None:
        if is_group and not admin_text:
            return _text(language, "admin_only")
        action, start_minutes, end_minutes = quiet_hours_command
        if action == "show":
            current_start, current_end = storage.get_quiet_hours(scope_id)
            return _text(
                language,
                "quiet_hours_current",
                start=_format_time(current_start),
                end=_format_time(current_end),
                timezone=storage.get_timezone(scope_id),
            )
        if action == "invalid" or start_minutes is None or end_minutes is None:
            return _text(language, "usage_quiet_hours")
        storage.set_quiet_hours(scope_id, start_minutes, end_minutes)
        details = f"{_format_time(start_minutes)}-{_format_time(end_minutes)}"
        storage.log_action(scope_id, sender, "set_quiet_hours", details=details)
        return _text(
            language,
            "quiet_hours_set",
            start=_format_time(start_minutes),
            end=_format_time(end_minutes),
            timezone=storage.get_timezone(scope_id),
        )

    if command_lowered in {"groups", "gruppen"}:
        groups = storage.list_groups()
        if not groups:
            return _text(language, "no_groups")
        lines = [f"{idx}. {gid}" for idx, gid in enumerate(groups, start=1)]
        return _text(language, "groups_header") + "\n" + "\n".join(lines)

    if command_lowered in {
        "chores",
        "list chores",
        "list",
        "tasks",
        "aufgaben",
        "liste",
        "list extend",
        "list details",
        "list extended",
        "liste erweitert",
        "liste details",
        "liste detail",
        "extend",
        "erweitert",
        "details",
    }:
        extended = command_lowered in {
            "list extend",
            "list details",
            "list extended",
            "liste erweitert",
            "liste details",
            "liste detail",
            "extend",
            "erweitert",
            "details",
        }
        return _with_usage_tip(
            storage,
            scope_id,
            sender,
            language,
            "list",
            _format_chores(storage, scope_id, storage.list_chores(scope_id), language, extended=extended),
        )

    parsed_stats = _parse_stats_command(command_lowered)
    if parsed_stats is not None:
        if parsed_stats.get("invalid"):
            if parsed_stats.get("needs_chore") or parsed_stats.get("scope") == "group":
                return _text(language, "stats_chore_usage")
            return _text(language, "stats_usage")

        chore_name = parsed_stats.get("chore_name")
        wants_chart = parsed_stats["wants_chart"]
        chart_kind = parsed_stats.get("chart_kind")

        if parsed_stats["scope"] == "user":
            if chore_name:
                reply = _with_usage_tip(
                    storage,
                    scope_id,
                    sender,
                    language,
                    "stats",
                    _format_user_chore_stats(storage, scope_id, sender, language, chore_name),
                )
            else:
                reply = _with_usage_tip(
                    storage,
                    scope_id,
                    sender,
                    language,
                    "stats",
                    _format_user_stats(storage, scope_id, sender, language),
                )
            if wants_chart:
                stats = storage.user_stats(scope_id, sender)
                by_chore = stats["by_chore"]
                if chore_name:
                    by_chore = [
                        row for row in by_chore if _matches_stats_chore(row["name"], chore_name, language)
                    ]
                chart = user_stats_chart(_labeled_chore_rows(by_chore, language), language)
                if chart:
                    return _stats_reply(reply, [chart])
                return mobile_blocks(reply, _text(language, "stats_chart_empty"))
            return reply

        # group stats
        if chore_name:
            reply = _with_usage_tip(
                storage,
                scope_id,
                sender,
                language,
                "stats",
                _format_group_chore_stats(storage, scope_id, language, chore_name),
            )
            chore_rows = [
                row
                for row in storage.task_stats(scope_id)
                if _matches_stats_chore(row["name"], chore_name, language)
            ]
            user_totals = [
                {"sender": person["sender"], "count": person["count"]}
                for row in chore_rows
                for person in row.get("by_person") or []
            ]
        else:
            reply = _with_usage_tip(
                storage,
                scope_id,
                sender,
                language,
                "stats",
                _format_group_stats(storage, scope_id, language),
            )
            user_totals = storage.group_completion_totals(scope_id)
            chore_rows = storage.task_stats(scope_id)

        if wants_chart:
            kind = chart_kind or ("people" if chore_name else "people")
            if chart_kind and chart_kind.lower() not in group_chart_kinds(language):
                return mobile_blocks(reply, _text(language, "stats_chart_unknown"))
            chart = group_stats_chart(
                kind,
                user_totals,
                _labeled_chore_rows(chore_rows, language),
                lambda sender_id: storage.display_name(scope_id, sender_id),
                language,
            )
            if chart:
                hint = ""
                if not chore_name and (chart_kind or "people").lower() in {
                    "people",
                    "leute",
                    "wer",
                    "users",
                    "mitglieder",
                }:
                    hint = _text(language, "stats_chart_suggest_group")
                return _stats_reply(mobile_blocks(reply, hint) if hint else reply, [chart])
            return mobile_blocks(reply, _text(language, "stats_chart_empty"))
        return reply

    if command_lowered in {"stats", "statistik"}:
        return _text(language, "stats_usage")

    if _is_cancel(command_text):
        storage.clear_pending_chore_setup(scope_id, sender)
        storage.clear_pending_chore_edit(scope_id, sender)
        storage.clear_pending_chore_add(scope_id)
        storage.clear_pending_member_name(scope_id, sender)
        storage.clear_pending_vacation_setup(scope_id, sender)
        storage.clear_pending_vacation_chore_add(scope_id, sender)
        storage.clear_reset_request(scope_id)
        return _text(language, "cancelled")

    pending_vacation_setup_reply = _handle_pending_vacation_setup(storage, command_text, sender, scope_id, language)
    if pending_vacation_setup_reply is not None:
        return pending_vacation_setup_reply

    pending_vacation_chore_reply = _handle_pending_vacation_chore_add(storage, command_text, sender, scope_id, language)
    if pending_vacation_chore_reply is not None:
        return pending_vacation_chore_reply

    vacation_reply = _handle_vacation_command(storage, command_text, sender, scope_id, language)
    if vacation_reply is not None:
        return vacation_reply

    pending_name_reply = _handle_pending_member_name(storage, command_text, sender, scope_id, language)
    if pending_name_reply is not None:
        return pending_name_reply

    pending_setup_reply = _handle_pending_chore_setup(storage, command_text, sender, scope_id, language)
    if pending_setup_reply is not None:
        return pending_setup_reply

    pending_edit_reply = _handle_pending_chore_edit(storage, command_text, sender, scope_id, language)
    if pending_edit_reply is not None:
        return pending_edit_reply

    bare_usage_key = _BARE_COMMAND_USAGE.get(" ".join(command_lowered.split()))
    if bare_usage_key:
        return _text(language, bare_usage_key)

    if command_lowered in {"edit", "bearbeite", "aendere", "ändere"}:
        return _text(language, "usage_edit")
    edit_name = _edit_command_name(command_text)
    if edit_name:
        canonical_name = _canonical_chore_name(storage, scope_id, edit_name)
        if canonical_name is None:
            return _text(language, "not_found", name=edit_name)
        storage.start_pending_chore_edit(scope_id, sender, canonical_name)
        return _text(language, "edit_options", name=canonical_name)

    undo_name = _strip_prefixed_value(
        command_text,
        ("undo done ", "undo ", "revoke done ", "revoke ", "rueckgaengig ", "rückgängig "),
    )
    if undo_name:
        ok, msg = storage.undo_last_done(scope_id, undo_name)
        if ok:
            storage.log_action(scope_id, sender, "undo_done", undo_name)
            return _text(language, "undo_done_saved", name=undo_name)
        if "No completion" in msg:
            return _text(language, "undo_done_missing", name=undo_name)
        return _text(language, "not_found", name=undo_name)

    done_name = _strip_prefixed_value(command_text, ("done ", "erledigt "))
    if done_name:
        chore_name, done_sender, done_error = _parse_done_target(storage, scope_id, done_name, sender, language)
        if done_error is not None:
            return done_error
        if not chore_name:
            return _text(language, "usage_done")
        if done_sender is None:
            return _text(language, "usage_done")
        if done_sender == sender and not storage.has_display_name(scope_id, sender):
            storage.start_pending_member_name(scope_id, sender, chore_name)
            return _text(language, "ask_display_name")
        ok, msg = storage.mark_done(scope_id, chore_name, done_sender)
        if ok:
            storage.log_action(scope_id, sender, "done", chore_name)
        return _with_usage_tip(
            storage,
            scope_id,
            sender,
            language,
            "done",
            _format_mark_done_message(ok, msg, chore_name, language, storage.get_timezone(scope_id)),
        )

    name_value = _strip_prefixed_value(command_text, ("name ", "my name ", "mein name "))
    if name_value or command_lowered in {"name", "my name", "mein name"}:
        if not name_value:
            return _text(language, "usage_name")
        if not is_valid_display_name(name_value):
            return _text(language, "display_name_invalid")
        storage.set_display_name(scope_id, sender, name_value)
        return _with_usage_tip(
            storage,
            scope_id,
            sender,
            language,
            "name",
            _text(language, "display_name_saved", name=name_value.strip()),
        )

    pending_confirmation = storage.get_pending_chore_add(scope_id, sender)
    confirmation_answer = _confirmation_answer(command_text)
    if pending_confirmation is not None and confirmation_answer is not None:
        if not confirmation_answer:
            storage.clear_pending_chore_add(scope_id)
            return _text(language, "cancelled")
        chore_name = pending_confirmation["name"]
        schedule = schedule_from_storage(
            pending_confirmation["reminder_schedule"],
            pending_confirmation["reminder_interval_minutes"],
        )
        storage.clear_pending_chore_add(scope_id)
        if storage.add_chore(scope_id, chore_name, schedule):
            repeat_schedule = _default_repeat_schedule(schedule)
            if repeat_schedule is not None:
                storage.set_chore_repeat_reminder(scope_id, chore_name, repeat_schedule)
                storage.log_action(
                    scope_id,
                    sender,
                    "set_repeat_reminder",
                    chore_name,
                    humanize_schedule(repeat_schedule, language),
                )
            storage.log_action(
                scope_id,
                sender,
                "add_chore",
                chore_name,
                humanize_schedule(schedule, language),
            )
            return _text(
                language,
                "added",
                name=chore_name,
                interval=format_schedule_frequency(schedule, language),
            )
        existing_names = [row["name"].lower() for row in storage.list_chores(scope_id)]
        if chore_name.lower() in existing_names:
            return _text(language, "already_exists", name=chore_name)
        return _text(language, "could_not_add", name=chore_name)

    if command_lowered in {"add", "add chore", "new chore", "aufgabe", "neue aufgabe"}:
        storage.start_pending_chore_setup(scope_id, sender)
        return _with_usage_tip(storage, scope_id, sender, language, "add", _text(language, "setup_chore_name"))

    once_command = _parse_once_command(command_text)
    if once_command == "guided":
        storage.start_pending_chore_setup(scope_id, sender, one_shot=True)
        return _with_usage_tip(storage, scope_id, sender, language, "add", _text(language, "setup_chore_name"))
    if once_command is not None:
        chore_name, schedule, reminder_at_minutes = once_command
        if not chore_name:
            return _text(language, "usage_once")
        return _with_usage_tip(
            storage,
            scope_id,
            sender,
            language,
            "add",
            _continue_once_interview(
                storage,
                scope_id,
                sender,
                language,
                chore_name,
                schedule,
                reminder_at_minutes,
            ),
        )

    if command_lowered in {"task", "todo", "open", "open task", "offen", "offene aufgabe"}:
        return _text(language, "usage_task")

    open_task_name = _parse_open_task_command(command_text)
    if open_task_name is not None:
        if not open_task_name:
            return _text(language, "usage_task")
        existing_names = [row["name"].lower() for row in storage.list_chores(scope_id)]
        if open_task_name.lower() in existing_names:
            return _text(language, "already_exists", name=open_task_name)
        added = _finalize_chore_creation(
            storage,
            scope_id,
            sender,
            language,
            open_task_name,
            {"type": "none"},
            None,
            True,
            None,
        )
        return _with_usage_tip(storage, scope_id, sender, language, "add", added)

    if admin_seen and command_lowered in {"confirm add", "add confirm"}:
        pending_add = storage.get_pending_chore_add(scope_id, sender)
        if pending_add is None:
            return _text(language, "no_pending_add")
        chore_name = pending_add["name"]
        schedule = schedule_from_storage(
            pending_add["reminder_schedule"],
            pending_add["reminder_interval_minutes"],
        )
        storage.clear_pending_chore_add(scope_id)
        if storage.add_chore(scope_id, chore_name, schedule):
            repeat_schedule = _default_repeat_schedule(schedule)
            if repeat_schedule is not None:
                storage.set_chore_repeat_reminder(scope_id, chore_name, repeat_schedule)
                storage.log_action(
                    scope_id,
                    sender,
                    "set_repeat_reminder",
                    chore_name,
                    humanize_schedule(repeat_schedule, language),
                )
            storage.log_action(
                scope_id,
                sender,
                "add_chore",
                chore_name,
                humanize_schedule(schedule, language),
            )
            return _text(
                language,
                "added",
                name=chore_name,
                interval=format_schedule_frequency(schedule, language),
            )
        existing_names = [row["name"].lower() for row in storage.list_chores(scope_id)]
        if chore_name.lower() in existing_names:
            return _text(language, "already_exists", name=chore_name)
        return _text(language, "could_not_add", name=chore_name)

    add_command = _parse_add_command(command_text)
    if add_command is not None:
        chore_name, schedule, reminder_at_minutes = add_command
        if schedule is not None and is_one_shot_schedule(schedule):
            if not chore_name:
                return _text(language, "usage_once")
            return _with_usage_tip(
                storage,
                scope_id,
                sender,
                language,
                "add",
                _continue_once_interview(
                    storage,
                    scope_id,
                    sender,
                    language,
                    chore_name,
                    schedule,
                    reminder_at_minutes,
                ),
            )
        if schedule is None:
            payload = _add_command_payload(command_text)
            chore_name, _ = _split_trailing_reminder_time(payload)
            chore_name = chore_name or payload
            if not chore_name:
                return _text(language, "usage_add")
            existing_names = [row["name"].lower() for row in storage.list_chores(scope_id)]
            if chore_name.lower() in existing_names:
                return _text(language, "already_exists", name=chore_name)
            storage.start_pending_chore_setup(scope_id, sender)
            storage.update_pending_chore_setup(scope_id, sender, "schedule", chore_name, "")
            return _text(language, "setup_chore_schedule", name=chore_name)
        if not chore_name:
            return _text(language, "usage_add")
        existing_names = [row["name"].lower() for row in storage.list_chores(scope_id)]
        if chore_name.lower() in existing_names:
            return _text(language, "already_exists", name=chore_name)
        repeat_schedule = _default_repeat_schedule(schedule) if schedule["type"] != "none" else None
        added = _finalize_chore_creation(
            storage,
            scope_id,
            sender,
            language,
            chore_name,
            schedule,
            reminder_at_minutes,
            True,
            repeat_schedule,
        )
        return _with_usage_tip(storage, scope_id, sender, language, "add", added)

    confirmation_command = _parse_confirmation_command(command_text)
    if confirmation_command is not None:
        chore_name, requires_confirmation = confirmation_command
        if not chore_name:
            return _text(language, "usage_confirmation")
        if not storage.set_chore_confirmation(scope_id, chore_name, requires_confirmation):
            return _text(language, "not_found", name=chore_name)
        storage.log_action(
            scope_id,
            sender,
            "set_confirmation",
            chore_name,
            "on" if requires_confirmation else "off",
        )
        return _text(
            language,
            "confirmation_set_on" if requires_confirmation else "confirmation_set_off",
            name=chore_name,
        )

    reminder_time_command = _parse_reminder_time_command(command_text)
    if reminder_time_command is not None:
        if reminder_time_command == "invalid":
            return _text(language, "usage_reminder_time")
        chore_name, reminder_at_minutes = reminder_time_command
        canonical_name = _canonical_chore_name(storage, scope_id, chore_name)
        if canonical_name is None:
            return _text(language, "not_found", name=chore_name)
        if not storage.set_chore_reminder_time(scope_id, canonical_name, reminder_at_minutes):
            return _text(language, "not_found", name=canonical_name)
        time_label = format_reminder_time_label(reminder_at_minutes, language)
        storage.log_action(scope_id, sender, "set_reminder_time", canonical_name, time_label)
        return _text(language, "reminder_time_set", name=canonical_name, time=time_label)

    schedule_command = _parse_schedule_command(command_text)
    if schedule_command is not None:
        chore_name, schedule = schedule_command
        if not chore_name or schedule is None:
            return _text(language, "usage_schedule")
        if not storage.set_chore_schedule(scope_id, chore_name, schedule):
            return _text(language, "not_found", name=chore_name)
        storage.log_action(
            scope_id,
            sender,
            "set_schedule",
            chore_name,
            humanize_schedule(schedule, language),
        )
        return _text(
            language,
            "schedule_set",
            name=chore_name,
            interval=format_schedule_frequency(schedule, language),
        )

    repeat_command = _parse_repeat_command(command_text)
    if repeat_command is not None:
        chore_name, schedule = repeat_command
        if not chore_name or schedule is None:
            return _text(language, "usage_repeat")
        if not storage.set_chore_repeat_reminder(scope_id, chore_name, schedule):
            return _text(language, "not_found", name=chore_name)
        storage.log_action(
            scope_id,
            sender,
            "set_repeat_reminder",
            chore_name,
            humanize_schedule(schedule, language),
        )
        return _text(
            language,
            "repeat_set",
            name=chore_name,
            interval=format_schedule_delay(schedule, language),
        )

    if command_lowered in {"delete", "delete chore", "remove", "loesche", "lösche"}:
        return _text(language, "usage_delete")
    chore_name = _strip_prefixed_value(command_text, ("delete chore ", "delete ", "remove ", "loesche ", "lösche "))
    if chore_name:
        if storage.delete_chore(scope_id, chore_name):
            storage.log_action(scope_id, sender, "delete_chore", chore_name)
            return _text(language, "deleted", name=chore_name)
        return _text(language, "not_found", name=chore_name)

    payload = _strip_prefixed_value(
        command_text,
        ("change chore ", "rename ", "umbenennen "),
    )
    if payload:
        if "->" not in payload:
            return _text(language, "usage_change")
        old_name, new_name = [p.strip() for p in payload.split("->", 1)]
        if not old_name or not new_name:
            return _text(language, "usage_change")
        ok, msg = storage.rename_chore(scope_id, old_name, new_name)
        if ok:
            storage.log_action(scope_id, sender, "rename_chore", old_name, new_name)
        return _format_rename_message(ok, msg, old_name, new_name, language)

    if command_lowered.startswith("history") or command_lowered.startswith("verlauf"):
        limit = _parse_history_limit(command_text)
        rows = storage.recent_logs(scope_id=scope_id, limit=limit)
        if not rows:
            return _text(language, "no_history")
        tz_name = storage.get_timezone(scope_id)
        lines = [
            _text(
                language,
                "history_line",
                idx=idx,
                name=row["chore_name"],
                sender=storage.display_name(scope_id, row["sender"]),
                done_at=_format_list_timestamp(row["done_at"], tz_name),
            )
            for idx, row in enumerate(rows, start=1)
        ]
        return _text(language, "history_header") + "\n" + "\n".join(lines)

    if command_lowered in {"reset group", "zuruecksetzen", "zurücksetzen"}:
        if is_group and not admin_text:
            return _text(language, "admin_only")
        if not group_id:
            return _text(language, "group_only")
        token = f"{secrets.randbelow(1000000):06d}"
        storage.upsert_reset_request(scope_id, sender, token, ttl_minutes=10)
        return _text(language, "reset_requested", token=token)

    if command_lowered in {"reset group cancel", "zuruecksetzen abbrechen", "zurücksetzen abbrechen"}:
        if is_group and not admin_text:
            return _text(language, "admin_only")
        storage.clear_reset_request(scope_id)
        return _text(language, "cancelled")

    reset_confirm_prefixes = ("reset group confirm ", "zuruecksetzen bestaetigen ", "zurücksetzen bestätigen ")
    if command_lowered.startswith(reset_confirm_prefixes):
        if is_group and not admin_text:
            return _text(language, "admin_only")
        if not group_id:
            return _text(language, "group_only")
        token = ""
        for prefix in reset_confirm_prefixes:
            if command_lowered.startswith(prefix):
                token = command_text[len(prefix):].strip()
                break
        if not token:
            return _text(language, "usage_reset_confirm")
        if not storage.validate_reset_request(scope_id, sender, token):
            return _text(language, "reset_failed")
        storage.reset_scope(scope_id)
        storage.clear_reset_request(scope_id)
        storage.log_action(scope_id, sender, "reset_group")
        return _text(language, "reset_done")

    guess = _guess_command(command_text, language)
    if guess:
        return _text(language, "did_you_mean", command=guess)
    return ""
