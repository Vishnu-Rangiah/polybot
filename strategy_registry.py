from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from strategy_types import Metrics


DEFAULT_REGISTRY_PATH = Path("strategies")


@dataclass(frozen=True)
class StrategyCandidate:
    strategy_id: str
    path: Path
    metadata: dict[str, Any]


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _compact_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def source_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _candidate_dir(registry_path: Path, strategy_id: str) -> Path:
    return registry_path / strategy_id


def save_strategy_candidate(
    source_path: Path,
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    strategy_id: str | None = None,
    author: str = "unknown",
    thesis: str = "",
    parent_strategy_id: str | None = None,
    status: str = "candidate",
    extra_metadata: Mapping[str, Any] | None = None,
) -> StrategyCandidate:
    source = source_path.read_text(encoding="utf-8")
    digest = source_hash(source)
    candidate_id = strategy_id or f"strategy_{_compact_timestamp()}_{digest[:8]}"
    candidate_path = _candidate_dir(registry_path, candidate_id)
    if candidate_path.exists():
        raise FileExistsError(f"Strategy candidate already exists: {candidate_path}")

    candidate_path.mkdir(parents=True)
    (candidate_path / "strategy.py").write_text(source, encoding="utf-8")
    (candidate_path / "evals.jsonl").touch()

    metadata = {
        "strategy_id": candidate_id,
        "created_at_utc": _utc_now(),
        "author": author,
        "parent_strategy_id": parent_strategy_id,
        "status": status,
        "thesis": thesis,
        "source_file": str(source_path),
        "source_hash_sha256": digest,
    }
    if extra_metadata:
        metadata.update(dict(extra_metadata))

    (candidate_path / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return StrategyCandidate(strategy_id=candidate_id, path=candidate_path, metadata=metadata)


def load_strategy_candidate(
    strategy_id: str,
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> StrategyCandidate:
    candidate_path = _candidate_dir(registry_path, strategy_id)
    metadata_path = candidate_path / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"No strategy metadata found at {metadata_path}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return StrategyCandidate(strategy_id=strategy_id, path=candidate_path, metadata=metadata)


def update_strategy_status(
    strategy_id: str,
    status: str,
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> StrategyCandidate:
    candidate = load_strategy_candidate(strategy_id, registry_path=registry_path)
    metadata = {
        **candidate.metadata,
        "status": status,
        "updated_at_utc": _utc_now(),
    }
    (candidate.path / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return StrategyCandidate(strategy_id=strategy_id, path=candidate.path, metadata=metadata)


def append_eval_result(
    strategy_id: str,
    metrics: Metrics | Mapping[str, Any],
    *,
    split: str,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    run_type: str = "fixture_backtest",
    data_ref: str = "default_fixture_cases",
    accepted: bool | None = None,
    notes: str = "",
) -> dict[str, Any]:
    candidate = load_strategy_candidate(strategy_id, registry_path=registry_path)
    metrics_payload = metrics.to_dict() if isinstance(metrics, Metrics) else dict(metrics)
    entry = {
        "eval_id": f"eval_{_compact_timestamp()}",
        "timestamp_utc": _utc_now(),
        "strategy_id": strategy_id,
        "split": split,
        "run_type": run_type,
        "data_ref": data_ref,
        "metrics": metrics_payload,
        "accepted": accepted,
        "notes": notes,
    }
    with (candidate.path / "evals.jsonl").open("a", encoding="utf-8") as evals:
        evals.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def list_strategy_candidates(registry_path: Path = DEFAULT_REGISTRY_PATH) -> list[StrategyCandidate]:
    if not registry_path.exists():
        return []

    candidates = []
    for metadata_path in sorted(registry_path.glob("*/metadata.json")):
        strategy_id = metadata_path.parent.name
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        candidates.append(StrategyCandidate(strategy_id=strategy_id, path=metadata_path.parent, metadata=metadata))
    return candidates


def iter_eval_results(
    strategy_id: str,
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> list[dict[str, Any]]:
    candidate = load_strategy_candidate(strategy_id, registry_path=registry_path)
    evals_path = candidate.path / "evals.jsonl"
    if not evals_path.exists():
        return []

    results = []
    with evals_path.open("r", encoding="utf-8") as evals:
        for line in evals:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage saved strategy candidates.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    save_parser = subparsers.add_parser("save", help="Save a strategy source file as an immutable candidate.")
    save_parser.add_argument("--source", type=Path, default=Path("strategy.py"))
    save_parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    save_parser.add_argument("--strategy-id", default=None)
    save_parser.add_argument("--author", default="human")
    save_parser.add_argument("--thesis", default="")
    save_parser.add_argument("--parent-strategy-id", default=None)
    save_parser.add_argument("--status", default="candidate")

    list_parser = subparsers.add_parser("list", help="List saved strategy candidates.")
    list_parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)

    status_parser = subparsers.add_parser("status", help="Update a strategy candidate status.")
    status_parser.add_argument("strategy_id")
    status_parser.add_argument("status")
    status_parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)

    eval_parser = subparsers.add_parser("append-eval", help="Append an eval result to a strategy candidate.")
    eval_parser.add_argument("strategy_id")
    eval_parser.add_argument("--split", required=True)
    eval_parser.add_argument("--metrics-json", required=True)
    eval_parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    eval_parser.add_argument("--run-type", default="fixture_backtest")
    eval_parser.add_argument("--data-ref", default="default_fixture_cases")
    eval_parser.add_argument("--accepted", action="store_true")
    eval_parser.add_argument("--notes", default="")

    args = parser.parse_args()
    if args.command == "save":
        candidate = save_strategy_candidate(
            args.source,
            registry_path=args.registry_path,
            strategy_id=args.strategy_id,
            author=args.author,
            thesis=args.thesis,
            parent_strategy_id=args.parent_strategy_id,
            status=args.status,
        )
        print(json.dumps(candidate.metadata, indent=2, sort_keys=True))
    elif args.command == "list":
        payload = [candidate.metadata for candidate in list_strategy_candidates(args.registry_path)]
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif args.command == "status":
        candidate = update_strategy_status(args.strategy_id, args.status, registry_path=args.registry_path)
        print(json.dumps(candidate.metadata, indent=2, sort_keys=True))
    elif args.command == "append-eval":
        entry = append_eval_result(
            args.strategy_id,
            json.loads(args.metrics_json),
            split=args.split,
            registry_path=args.registry_path,
            run_type=args.run_type,
            data_ref=args.data_ref,
            accepted=True if args.accepted else None,
            notes=args.notes,
        )
        print(json.dumps(entry, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
