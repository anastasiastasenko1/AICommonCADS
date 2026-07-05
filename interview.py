"""Bootstrap interview: Critical Decision Method, LLM-led, in the terminal.

Used once per workflow to seed the model. Short by design (~10 minutes):
pick one non-routine incident, sweep it (timeline → decision points →
deepening probes), close with the novice-contrast question. The full
transcript becomes ONE interview episode; consolidation does the rest.
"""

from __future__ import annotations

import json

from . import llm, tasktypes
from .store import Store

SYSTEM = """You are a knowledge-elicitation interviewer running a Critical Decision
Method session about the workflow '{workflow}' (task type: {task_type}).
Experts of this type systematically under-report: {blind_spot}.

Rules — these come from 40 years of elicitation research, follow them strictly:
- NEVER ask "how do you do X in general". Anchor everything to ONE concrete,
  non-routine incident the expert picks.
- Sweep order: (1) get the incident and its rough timeline; (2) locate the 2-3
  real decision points; (3) deepen each: what did you notice (cues)? what did
  you expect to happen? what else could you have done?; (4) close with:
  "what would a novice have gotten wrong here?"
- One question at a time, short and conversational. React to what they said.
- 8-12 questions total, then say exactly: [INTERVIEW COMPLETE]
The expert's time is precious; every question must earn its place."""


def run(store: Store, workflow: str, chat_fn=None, input_fn=input, print_fn=print) -> dict:
    cfg = store.config()
    model = store.load_model(workflow)
    tt = tasktypes.get(model["task_type"])
    system = SYSTEM.format(workflow=workflow, task_type=model["task_type"],
                           blind_spot=tt["blind_spot"])
    chat_fn = chat_fn or (lambda s, u: llm.chat(s, u, cfg))

    print_fn(f"\n— Bootstrap interview for '{workflow}' —")
    print_fn("Think of one recent time this workflow was NOT routine. Type '/done' to stop early.\n")

    transcript: list[dict] = []
    turn = "Please start the interview."
    for _ in range(15):
        reply = chat_fn(system, json.dumps({"transcript": transcript, "instruction": turn},
                                           ensure_ascii=False))
        done = "[INTERVIEW COMPLETE]" in reply
        question = reply.replace("[INTERVIEW COMPLETE]", "").strip()
        if question:
            print_fn(f"\napprentice> {question}")
            transcript.append({"role": "interviewer", "text": question})
        if done:
            break
        answer = input_fn("you> ").strip()
        if answer.lower() in ("/done", "/quit", "/q"):
            break
        transcript.append({"role": "expert", "text": answer})
        turn = "Continue the interview."

    print_fn("\nThanks — saving the interview. Run `apprentice consolidate` to fold it into the model.")
    return store.append_episode(workflow, "interview", {"transcript": transcript})
