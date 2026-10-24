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
    assert not _excluded("src/regista/static/product/index.html") and not _excluded("src/regista/schemas/regista-events.schema.json")
    assert _excluded(".env")
    assert _excluded("data/synthetic/sample/syn_0294/agents/trace.jsonl")
    assert _excluded("data/vision/vis_0201/.vision_work/identity.joblib")  # full vision outputs stay on the machine that ran them


def test_the_image_carries_the_league_and_builds_its_matches():
    docker = (REPO / "Dockerfile").read_text()
    assert "COPY data/season/league.json" in docker and "regista.season" in docker and "REGISTA_SEASON=" in docker
    assert _excluded("data/season/matches/rl_r01_ash_fai/events.jsonl") and not _excluded("data/season/league.json")
    # the Profile agent's summaries ship beside the league (regista.season.summaries.summaries_path)
    assert "COPY data/season/summaries.json ./data/season/summaries.json" in docker and not _excluded("data/season/summaries.json")
    # ... and the split-half reliability that marks noisy metrics (regista.season.reliability.load)
    assert "COPY data/season/reliability.json ./data/season/reliability.json" in docker
    assert not _excluded("data/season/reliability.json")
