"""
Latency report — pulls every real call made against the assistant from
Vapi's own API and reports median/p95 round-trip time for each tool call.

Note: this reads from Vapi's call logs directly rather than the backend's
own turn_logs table. turn_logs exists in the schema for a future
self-hosted latency pipeline, but nothing currently writes to it — every
tool call's timing so far has only gone to stdout via logger.info(), not
the database. Rather than fabricate numbers from an empty table, this
script uses the real, already-recorded timing Vapi captured on every
actual call made tonight.

Usage:
    export VAPI_API_KEY="your-vapi-private-key"
    python scripts/latency_report.py
"""
import os
import sys
import statistics
from datetime import datetime

import requests

VAPI_API_KEY = os.environ.get("VAPI_API_KEY")
if not VAPI_API_KEY:
    sys.exit("Set VAPI_API_KEY first: export VAPI_API_KEY=your-vapi-private-key")

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

HEADERS = {"Authorization": f"Bearer {VAPI_API_KEY}"}


def fetch_calls():
    resp = requests.get("https://api.vapi.ai/call", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_call_detail(call_id: str):
    resp = requests.get(f"https://api.vapi.ai/call/{call_id}", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def extract_tool_latencies(call_detail: dict):
    """Walks a call's message log and pairs each tool_calls request with its
    tool_call_result, returning round-trip latency in ms per tool invocation.

    Real Vapi message shapes (confirmed against a live call):
      {"role": "tool_calls", "secondsFromStart": 12.07,
       "toolCalls": [{"id": "toolu_...", "function": {"name": "lookup_guest"}}]}
      {"role": "tool_call_result", "secondsFromStart": 13.37,
       "toolCallId": "toolu_...", "name": "lookup_guest", "result": "..."}

    Latency here is end-to-end from the model deciding to call the tool to
    the result being available — this includes network hops to ngrok/Railway
    and back, not just the backend's own processing time, which is the
    number that actually matters for how a caller experiences the pause.
    """
    messages = call_detail.get("messages") or call_detail.get("artifact", {}).get("messages", [])
    latencies = []
    pending = {}  # toolCallId -> {"time": seconds_from_start, "name": tool name}

    for msg in messages:
        role = msg.get("role")
        seconds = msg.get("secondsFromStart")

        if role == "tool_calls":
            for tc in msg.get("toolCalls", []):
                call_id = tc.get("id")
                name = (tc.get("function") or {}).get("name", "unknown")
                if call_id and seconds is not None:
                    pending[call_id] = {"time": seconds, "name": name}

        elif role == "tool_call_result":
            call_id = msg.get("toolCallId")
            if call_id and call_id in pending and seconds is not None:
                start = pending.pop(call_id)
                delta_ms = (float(seconds) - float(start["time"])) * 1000
                if delta_ms >= 0:
                    latencies.append({"tool": start["name"], "latency_ms": delta_ms})

    return latencies


def main():
    print("Fetching calls from Vapi...")
    calls = fetch_calls()

    if not calls:
        sys.exit("No calls found on this Vapi account yet — make at least one test call first.")

    limit = os.environ.get("CALL_LIMIT")
    if limit:
        calls = calls[: int(limit)]
        print(f"(limited to the {len(calls)} most recent calls)")

    all_latencies = []
    per_call_summary = []

    for call in calls:
        call_id = call.get("id")
        if not call_id:
            continue
        detail = fetch_call_detail(call_id)
        latencies = extract_tool_latencies(detail)
        all_latencies.extend(latencies)
        per_call_summary.append(
            {
                "call_id": call_id,
                "started_at": call.get("startedAt", "?"),
                "cost": call.get("cost"),
                "tool_calls": len(latencies),
            }
        )

    if not all_latencies:
        print(
            "\nNo tool-call timing could be extracted from Vapi's message logs "
            "for these calls."
        )
        sys.exit(1)

    values = [l["latency_ms"] for l in all_latencies]
    median = statistics.median(values)
    p95 = statistics.quantiles(values, n=20)[18] if len(values) >= 20 else max(values)

    print(f"\n{len(all_latencies)} tool calls across {len(per_call_summary)} calls")
    print(f"Median tool round-trip: {median:.0f} ms")
    print(f"P95 tool round-trip:    {p95:.0f} ms")

    by_tool = {}
    for l in all_latencies:
        by_tool.setdefault(l["tool"], []).append(l["latency_ms"])

    print("\nBy tool:")
    for tool, vals in sorted(by_tool.items()):
        print(f"  {tool}: median {statistics.median(vals):.0f} ms  (n={len(vals)})")

    report_path = os.path.join(os.path.dirname(__file__), "..", "latency_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Latency report\n\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"**Median tool round-trip: {median:.0f} ms**\n\n")
        f.write(f"**P95 tool round-trip: {p95:.0f} ms**\n\n")
        f.write(f"Based on {len(all_latencies)} tool calls across {len(per_call_summary)} real calls.\n\n")
        f.write("## By tool\n\n| Tool | Median (ms) | Calls |\n|---|---|---|\n")
        for tool, vals in sorted(by_tool.items()):
            f.write(f"| {tool} | {statistics.median(vals):.0f} | {len(vals)} |\n")
    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()