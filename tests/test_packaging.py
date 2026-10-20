"""The container image must contain the package: a too-broad .dockerignore once shipped an image without regista.agents."""

import fnmatch
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _patterns():
    return [l.strip().rstrip("/") for l in (REPO / ".dockerignore").read_text().splitlines() if l.strip() and not l.startswith("#")]


def _excluded(path: str) -> bool:
    for pat in _patterns():
        if fnmatch.fnmatch(path, pat) or path.startswith(pat + "/"):
            return True
        # "**/x" and "a/**/x" match x at any depth below the prefix, and everything under it.
        if "**" in pat:
            head, _, tail = pat.partition("**/")
            if path.startswith(head) and any(fnmatch.fnmatch("/".join(path.split("/")[i:j]), tail)
                                            for i in range(len(path.split("/"))) for j in range(i + 1, len(path.split("/")) + 1)):
                return True
    return False


def test_dockerignore_keeps_the_package_and_drops_run_state():
    for f in (REPO / "src" / "regista").rglob("*.py"):
        rel = f.relative_to(REPO).as_posix()
        assert not _excluded(rel), f"{rel} would be missing from the container image"
    assert not _excluded("src/regista/static/viewer.html") and not _excluded("src/regista/schemas/regista-events.schema.json")
    assert _excluded(".env")
    assert _excluded("data/synthetic/sample/syn_0294/agents/trace.jsonl")
