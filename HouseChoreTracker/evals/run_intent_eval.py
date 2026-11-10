"""Run the intent eval against a real model.

    python evals/run_intent_eval.py --base-url http://<macmini-ip>:11434/v1 --model qwen2.5:14b [--model other ...]

Slots are compared after running them through the bot's own parsers, so
"every Monday" and "jeden montag" count as the same schedule. Needs `requests`.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import llm_assist  # noqa: E402
from schedule_utils import parse_reminder_time_answer, parse_schedule  # noqa: E402
from vacation_utils import parse_duration  # noqa: E402


def _norm_text(value: object) -> object:
    return " ".join(str(value).casefold().split()) if isinstance(value, str) else value


def _norm_slot(name: str, value: object, intent: str | None) -> object:
    if value is None or isinstance(value, bool):
        return value
    text = str(value)
    if name == "schedule":
        parsed = parse_schedule(text)
        if intent == "add_once" and parsed is not None and parsed.get("type") == "interval":
            return ("once-in", parsed["value"], parsed["unit"])
        if intent == "add_once" and parsed is not None and parsed.get("type") == "weekday":
            return ("once-weekday", parsed["weekday"])
        return parsed if parsed is not None else _norm_text(text)
    if name == "remind_time":
        return parse_reminder_time_answer(text)
    if name in {"when", "duration"}:
        if text.strip().lower() in {"now", "jetzt", "sofort"}:
            return 0
        parsed = parse_duration(text[3:] if text.lower().startswith("in ") else text)
        return parsed.total_seconds() if parsed is not None else _norm_text(text)
    if name == "value":
        for parser in (parse_schedule, parse_reminder_time_answer):
            parsed = parser(text)
            if parsed not in (None, "invalid"):
                return parsed
        lowered = text.strip().lower()
        if lowered in {"yes", "ja", "true", "on"}:
            return True
        if lowered in {"no", "nein", "false", "off"}:
            return False
    return _norm_text(text)


def run(base_url: str, model: str, cases: list[dict], timeout: float, verbose: bool) -> dict:
    client = llm_assist.LlmClient(base_url, model, timeout)
    latencies: list[int] = []
    intent_ok = slots_ok = failures = 0
    chatter_total = chatter_answered = 0
    misses: list[str] = []
    for case in cases:
        expect = case["expect"]
        result, raw, latency_ms = llm_assist.interpret(
            client, case["text"], case["language"], case["chores"], case.get("group", True), case.get("dialogue")
        )
        latencies.append(latency_ms)
        if result is None:
            failures += 1
            misses.append(f"FAILED   {case['text']!r}: {raw[:200]!r}")
            continue
        if expect["kind"] == "chatter":
            chatter_total += 1
            answered = result.kind != "chatter" and result.confidence >= llm_assist.group_min_confidence()
            chatter_answered += answered
            if answered:
                misses.append(f"CHATTER  {case['text']!r} -> {result.kind}/{result.intent} ({result.confidence:.2f})")
        same_intent = result.kind == expect["kind"] and result.intent == expect["intent"]
        intent_ok += same_intent
        if not same_intent:
            if expect["kind"] != "chatter":
                misses.append(
                    f"INTENT   {case['text']!r}: want {expect['kind']}/{expect['intent']}, got {result.kind}/{result.intent}"
                )
            continue
        wrong = {
            name: (want, result.slots.get(name))
            for name, want in expect["slots"].items()
            if _norm_slot(name, want, expect["intent"]) != _norm_slot(name, result.slots.get(name), expect["intent"])
        }
        if wrong:
            misses.append(f"SLOTS    {case['text']!r}: " + ", ".join(f"{k} want {w!r} got {g!r}" for k, (w, g) in wrong.items()))
        else:
            slots_ok += 1
        if verbose:
            print(f"  {latency_ms:5d} ms  {case['text']!r} -> {result.kind}/{result.intent} {result.slots}")

    latencies.sort()
    total = len(cases)
    return {
        "model": model,
        "cases": total,
        "intent_accuracy": intent_ok / total,
        "slots_fully_correct": slots_ok / total,
        "chatter_answered": chatter_answered / chatter_total if chatter_total else 0.0,
        "failures": failures,
        "p50_ms": statistics.median(latencies) if latencies else 0,
        "p95_ms": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else 0,
        "misses": misses,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"))
    parser.add_argument("--model", action="append", help="repeat to compare several models")
    parser.add_argument("--cases", default=os.path.join(HERE, "intent_cases.jsonl"))
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--only", help="run only cases whose text contains this")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    models = args.model or [os.getenv("LLM_MODEL", "")]
    if not models[0]:
        parser.error("give --model (or set LLM_MODEL)")

    with open(args.cases, encoding="utf-8") as handle:
        cases = [json.loads(line) for line in handle if line.strip()]
    if args.only:
        cases = [case for case in cases if args.only.lower() in case["text"].lower()]

    summaries = []
    for model in models:
        print(f"\n=== {model} ({len(cases)} cases) ===")
        summary = run(args.base_url, model, cases, args.timeout, args.verbose)
        for line in summary["misses"]:
            print("  " + line)
        summaries.append(summary)

    print("\nmodel                          intent  slots  chatter-answered  fail  p50ms  p95ms")
    for s in summaries:
        print(
            f"{s['model']:<30} {s['intent_accuracy']:6.0%} {s['slots_fully_correct']:6.0%} "
            f"{s['chatter_answered']:17.0%} {s['failures']:5d} {s['p50_ms']:6.0f} {s['p95_ms']:6.0f}"
        )
    print("targets                          ≥90%   ≥85%               ≈0%            <3000")


if __name__ == "__main__":
    main()
