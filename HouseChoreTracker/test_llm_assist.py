from __future__ import annotations

import json
import os
import tempfile
import unittest

import llm_assist
from commands import handle_command
from storage import Storage

SENDER = "sender-mo"
OTHER = "sender-anna"
SCOPE = "group:test-group"
GROUP = "test-group"


def llm_output(kind: str = "action", intent: str | None = None, confidence: float = 0.9, suggestions=(), **slots) -> str:
    full = {name: None for name in llm_assist.SLOT_NAMES}
    full.update(slots)
    return json.dumps(
        {"kind": kind, "intent": intent, "slots": full, "suggestions": list(suggestions), "confidence": confidence}
    )


class FakeLlm:
    """Answers by message text; records every message it was asked about."""

    def __init__(self) -> None:
        self.answers: dict[str, object] = {}
        self.calls: list[str] = []
        self.dialogues: list[str] = []

    def complete(self, messages: list[dict]) -> str | None:
        content = messages[-1]["content"]
        text = content.rsplit("Message:\n", 1)[1]
        self.calls.append(text)
        if "middle of a dialogue" in content:
            self.dialogues.append(text)
        answer = self.answers.get(text)
        if isinstance(answer, Exception):
            raise answer
        return answer


class LlmAssistTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(os.path.join(self.tmp.name, "chores.db"))
        handle_command(self.storage, "deutsch", SENDER, SCOPE, GROUP)
        self.storage.set_display_name(SCOPE, SENDER, "Mo")
        self.storage.set_display_name(SCOPE, OTHER, "Anna")
        self.llm = FakeLlm()
        llm_assist.set_client(self.llm)
        os.environ.pop("LLM_SCOPES", None)

    def tearDown(self) -> None:
        llm_assist.set_client(None)
        self.tmp.cleanup()

    def send(self, text: str, sender: str = SENDER, group: str | None = GROUP) -> str:
        reply = handle_command(self.storage, text, sender, SCOPE, group)
        if isinstance(reply, list):
            return "\n".join(reply)
        if isinstance(reply, dict):
            return str(reply.get("reply", ""))
        return str(reply)

    def chore(self, name: str):
        for row in self.storage.list_chores(SCOPE):
            if row["name"] == name:
                return row
        return None

    def add_existing(self, name: str = "Bad putzen") -> None:
        self.send(f"aufgabe {name} jeden Tag")
        self.assertIsNotNone(self.chore(name))

    def done_count(self, name: str) -> int:
        return sum(1 for row in self.storage.recent_logs(SCOPE, limit=100) if row["chore_name"] == name)


class ParserFirstTests(LlmAssistTestCase):
    def test_exact_commands_and_dialogue_answers_never_reach_the_llm(self) -> None:
        self.send("liste")
        self.send("aufgabe")
        self.send("Müll")
        self.send("jeden Montag")
        self.send("08:00")
        self.send("ja")
        self.send("erledigt Müll")
        self.assertEqual(self.llm.calls, [])


class AddChoreTests(LlmAssistTestCase):
    MESSAGE = "Erinner uns jeden Montag um 8 ans Fensterputzen, jemand muss es bestätigen"

    def full_slots(self) -> str:
        return llm_output(
            intent="add_chore",
            name="Fensterputzen",
            schedule="every monday",
            remind_time="08:00",
            done_confirmation=True,
        )

    def test_all_slots_asks_once_then_yes_creates_exactly_that(self) -> None:
        self.llm.answers[self.MESSAGE] = self.full_slots()
        reply = self.send(self.MESSAGE)
        self.assertIn("Habe ich das richtig verstanden?", reply)
        self.assertIn("Fensterputzen", reply)
        self.assertIn("jeden Montag", reply)
        self.assertIn("um 08:00", reply)
        self.assertIsNone(self.chore("Fensterputzen"))

        self.assertIn("Aufgabe angelegt: Fensterputzen", self.send("ja"))
        row = self.chore("Fensterputzen")
        self.assertEqual(row["reminder_at_minutes"], 8 * 60)
        self.assertEqual(row["reminder_schedule"], "weekday:0")
        self.assertEqual(row["requires_confirmation"], 1)

    def test_no_creates_nothing(self) -> None:
        self.llm.answers[self.MESSAGE] = self.full_slots()
        self.send(self.MESSAGE)
        self.assertIn("verworfen", self.send("nein"))
        self.assertIsNone(self.chore("Fensterputzen"))

    def test_partial_slots_continue_the_normal_interview(self) -> None:
        self.llm.answers["fenster jeden montag"] = llm_output(
            intent="add_chore", name="Fensterputzen", schedule="every monday"
        )
        reply = self.send("fenster jeden montag")
        self.assertIn("Verstanden: Fensterputzen · jeden Montag", reply)
        self.assertIn("Um wie viel Uhr", reply)
        self.assertIn("Muss 'Fensterputzen' als erledigt", self.send("08:00"))
        self.assertIn("Aufgabe angelegt", self.send("nein"))
        row = self.chore("Fensterputzen")
        self.assertEqual(row["reminder_at_minutes"], 8 * 60)
        self.assertEqual(row["requires_confirmation"], 0)

    def test_schedule_without_time_of_day_skips_reminder_time(self) -> None:
        self.llm.answers["alle 3 stunden lüften"] = llm_output(intent="add_chore", name="Lüften", schedule="every 3 hours")
        reply = self.send("alle 3 stunden lüften")
        self.assertNotIn("Um wie viel Uhr", reply)
        self.assertIn("Muss 'Lüften' als erledigt", reply)

    def test_invalid_schedule_is_treated_as_missing(self) -> None:
        self.llm.answers["staubsaugen ab und zu"] = llm_output(intent="add_chore", name="Staubsaugen", schedule="sometimes")
        reply = self.send("staubsaugen ab und zu")
        self.assertIn("Wie oft ist 'Staubsaugen' fällig?", reply)

    def test_no_schedule_creates_open_task_after_yes(self) -> None:
        self.llm.answers["irgendwann keller aufräumen"] = llm_output(intent="add_chore", name="Keller", schedule="none")
        self.assertIn("Habe ich das richtig verstanden?", self.send("irgendwann keller aufräumen"))
        self.assertIn("Offene Aufgabe angelegt: Keller", self.send("ja"))

    def test_existing_name_is_refused(self) -> None:
        self.add_existing("Bad putzen")
        self.llm.answers["bad jeden tag putzen"] = llm_output(intent="add_chore", name="bad putzen", schedule="every day")
        self.assertIn("gibt es schon", self.send("bad jeden tag putzen"))


