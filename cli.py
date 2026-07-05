"""apprentice — CLI entry point. The system lives here; MCP is a view."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from . import __version__, compiler, consolidate, interview, policy, schema
from .store import Store


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="apprentice",
        description="Tacit-knowledge elicitation harness — an apprentice around the assistant you already use.",
    )
    p.add_argument("--version", action="version", version=f"apprentice {__version__}")
    p.add_argument("--home", help="store location (default: ./.apprentice if present, else ~/.apprentice)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="initialise the store")
    s.add_argument("--owner", required=True, help="your name or email (provenance)")

    s = sub.add_parser("new", help="create a workflow")
    s.add_argument("workflow")
    s.add_argument("--type", required=True, dest="task_type", choices=schema.TASK_TYPES)
    s.add_argument("--description", default="")

    sub.add_parser("status", help="overview of all workflows")

    s = sub.add_parser("observe", help="record evidence (the primary channel: corrections)")
    s.add_argument("workflow")
    s.add_argument("--draft", help="file: what the assistant produced")
    s.add_argument("--final", help="file: what you actually shipped")
    s.add_argument("--artifact", help="file: a template or exemplary document")
    s.add_argument("--note", default="", help="free-text context")

    s = sub.add_parser("ask", help="show today's question (respects budget & convergence)")
    s.add_argument("workflow")

    s = sub.add_parser("answer", help="answer a question")
    s.add_argument("workflow")
    s.add_argument("question_id")
    s.add_argument("text", nargs="+")

    s = sub.add_parser("interview", help="CDM bootstrap interview (LLM-led, ~10 min)")
    s.add_argument("workflow")

    s = sub.add_parser("consolidate", help="offline pass: episodes → model deltas (cron-able)")
    s.add_argument("workflow", nargs="?", help="default: all workflows")

    s = sub.add_parser("review", help="audit the model: assertions, confidence, provenance")
    s.add_argument("workflow")

    s = sub.add_parser("compile", help="export environment spec for synthetic training")
    s.add_argument("workflow")
    s.add_argument("--min-confidence", type=float, default=compiler.MIN_CONFIDENCE)

    sub.add_parser("serve", help="start the MCP adapter (stdio)")

    args = p.parse_args(argv)
    store = Store(Path(args.home) if args.home else None)

    try:
        return _dispatch(args, store)
    except (FileNotFoundError, FileExistsError, KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _dispatch(args, store: Store) -> int:
    if args.cmd == "init":
        root = store.init(args.owner)
        print(f"initialised store at {root}")
        print("next: apprentice new <workflow> --type <task_type>")
        return 0

    if args.cmd == "new":
        store.create_workflow(args.workflow, args.task_type, args.description)
        print(f"created workflow '{args.workflow}' ({args.task_type})")
        print(f"model: {store.workflow_dir(args.workflow) / 'model.yaml'} — yours to read and edit")
        print(f"seed it: apprentice interview {args.workflow}")
        return 0

    if args.cmd == "status":
        workflows = store.list_workflows()
        if not workflows:
            print("no workflows yet — apprentice new <name> --type <task_type>")
            return 0
        cfg = store.config()
        for name in workflows:
            m = store.load_model(name)
            qs = store.questions(name)
            eps = store.episodes(name)
            pend = len(store.episodes(name, unconsolidated_only=True))
            y = policy.rolling_yield(qs, int(cfg.get("yield_window", 20)))
            n_assert = sum(1 for _ in schema.iter_assertions(m))
            print(f"{name:30s} {m['task_type']:14s} {m.get('status', 'active'):10s} "
                  f"assertions:{n_assert:<4d} episodes:{len(eps):<4d} unconsolidated:{pend:<3d} "
                  f"queue:{len(qs.get('queue', [])):<3d} yield:{'—' if y is None else f'{y:.0%}'}")
        return 0

    if args.cmd == "observe":
        payload: dict = {"note": args.note}
        if args.draft and args.final:
            kind = "correction"
            payload["draft"] = Path(args.draft).read_text()
            payload["final"] = Path(args.final).read_text()
        elif args.artifact:
            kind = "artifact"
            payload["content"] = Path(args.artifact).read_text()
        elif args.note:
            kind = "volunteered"
        else:
            print("error: provide --draft+--final, --artifact, or --note", file=sys.stderr)
            return 1
        ep = store.append_episode(args.workflow, kind, payload)
        print(f"recorded {kind} episode {ep['id']}")
        return 0

    if args.cmd == "ask":
        q = policy.next_question(store, args.workflow)
        if q is None:
            print("no question today (budget spent, queue empty, or workflow converged)")
            return 0
        print(f"[{q['id']} · {q['strategy']}]\n{q['text']}")
        print(f"\nanswer with: apprentice answer {args.workflow} {q['id']} \"...\"")
        return 0

    if args.cmd == "answer":
        ep = policy.record_answer(store, args.workflow, args.question_id, " ".join(args.text))
        print(f"recorded answer as episode {ep['id']}")
        return 0

    if args.cmd == "interview":
        interview.run(store, args.workflow)
        return 0

    if args.cmd == "consolidate":
        targets = [args.workflow] if args.workflow else store.list_workflows()
        for name in targets:
            s = consolidate.consolidate(store, name)
            if s.get("episodes", 0) == 0:
                print(f"{name}: nothing to consolidate")
            else:
                print(f"{name}: {s['episodes']} episodes → +{s['added']} assertions, "
                      f"{s['confirmed']} confirmed, {s['contradicted']} contradicted, "
                      f"{s['questions']} questions queued  ({s['report']})")
        return 0

    if args.cmd == "review":
        m = store.load_model(args.workflow)
        print(f"# {m['workflow']} ({m['task_type']}, {m.get('status')})\n")
        for section, a in schema.iter_assertions(m):
            prov = a.get("provenance", {})
            text = a.get("rule") or a.get("condition") or a.get("text") or ""
            flag = "  ⚠ CONTRADICTED" if a.get("contradiction_note") else ""
            print(f"[{a.get('id', '?'):12s}] {a.get('confidence', '?'):>4} {section:18s} {text}{flag}")
            print(f"{'':19s}└ {prov.get('method', '?')} · {prov.get('source', '?')} · {prov.get('episode', '—')}")
        print(f"\nedit or delete directly: {store.workflow_dir(args.workflow) / 'model.yaml'}")
        return 0

    if args.cmd == "compile":
        path, spec = compiler.write_spec(store, args.workflow, args.min_confidence)
        print(f"environment spec written to {path}")
        print(json.dumps({
            "task_type": spec["task_type"],
            "exceptions_in_generator": len(spec["scenario_generator"]["exception_distribution"]),
            "decision_rules": len(spec["reference_policy"]["decision_rules"]),
            "checkers": len(spec["checkers"]),
            "held_out_cases": len(spec["held_out_cases"]["episode_ids"]),
            "excluded_low_confidence": spec["compiled_from"]["assertions_excluded_below_threshold"],
        }, indent=2))
        return 0

    if args.cmd == "serve":
        from . import mcp_server
        try:
            mcp_server.serve(store)
        except ImportError:
            print("error: MCP extra not installed — pip install 'apprentice-harness[mcp]'", file=sys.stderr)
            return 1
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
