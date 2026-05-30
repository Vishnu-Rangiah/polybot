from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from backtest import StrategyFn, backtest, load_cases
from strategy_registry import (
    DEFAULT_REGISTRY_PATH,
    append_eval_result,
    iter_eval_results,
    list_strategy_candidates,
    load_strategy_candidate,
)
from strategy_types import Metrics

DEFAULT_EVAL_SPLITS = ("train", "val")
MIN_TRADES_FOR_PROMOTION = 1
MAX_BRIER_DEGRADATION = 0.05
PROMOTED_STATUS = "promoted_paper"


@dataclass(frozen=True)
class BaselineValidation:
    strategy_id: str | None
    sharpe: float | None
    brier: float | None


@dataclass(frozen=True)
class PromotionDecision:
    promote: bool
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {"promote": self.promote, "reasons": list(self.reasons)}


@dataclass(frozen=True)
class CandidateEvaluation:
    strategy_id: str
    metrics_by_split: dict[str, Metrics]
    promotion: PromotionDecision
    data_ref: str

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy_id": self.strategy_id,
            "data_ref": self.data_ref,
            "metrics_by_split": {split: metrics.to_dict() for split, metrics in self.metrics_by_split.items()},
            "promotion": self.promotion.to_dict(),
        }


def load_strategy_fn_from_file(source_path: Path, function_name: str = "decide") -> StrategyFn:
    """Import a strategy callable from an arbitrary file without polluting the import path."""
    source_path = Path(source_path)
    module_name = f"_candidate_{source_path.parent.name}_{source_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load strategy module from {source_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise

    strategy_fn = getattr(module, function_name, None)
    if not callable(strategy_fn):
        raise TypeError(f"{function_name!r} in {source_path} is not callable.")
    return strategy_fn


def _best_val_metrics(rows: list[dict]) -> tuple[float | None, float | None]:
    best_sharpe: float | None = None
    best_brier: float | None = None
    for row in rows:
        if row.get("split") != "val":
            continue
        metrics = row.get("metrics") or {}
        sharpe = metrics.get("sharpe")
        brier = metrics.get("brier")
        if sharpe is not None and (best_sharpe is None or sharpe > best_sharpe):
            best_sharpe = sharpe
            best_brier = brier
    return best_sharpe, best_brier


def current_best_validation(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    exclude_strategy_id: str | None = None,
) -> BaselineValidation:
    """Find the strongest validation Sharpe among already-promoted strategies."""
    best = BaselineValidation(strategy_id=None, sharpe=None, brier=None)
    for candidate in list_strategy_candidates(registry_path):
        if candidate.strategy_id == exclude_strategy_id:
            continue
        if candidate.metadata.get("status") != PROMOTED_STATUS:
            continue

        rows = iter_eval_results(candidate.strategy_id, registry_path=registry_path)
        sharpe, brier = _best_val_metrics(rows)
        if sharpe is None:
            continue
        if best.sharpe is None or sharpe > best.sharpe:
            best = BaselineValidation(strategy_id=candidate.strategy_id, sharpe=sharpe, brier=brier)
    return best


def evaluate_promotion(
    metrics_by_split: dict[str, Metrics],
    baseline: BaselineValidation,
    *,
    min_trades: int = MIN_TRADES_FOR_PROMOTION,
    max_brier_degradation: float = MAX_BRIER_DEGRADATION,
) -> PromotionDecision:
    reasons: list[str] = []
    val = metrics_by_split.get("val")
    if val is None:
        return PromotionDecision(promote=False, reasons=["No validation metrics were produced."])

    if val.n_trades < min_trades:
        reasons.append(f"Validation trades {val.n_trades} below minimum {min_trades}.")

    if baseline.sharpe is not None and val.sharpe <= baseline.sharpe:
        reasons.append(
            f"Validation Sharpe {val.sharpe} does not beat current best {baseline.sharpe}."
        )

    if (
        baseline.brier is not None
        and val.brier is not None
        and val.brier > baseline.brier + max_brier_degradation
    ):
        reasons.append(
            f"Validation Brier {val.brier} degrades beyond {baseline.brier} + {max_brier_degradation}."
        )

    return PromotionDecision(promote=not reasons, reasons=reasons)


def evaluate_saved_strategy(
    strategy_id: str,
    *,
    splits: tuple[str, ...] = DEFAULT_EVAL_SPLITS,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    cases_path: Path | None = None,
    function_name: str = "decide",
    run_type: str = "fixture_backtest",
    record: bool = True,
    check_promotion: bool = True,
) -> CandidateEvaluation:
    """Load a saved candidate, score it over the requested splits, and optionally record results."""
    candidate = load_strategy_candidate(strategy_id, registry_path=registry_path)
    strategy_path = candidate.path / "strategy.py"
    strategy_fn = load_strategy_fn_from_file(strategy_path, function_name)

    cases = load_cases(cases_path)
    data_ref = "default_fixture_cases" if cases_path is None else str(cases_path)

    metrics_by_split: dict[str, Metrics] = {}
    for split in splits:
        metrics = backtest(strategy_fn, split=split, cases=cases)
        metrics_by_split[split] = metrics

    promotion = PromotionDecision(promote=False, reasons=["Promotion check skipped."])
    if check_promotion:
        baseline = current_best_validation(registry_path=registry_path, exclude_strategy_id=strategy_id)
        promotion = evaluate_promotion(metrics_by_split, baseline)

    if record:
        for split, metrics in metrics_by_split.items():
            accepted = promotion.promote if (check_promotion and split == "val") else None
            append_eval_result(
                strategy_id,
                metrics,
                split=split,
                registry_path=registry_path,
                run_type=run_type,
                data_ref=data_ref,
                accepted=accepted,
                notes="; ".join(promotion.reasons) if (check_promotion and split == "val") else "",
            )

    return CandidateEvaluation(
        strategy_id=strategy_id,
        metrics_by_split=metrics_by_split,
        promotion=promotion,
        data_ref=data_ref,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a saved strategy candidate with the frozen backtester.")
    parser.add_argument("strategy_id", help="Strategy candidate id under the registry.")
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--splits", default="train,val", help="Comma-separated splits to score.")
    parser.add_argument("--cases-path", type=Path, default=None, help="Optional JSONL backtest case file.")
    parser.add_argument("--function-name", default="decide", help="Strategy callable to import.")
    parser.add_argument("--no-record", action="store_true", help="Do not append eval rows to the registry.")
    parser.add_argument("--no-promotion", action="store_true", help="Skip the promotion gate check.")
    args = parser.parse_args()

    splits = tuple(split.strip() for split in args.splits.split(",") if split.strip())
    evaluation = evaluate_saved_strategy(
        args.strategy_id,
        splits=splits,
        registry_path=args.registry_path,
        cases_path=args.cases_path,
        function_name=args.function_name,
        record=not args.no_record,
        check_promotion=not args.no_promotion,
    )
    print(json.dumps(evaluation.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