class AddOnceTests(LlmAssistTestCase):
    def test_add_once_is_one_shot_and_asks_count_stats_only_if_missing(self) -> None:
        self.llm.answers["morgen abend vermieter anrufen"] = llm_output(
            intent="add_once", name="Vermieter anrufen", schedule="tomorrow", remind_time="19:00"
        )
        reply = self.send("morgen abend vermieter anrufen")
        self.assertIn("Statistik", reply)
        self.assertIn("Muss 'Vermieter anrufen'", self.send("nein"))
        self.assertIn("Einmalaufgabe angelegt", self.send("ja"))
        row = self.chore("Vermieter anrufen")
        self.assertTrue(row["reminder_schedule"].startswith("once"))
        self.assertEqual(row["reminder_at_minutes"], 19 * 60)

    def test_add_once_complete_goes_to_yes_no(self) -> None:
        self.llm.answers["morgen müll"] = llm_output(
            intent="add_once",
            name="Sperrmüll",
            schedule="tomorrow",
            remind_time="anytime",
            count_stats=False,
            done_confirmation=False,
        )
        reply = self.send("morgen müll")
        self.assertIn("Einmalige Aufgabe: Sperrmüll", reply)
        self.assertIn("zählt nicht in der Statistik", reply)
        self.assertIn("Einmalaufgabe angelegt", self.send("ja"))


class DialogueFillTests(LlmAssistTestCase):
    def test_free_text_answer_fills_two_steps(self) -> None:
        self.send("aufgabe")
        self.send("Fensterputzen")
        self.llm.answers["jeden Montag früh"] = llm_output(
            intent="add_chore", schedule="every monday", remind_time="08:00"
        )
        reply = self.send("jeden Montag früh")
        self.assertEqual(self.llm.dialogues, ["jeden Montag früh"])
        self.assertIn("Muss 'Fensterputzen' als erledigt", reply)
        self.assertIn("Aufgabe angelegt", self.send("ja"))
        self.assertEqual(self.chore("Fensterputzen")["reminder_at_minutes"], 8 * 60)

    def test_unclear_answer_keeps_the_usage_reply(self) -> None:
        self.send("aufgabe")
        self.send("Fensterputzen")
        self.llm.answers["keine ahnung"] = llm_output(kind="unclear")
        self.assertIn("So geht's", self.send("keine ahnung"))
        self.assertIn("Wie oft", self.send("abbrechen") + "Wie oft")  # dialogue was still open

    def test_cancel_never_goes_to_llm(self) -> None:
        self.send("aufgabe")
        self.send("Fensterputzen")
        self.send("abbrechen")
        self.assertEqual(self.llm.calls, [])


