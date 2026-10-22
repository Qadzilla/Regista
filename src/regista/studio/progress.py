"""Run a Studio job's command with progress lines, so its log streams while it runs.

    python3 -u -m regista.studio.progress regista.vision run VIDEO --roster … --workflow
    python3 -u -m regista.studio.progress regista.agents MATCH_DIR --player …

The vision and agent CLIs print their trace only when the whole run is over, which left a Studio job's log empty for
minutes. This wrapper changes nothing in them: it wraps each agent's ``handle`` (the same objects the workflow runs) to
print a line when the agent starts and when it finishes, prints a heartbeat every ``REGISTA_JOB_HEARTBEAT_S`` seconds
(default 30), then calls the command's own ``main(argv)`` and exits with its code. Every line is flushed at once.
"""

from __future__ import annotations

import importlib
import os
import sys
import threading
import time
from typing import Any

ALLOWED = ("regista.vision", "regista.agents")
T0 = time.monotonic()


def _elapsed(seconds: float | None = None) -> str:
    s = int(time.monotonic() - T0 if seconds is None else seconds)
    return f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"


def say(text: str) -> None:
    print(f"[studio {_elapsed()}] {text}", flush=True)


def wrap_agents(agents: list[Any]) -> list[Any]:
    """Give each agent a ``handle`` that announces itself; the original runs unchanged (retries call it again)."""
    for agent in agents:
        inner = agent.handle
        role = getattr(agent, "role", type(agent).__name__)

        def handle(state, _inner=inner, _role=role):
            say(f"{_role}: started")
            t = time.monotonic()
            try:
                out = _inner(state)
            except Exception as exc:
                say(f"{_role}: failed after {_elapsed(time.monotonic() - t)} ({type(exc).__name__}: {str(exc)[:200]})")
                raise
            say(f"{_role}: done in {_elapsed(time.monotonic() - t)}")
            return out

        agent.handle = handle
    return agents


def install(module: str) -> None:
    """Patch the factory the command builds its agents from (looked up at call time, so the patch takes)."""
    if module == "regista.vision":
        from regista.vision import agents as vision

        factory = vision.vision_agents
        vision.vision_agents = lambda config=None: wrap_agents(factory(config))
    elif module == "regista.agents":
        from regista.agents import roles

        factory = roles.default_agents
        roles.default_agents = lambda: wrap_agents(factory())


def heartbeat(every: float, stop: threading.Event) -> None:
    while not stop.wait(every):
        say("still running")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ALLOWED:
        print(f"usage: python3 -m regista.studio.progress {{{','.join(ALLOWED)}}} ARGS…", file=sys.stderr)
        return 2
    module, args = argv[0], argv[1:]
    say(f"started: python3 -m {module} {' '.join(args)}")
    if module == "regista.vision" and args[:1] == ["run"] and "--workflow" not in args:
        say("without the workflow the vision pipeline reports only when it ends; the heartbeat shows it is alive")
    install(module)  # before the command imports its factory by name
    stop = threading.Event()
    every = float(os.environ.get("REGISTA_JOB_HEARTBEAT_S") or 30)
    threading.Thread(target=heartbeat, args=(every, stop), daemon=True).start()
    try:
        rc = importlib.import_module(f"{module}.__main__").main(args)
    except SystemExit as exc:  # argparse errors and explicit exits
        rc = exc.code if isinstance(exc.code, int) else 1
    finally:
        stop.set()
    say(f"finished with exit code {rc}")
    return int(rc or 0)


if __name__ == "__main__":
    sys.exit(main())
