"""`python -m demo_agent run --bug {none,loop,silent_error,cost_spike} --n 10 [--offline]`."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Mapping
from typing import Sequence

import httpx

from demo_agent.agent import BUGS, QUESTIONS, ContainmentFlags, run_order_lookup
from demo_agent.llm import ScriptedModel, TogetherModel, prices_from_env
from demo_agent.recording import LangfuseSink, TraceRecorder

DEFAULT_CONTAINMENT_URL = "http://127.0.0.1:8700"
DEFAULT_LANGFUSE_HOST = "http://localhost:3000"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="demo_agent")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run the order-lookup agent with one bug switched on")
    run.add_argument("--bug", choices=BUGS, default="none")
    run.add_argument("--n", type=int, default=1, help="number of runs (default 1)")
    run.add_argument("--offline", action="store_true", help="use the scripted model; no API key, no Langfuse")
    return parser


def build_sink(env: Mapping[str, str], http: httpx.Client) -> LangfuseSink | None:
    public_key = env.get("LANGFUSE_PUBLIC_KEY")
    secret_key = env.get("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        return None
    host = env.get("LANGFUSE_HOST", DEFAULT_LANGFUSE_HOST)
    return LangfuseSink(host, public_key, secret_key, http=http)


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    args = build_parser().parse_args(argv)
    if args.command != "run":
        return 2
    if args.n < 1:
        print("--n must be at least 1", file=sys.stderr)
        return 2

    api_key = None
    model_name = None
    if not args.offline:
        api_key = env.get("TOGETHER_API_KEY")
        model_name = env.get("TOGETHER_MODEL")
        if not api_key or not model_name:
            print("online runs need TOGETHER_API_KEY and TOGETHER_MODEL (or pass --offline)", file=sys.stderr)
            return 2
        if not env.get("DEMO_PRICE_INPUT_PER_MTOK") or not env.get("DEMO_PRICE_OUTPUT_PER_MTOK"):
            print(
                "online runs need DEMO_PRICE_INPUT_PER_MTOK and DEMO_PRICE_OUTPUT_PER_MTOK "
                "set to the Together model's USD per million tokens",
                file=sys.stderr,
            )
            return 2

    try:
        prices = prices_from_env(env)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    failures = 0
    with httpx.Client() as http:
        flags = ContainmentFlags(env.get("TRIPWIRE_CONTAINMENT_URL", DEFAULT_CONTAINMENT_URL), http=http)
        sink = None if args.offline else build_sink(env, http)
        for index in range(args.n):
            recorder = TraceRecorder(prices=prices)
            if args.offline:
                model = ScriptedModel(args.bug)
                name = "scripted"
            else:
                assert api_key is not None and model_name is not None
                model = TogetherModel(api_key, http=http)
                name = model_name
            question = QUESTIONS[index % len(QUESTIONS)]
            result = run_order_lookup(
                question, bug=args.bug, model=model, model_name=name, flags=flags, recorder=recorder,
            )
            if sink is not None:
                try:
                    sink.send(result.trace, recorder.details)
                except httpx.HTTPError as exc:
                    logging.getLogger(__name__).warning("Langfuse send failed for %s: %s", result.trace.id, exc)
            if result.status == "error":
                failures += 1
            print(
                f"run {index + 1}/{args.n} bug={args.bug} status={result.status} "
                f"trace={result.trace.id} observations={len(result.trace.observations)} "
                f"cost_usd={result.trace.total_cost_usd:.4f}"
            )
    return 1 if failures else 0