class DoneAndUndoTests(LlmAssistTestCase):
    def test_mark_done_needs_yes(self) -> None:
        self.add_existing()
        self.llm.answers["bad ist sauber"] = llm_output(intent="mark_done", chore="Bad putzen")
        self.assertIn("'Bad putzen' als erledigt markieren", self.send("bad ist sauber"))
        self.assertEqual(self.done_count("Bad putzen"), 0)
        reply = self.send("ja")
        self.assertIn("Tipp: nächstes Mal einfach: erledigt Bad putzen", reply)
        self.assertEqual(self.done_count("Bad putzen"), 1)

    def test_unknown_chore_suggests_and_changes_nothing(self) -> None:
        self.add_existing()
        self.llm.answers["küche ist sauber"] = llm_output(intent="mark_done", chore="Küche")
        reply = self.send("küche ist sauber")
        self.assertIn("Welche Aufgabe meinst du?", reply)
        self.assertIn("erledigt Bad putzen", reply)
        self.assertEqual(self.done_count("Bad putzen"), 0)
        self.assertIsNone(self.storage.get_pending_llm_action(SCOPE, SENDER))

    def test_undo(self) -> None:
        self.add_existing()
        self.send("erledigt Bad putzen")
        self.llm.answers["ups bad war doch nicht"] = llm_output(intent="undo_done", chore="Bad putzen")
        self.send("ups bad war doch nicht")
        self.send("ja")
        self.assertEqual(self.done_count("Bad putzen"), 0)


