from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

import llm_assist
from test_llm_assist import GROUP, SCOPE, SENDER, llm_output

_TMP = tempfile.TemporaryDirectory()
os.environ.setdefault("SIGNAL_BOT_NUMBER", "+10000000000")
os.environ["DATABASE_PATH"] = os.path.join(_TMP.name, "chores.db")
import app as chore_app  # noqa: E402  (needs the env above)


def _response(payload: dict) -> mock.Mock:
    response = mock.Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _ps(*names: str) -> mock.Mock:
    return _response({"models": [{"name": name, "model": name} for name in names]})


def _chat(content: str) -> mock.Mock:
    return _response({"choices": [{"message": {"content": content}}]})


class ClientColdCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = llm_assist.LlmClient("http://mini:11434/v1", "qwen3.6:35b", 20.0)
        llm_assist.warming.clear()

    def tearDown(self) -> None:
        llm_assist.warming.clear()

    def test_loaded_model_answers_with_normal_timeout(self) -> None:
        with mock.patch("requests.get", return_value=_ps("qwen3.6:35b")) as get, mock.patch(
            "requests.post", return_value=_chat("{}")
        ) as post:
            self.assertEqual(self.client.complete([]), "{}")
        self.assertEqual(get.call_args.args[0], "http://mini:11434/api/ps")
        self.assertEqual(post.call_args.kwargs["timeout"], 20.0)

    def test_cold_model_raises_without_calling_chat(self) -> None:
        with mock.patch("requests.get", return_value=_ps()), mock.patch("requests.post") as post:
            with self.assertRaises(llm_assist.ModelCold):
                self.client.complete([])
        post.assert_not_called()

    def test_warming_queues_even_if_model_shows_loaded(self) -> None:
        llm_assist.warming.set()
        with mock.patch("requests.get", return_value=_ps("qwen3.6:35b")), mock.patch("requests.post") as post:
            with self.assertRaises(llm_assist.ModelCold):
                self.client.complete([])
        post.assert_not_called()

    def test_cold_start_allowed_waits_with_long_timeout(self) -> None:
        with mock.patch("requests.get") as get, mock.patch("requests.post", return_value=_chat("{}")) as post:
            with llm_assist.cold_start_allowed():
                self.assertEqual(self.client.complete([]), "{}")
        get.assert_not_called()
        self.assertEqual(post.call_args.kwargs["timeout"], 120.0)

    def test_failed_load_check_counts_as_loaded(self) -> None:
        with mock.patch("requests.get", side_effect=OSError("down")), mock.patch(
            "requests.post", return_value=_chat("{}")
        ) as post:
            self.assertEqual(self.client.complete([]), "{}")
        post.assert_called_once()


class ColdFakeLlm:
    """Cold until cold_start_allowed() is used, then answers like the real model would."""

    def __init__(self, answer: str) -> None:
        self.answer = answer

    def complete(self, messages: list[dict]) -> str | None:
        if not getattr(llm_assist._local, "allow_cold", False):
            raise llm_assist.ModelCold()
        return self.answer


class AppDeferTests(unittest.TestCase):
    def setUp(self) -> None:
        self.http = chore_app.app.test_client()
        self.post("deutsch")
        chore_app.storage.set_display_name(SCOPE, SENDER, "Mo")
        llm_assist.warming.clear()
        self.sent: list[tuple] = []
        patcher = mock.patch.object(chore_app, "_queue_signal_reply", lambda *args: self.sent.append(args))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(llm_assist.set_client, None)
        self.addCleanup(llm_assist.warming.clear)

    def post(self, message: str) -> dict:
        body = {"scope_id": SCOPE, "sender": SENDER, "message": message, "group_id": GROUP}
        return self.http.post("/internal/handle", json=body).get_json()

    def drain(self) -> None:
        while not chore_app.deferred_messages.empty():
            worker_once()

    def test_cold_message_gets_notice_then_answer(self) -> None:
        llm_assist.set_client(ColdFakeLlm(llm_output(intent="show", what="list")))
        first = self.post("was steht noch an?")
        self.assertIn("Kaltstart", first["reply"])
        second = self.post("und sonst so?")
        self.assertEqual(second["reply"], "")
        self.assertTrue(llm_assist.warming.is_set())
        self.drain()
        self.assertFalse(llm_assist.warming.is_set())
        self.assertEqual(len(self.sent), 2)
        self.assertTrue(all(args[0] == GROUP and args[1] == SENDER for args in self.sent))

    def test_parsed_commands_skip_the_llm(self) -> None:
        llm_assist.set_client(ColdFakeLlm(""))
        reply = self.post("liste")
        self.assertNotIn("Kaltstart", str(reply))
        self.assertTrue(chore_app.deferred_messages.empty())


def worker_once() -> None:
    """One iteration of app._run_deferred_loop (the real loop never returns)."""
    stop = RuntimeError("stop")
    original_get = chore_app.deferred_messages.get
    calls = {"n": 0}

    def get_once():
        calls["n"] += 1
        if calls["n"] > 1:
            raise stop
        return original_get()

    with mock.patch.object(chore_app.deferred_messages, "get", get_once):
        try:
            chore_app._run_deferred_loop()
        except RuntimeError as exc:
            if exc is not stop:
                raise


if __name__ == "__main__":
    unittest.main()
