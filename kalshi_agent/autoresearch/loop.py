from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from kalshi_agent.autoresearch.evaluator import (
    current_best_validation,
    evaluate_saved_strategy,
    load_strategy_fn_from_file,
)
from kalshi_agent.autoresearch.registry import (
    DEFAULT_REGISTRY_PATH,
    iter_eval_results,
    load_strategy_candidate,
    save_strategy_candidate,
    update_strategy_status,
)
from kalshi_agent.autoresearch.worker import DEFAULT_CODEX_APP_NAME, DEFAULT_CODEX_SECRET_NAME, WorkerContext, get_worker

DEFAULT_THESIS_PATH = Path("thesis.md")
DEFAULT_BASELINE_PATH = Path(__file__).resolve().parent / "baseline.py"
DEFAULT_LEDGER_PATH = Path("strategy_ledger.jsonl")

STATUS_PROMOTED = "promoted_paper"
STATUS_REJECTED = "rejected"
STATUS_INVALID = "rejected_invalid"


@dataclass
class ParentStrategy:
    strategy_id: str | None
    source: str
    prior_metrics: dict[str, object]


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _latest_val_metrics(strategy_id: str, *, registry_path: Path) -> dict[str, object]:
    for row in reversed(iter_eval_results(strategy_id, registry_path=registry_path)):
        if row.get("split") == "val":
            return dict(row.get("metrics") or {})
    return {}


def resolve_parent(
    *,
    registry_path: Path,
    baseline_path: Path,
) -> ParentStrategy:
    """Use the current best promoted strategy as the parent, else the baseline file."""
    best = current_best_validation(registry_path=registry_path)
    if best.strategy_id is not None:
        candidate = load_strategy_candidate(best.strategy_id, registry_path=registry_path)
        source = (candidate.path / "strategy.py").read_text(encoding="utf-8")
        prior = _latest_val_metrics(best.strategy_id, registry_path=registry_path)
        return ParentStrategy(strategy_id=best.strategy_id, source=source, prior_metrics=prior)

    return ParentStrategy(
        strategy_id=None,
        source=baseline_path.read_text(encoding="utf-8"),
        prior_metrics={},
    )


def _is_valid_strategy(source: str) -> tuple[bool, str]:
    try:
        compile(source, "<candidate>", "exec")
    except SyntaxError as exc:
        return False, f"Syntax error: {exc}"

    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / "strategy.py"
        probe.write_text(source, encoding="utf-8")
        try:
            load_strategy_fn_from_file(probe, "decide")
        except Exception as exc:  # noqa: BLE001 - report any import/contract failure
            return False, f"Failed to load decide(): {exc}"
    return True, ""


def _append_ledger(ledger_path: Path, entry: dict[str, object]) -> None:
    with ledger_path.open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(entry, sort_keys=True) + "\n")


def run_loop(
    *,
    iterations: int,
    worker_name: str,
    worker_options: dict[str, object] | None = None,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    thesis_path: Path = DEFAULT_THESIS_PATH,
    baseline_path: Path = DEFAULT_BASELINE_PATH,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    cases_path: Path | None = None,
) -> list[dict[str, object]]:
    thesis = thesis_path.read_text(encoding="utf-8") if thesis_path.exists() else ""
    worker = get_worker(worker_name, **(worker_options or {}))
    summaries: list[dict[str, object]] = []

    for attempt_index in range(iterations):
        parent = resolve_parent(registry_path=registry_path, baseline_path=baseline_path)
        context = WorkerContext(
            thesis=thesis,
            parent_source=parent.source,
            parent_strategy_id=parent.strategy_id,
            prior_metrics=parent.prior_metrics,
            attempt_index=attempt_index,
            attempt_label=f"iter{attempt_index}",
        )

        result = worker.generate(context)
        valid, invalid_reason = _is_valid_strategy(result.source)

        with tempfile.TemporaryDirectory() as tmp:
            working = Path(tmp) / "strategy.py"
            working.write_text(result.source, encoding="utf-8")
            candidate = save_strategy_candidate(
                working,
                registry_path=registry_path,
                author=result.worker_type,
                thesis=thesis.splitlines()[0] if thesis else "",
                parent_strategy_id=parent.strategy_id,
                status="candidate",
                extra_metadata={
                    "rationale": result.rationale,
                    "worker_type": result.worker_type,
                    "attempt_index": attempt_index,
                },
            )

        entry: dict[str, object] = {
            "timestamp_utc": _utc_now(),
            "iteration": attempt_index,
            "strategy_id": candidate.strategy_id,
            "parent_strategy_id": parent.strategy_id,
            "worker_type": result.worker_type,
        }

        if not valid:
            update_strategy_status(candidate.strategy_id, STATUS_INVALID, registry_path=registry_path)
            entry.update({"status": STATUS_INVALID, "reason": invalid_reason})
            _append_ledger(ledger_path, entry)
            summaries.append(entry)
            continue

        evaluation = evaluate_saved_strategy(
            candidate.strategy_id,
            registry_path=registry_path,
            cases_path=cases_path,
            run_type="loop_backtest",
        )
        status = STATUS_PROMOTED if evaluation.promotion.promote else STATUS_REJECTED
        update_strategy_status(candidate.strategy_id, status, registry_path=registry_path)

        entry.update(
            {
                "status": status,
                "metrics": {split: m.to_dict() for split, m in evaluation.metrics_by_split.items()},
                "promotion": evaluation.promotion.to_dict(),
            }
        )
        _append_ledger(ledger_path, entry)
        summaries.append(entry)

    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the strategy autoresearch loop.")
    parser.add_argument("--iterations", type=int, default=3, help="Number of candidate attempts.")
    parser.add_argument("--worker", choices=["mock", "codex"], default="mock", help="Strategy worker backend.")
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--thesis", type=Path, default=DEFAULT_THESIS_PATH)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--ledger-path", type=Path, default=DEFAULT_LEDGER_PATH)
    parser.add_argument("--cases-path", type=Path, default=None)
    parser.add_argument("--codex-app-name", default=DEFAULT_CODEX_APP_NAME)
    parser.add_argument("--codex-secret-name", default=DEFAULT_CODEX_SECRET_NAME)
    parser.add_argument("--codex-model", default=None)
    parser.add_argument("--codex-timeout-seconds", type=int, default=600)
    args = parser.parse_args()

    worker_options: dict[str, object] = {}
    if args.worker == "codex":
        worker_options = {
            "app_name": args.codex_app_name,
            "secret_name": args.codex_secret_name,
            "codex_model": args.codex_model,
            "timeout_seconds": args.codex_timeout_seconds,
        }

    summaries = run_loop(
        iterations=args.iterations,
        worker_name=args.worker,
        worker_options=worker_options,
        registry_path=args.registry_path,
        thesis_path=args.thesis,
        baseline_path=args.baseline,
        ledger_path=args.ledger_path,
        cases_path=args.cases_path,
    )
    print(json.dumps(summaries, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