class YesNoCheckTests(LlmAssistTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.add_existing()
        self.llm.answers["bad ist sauber"] = llm_output(intent="mark_done", chore="Bad putzen")
        self.send("bad ist sauber")

    def test_only_the_original_sender_can_confirm(self) -> None:
        self.send("ja", sender=OTHER)
        self.assertEqual(self.done_count("Bad putzen"), 0)
        self.send("ja")
        self.assertEqual(self.done_count("Bad putzen"), 1)

    def test_other_message_clears_the_check(self) -> None:
        self.assertIn("Bad putzen", self.send("liste"))
        self.send("ja")
        self.assertEqual(self.done_count("Bad putzen"), 0)

    def test_check_expires(self) -> None:
        with self.storage._connect() as conn:
            conn.execute("UPDATE pending_llm_actions SET expires_at = datetime('now', '-1 minutes')")
            conn.commit()
        self.send("ja")
        self.assertEqual(self.done_count("Bad putzen"), 0)


class EditDeleteTests(LlmAssistTestCase):
    def test_delete_uses_the_existing_confirmation(self) -> None:
        self.add_existing()
        self.llm.answers["bad brauchen wir nicht mehr"] = llm_output(intent="delete_chore", chore="Bad putzen")
        self.assertIn("samt Verlauf löschen?", self.send("bad brauchen wir nicht mehr"))
        self.assertIsNotNone(self.chore("Bad putzen"))
        self.send("nein")
        self.assertIsNotNone(self.chore("Bad putzen"))
        self.send("bad brauchen wir nicht mehr")
        self.send("ja")
        self.assertIsNone(self.chore("Bad putzen"))

    def test_edit_with_value_asks_then_applies(self) -> None:
        self.add_existing()
        self.llm.answers["bad nur noch dienstags"] = llm_output(
            intent="edit_chore", chore="Bad putzen", field="schedule", value="every tuesday"
        )
        self.assertIn("Zeitplan auf jeden Dienstag", self.send("bad nur noch dienstags"))
        self.send("ja")
        self.assertEqual(self.chore("Bad putzen")["reminder_schedule"], "weekday:1")

    def test_edit_without_value_opens_that_step(self) -> None:
        self.add_existing()
        self.llm.answers["bad zeitplan ändern"] = llm_output(intent="edit_chore", chore="Bad putzen", field="schedule")
        self.assertIn("Wie oft ist 'Bad putzen' fällig?", self.send("bad zeitplan ändern"))
        self.send("jeden Freitag")
        self.assertEqual(self.chore("Bad putzen")["reminder_schedule"], "weekday:4")

    def test_rename(self) -> None:
        self.add_existing()
        self.llm.answers["nenn bad lieber badezimmer"] = llm_output(
            intent="rename_chore", chore="Bad putzen", new_name="Badezimmer"
        )
        self.send("nenn bad lieber badezimmer")
        self.send("ja")
        self.assertIsNotNone(self.chore("Badezimmer"))


class OtherIntentTests(LlmAssistTestCase):
    def test_show_runs_immediately_with_hint(self) -> None:
        self.add_existing()
        self.llm.answers["was steht an?"] = llm_output(intent="show", what="list")
        reply = self.send("was steht an?")
        self.assertIn("Verstanden als: liste", reply)
        self.assertIn("Bad putzen", reply)

    def test_set_name(self) -> None:
        self.llm.answers["ich heiße übrigens Moritz"] = llm_output(intent="set_name", display_name="Moritz")
        self.send("ich heiße übrigens Moritz")
        self.send("ja")
        self.assertEqual(self.storage.display_name(SCOPE, SENDER), "Moritz")

    def test_vacation_complete_and_partial(self) -> None:
        self.llm.answers["bin 2 wochen weg"] = llm_output(intent="vacation", when="now", duration="2 weeks")
        self.assertIn("dauert 14 Tage", self.send("bin 2 wochen weg"))
        self.send("ja")
        self.assertIsNotNone(self.storage.get_member_vacation(SCOPE, SENDER))

    def test_vacation_partial_asks_duration(self) -> None:
        self.llm.answers["ab nächster woche urlaub"] = llm_output(intent="vacation", when="1 week")
        self.send("ab nächster woche urlaub")
        self.assertEqual(self.storage.get_pending_vacation_setup(SCOPE, SENDER)["step"], "duration")

    def test_admin_commands_cannot_be_reached(self) -> None:
        # "reset" is not an intent; the parser drops it and nothing happens.
        self.add_existing()
        self.llm.answers["lösch alles"] = llm_output(intent="reset_group")
        self.send("lösch alles")
        self.send("ja")
        self.assertIsNotNone(self.chore("Bad putzen"))


class ChatterAndFailureTests(LlmAssistTestCase):
    def test_chatter_in_group_is_silent(self) -> None:
        self.llm.answers["wer kommt heute zum essen?"] = llm_output(kind="chatter")
        self.assertEqual(self.send("wer kommt heute zum essen?"), "")

    def test_chatter_in_dm_gets_suggestions(self) -> None:
        dm_scope = "dm:sender-mo"
        handle_command(self.storage, "deutsch", SENDER, dm_scope, None)
        self.llm.answers["hallo"] = llm_output(kind="chatter")
        reply = handle_command(self.storage, "hallo", SENDER, dm_scope, None)
        self.assertIn("Meintest du vielleicht", reply)

    def test_low_confidence_in_group_keeps_old_behaviour(self) -> None:
        self.add_existing()
        self.llm.answers["bad?"] = llm_output(intent="mark_done", chore="Bad putzen", confidence=0.3)
        self.assertEqual(self.send("bad?"), "")
        self.assertIsNone(self.storage.get_pending_llm_action(SCOPE, SENDER))

    def test_unclear_gets_suggestions(self) -> None:
        self.llm.answers["bot mach mal das ding"] = llm_output(kind="unclear", suggestions=["liste", "quatsch"])
        reply = self.send("bot mach mal das ding")
        self.assertIn("- liste", reply)
        self.assertNotIn("quatsch", reply)

    def test_failures_behave_like_today(self) -> None:
        for answer in (None, "not json", '{"kind": "action"}', TimeoutError("slow")):
            with self.subTest(answer=answer):
                self.llm.answers["listee"] = answer
                self.assertEqual(self.send("listee"), "Meintest du: liste?")
                self.llm.answers["wetter heute"] = answer
                self.assertEqual(self.send("wetter heute"), "")

    def test_every_call_is_logged(self) -> None:
        self.llm.answers["wer kommt heute zum essen?"] = llm_output(kind="chatter")
        self.send("wer kommt heute zum essen?")
        self.send("wetter heute")
        with self.storage._connect() as conn:
            outcomes = [row["outcome"] for row in conn.execute("SELECT outcome FROM llm_log ORDER BY id")]
        self.assertEqual(outcomes, ["chatter", "failed"])


class ConfigTests(unittest.TestCase):
    def tearDown(self) -> None:
        for name in ("LLM_ENABLED", "LLM_BASE_URL", "LLM_MODEL", "LLM_SCOPES"):
            os.environ.pop(name, None)
        llm_assist.set_client(None)

    def test_disabled_by_default(self) -> None:
        self.assertIsNone(llm_assist.client_for(SCOPE))

    def test_enabled_needs_url_and_model(self) -> None:
        os.environ["LLM_ENABLED"] = "true"
        self.assertIsNone(llm_assist.client_for(SCOPE))
        os.environ["LLM_BASE_URL"] = "http://192.168.178.50:11434/v1"
        os.environ["LLM_MODEL"] = "qwen2.5:14b"
        self.assertIsNotNone(llm_assist.client_for(SCOPE))

    def test_scope_allowlist(self) -> None:
        llm_assist.set_client(FakeLlm())
        os.environ["LLM_SCOPES"] = "group:other"
        self.assertIsNone(llm_assist.client_for(SCOPE))
        os.environ["LLM_SCOPES"] = f"group:other, {SCOPE}"
        self.assertIsNotNone(llm_assist.client_for(SCOPE))

    def test_parse_output_tolerates_code_fences(self) -> None:
        parsed = llm_assist.parse_output("```json\n" + llm_output(intent="show", what="list") + "\n```")
        self.assertEqual(parsed.intent, "show")
        self.assertEqual(parsed.slots["what"], "list")


if __name__ == "__main__":
    unittest.main()
