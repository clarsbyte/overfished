"""Local tester for the Claude-Haiku AI vessel call — no Twilio required.

Two modes:

1. ``python test_ai_call.py``
       Interactive REPL. Plays the warning to stdout, then loops:
       you type a question, Claude Haiku answers from the PDF.
       Type ``quit`` / ``goodbye`` / Ctrl-D to end.

2. ``python test_ai_call.py --webhook``
       Replays the Twilio webhook flow end-to-end via FastAPI's TestClient.
       Prints the TwiML that Twilio would receive on each turn.
       Useful for verifying the routes before pointing ngrok at the server.

Both modes default to:
    case_id  = SCB-2026-0425-001
    document = cease_and_desist_order.pdf
    vessel   = LU RONG YUAN YU 666 / MMSI 412345678
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")  # backend/.env — ANTHROPIC_API_KEY etc.

import comms_lookup

DEMO_VESSEL = "LU RONG YUAN YU 666"
DEMO_MMSI = "412345678"
DEMO_CASE = "SCB-2026-0425-001"
DEMO_DOC = "cease_and_desist_order.pdf"


def repl() -> int:
    print(f"Loading evidence PDF: {DEMO_CASE}/{DEMO_DOC}")
    try:
        sess = comms_lookup.register_call_session(
            "LOCAL_REPL_SID",
            vessel_name=DEMO_VESSEL,
            mmsi=DEMO_MMSI,
            case_id=DEMO_CASE,
            doc_filename=DEMO_DOC,
        )
    except FileNotFoundError as exc:
        print(f"  FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"  loaded {len(sess['evidence']):,} chars of evidence text")
    print()
    print("=" * 60)
    print(comms_lookup.build_warning_text(DEMO_VESSEL))
    print("=" * 60)
    print('  (type a question, or "quit"/"goodbye" to end)')
    print()

    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        if user.lower() in {"quit", "exit", "goodbye", "bye"}:
            print("  Acknowledged. Comply with the order. Goodbye.")
            break
        try:
            reply = comms_lookup.haiku_respond("LOCAL_REPL_SID", user)
        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            continue
        print(f"AI > {reply}")
        print()
    return 0


def webhook_replay() -> int:
    from fastapi.testclient import TestClient

    import api.main as m

    client = TestClient(m.app)
    qs = (
        f"vessel_name={DEMO_VESSEL.replace(' ', '%20')}"
        f"&mmsi={DEMO_MMSI}"
        f"&case_id={DEMO_CASE}"
        f"&doc={DEMO_DOC}"
    )

    print(f"POST /twilio/voice/start?{qs}")
    r = client.post(
        f"/twilio/voice/start?{qs}",
        data={"CallSid": "CAlocaltest", "From": "+15550000", "To": "+15551111"},
    )
    print(f"  -> {r.status_code}")
    print(r.text)
    print()

    while True:
        try:
            user = input("speech> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        print(f"POST /twilio/voice/respond?{qs}  SpeechResult={user!r}")
        r = client.post(
            f"/twilio/voice/respond?{qs}",
            data={"CallSid": "CAlocaltest", "SpeechResult": user},
        )
        print(f"  -> {r.status_code}")
        print(r.text)
        print()
        if "<Hangup" in r.text:
            break
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--webhook",
        action="store_true",
        help="Replay the Twilio TwiML webhook flow instead of the plain REPL.",
    )
    args = parser.parse_args()
    return webhook_replay() if args.webhook else repl()


if __name__ == "__main__":
    sys.exit(main())
