"""The trained vision models in the Player view's store (``models/vision/``), where the worker loads them from.

    python -m regista.player.models push [--models models/vision]    # this machine's trained models -> the store
    python -m regista.player.models pull [--models DIR]              # the store's models -> a folder
    python -m regista.player.models list

The store is ``store_from_env()``: the Azure storage account when ``REGISTA_STORAGE_ACCOUNT`` is set (its private
``models`` container), otherwise the local folder. Models never go into git.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from regista.player.store import Store, store_from_env

PREFIX = "vision"
DEFAULT_MODELS = Path("models/vision")
REQUIRED = ("shot_model.joblib", "kit_number_reader.joblib", "identity_config.json", "event_spotter.joblib")


def push(store: Store, src: Path | str = DEFAULT_MODELS) -> int:
    """Upload every file under ``src`` to ``models/vision/``. Refuses a folder missing one of the models the vision
    workflow loads, so the worker never pulls half a set."""
    src = Path(src)
    missing = [f for f in REQUIRED if not (src / f).is_file()]
    if missing:
        raise ValueError(f"{src} is missing {', '.join(missing)}; train with python -m regista.vision train (and train-events)")
    return store.put_dir("models", PREFIX, src)


def pull(store: Store, dest: Path | str) -> int:
    """Download ``models/vision/`` into ``dest``. Returns the number of files (0 when nothing has been pushed)."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    return store.get_dir("models", PREFIX, dest)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m regista.player.models", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("push", help="upload trained models to the store")
    p.add_argument("--models", type=Path, default=DEFAULT_MODELS)
    g = sub.add_parser("pull", help="download the store's models")
    g.add_argument("--models", type=Path, default=DEFAULT_MODELS)
    sub.add_parser("list", help="say which store is in use and whether it holds models")
    args = ap.parse_args(argv)
    store = store_from_env()
    if args.cmd == "push":
        n = push(store, args.models)
        print(json.dumps({"store": store.kind, "pushed": n, "from": str(args.models), "to": f"models/{PREFIX}/"}))
    elif args.cmd == "pull":
        n = pull(store, args.models)
        print(json.dumps({"store": store.kind, "pulled": n, "to": str(args.models)}))
        return 0 if n else 1
    else:
        print(json.dumps({"store": store.kind, "models": PREFIX in store.list_prefixes("models")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
