from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import modal

from codex_worker import CodexModalWorker, WorkerContext
from strategy_registry import DEFAULT_REGISTRY_PATH, load_strategy_candidate

app = modal.App("polybot-strategy-search")

# Scoring image carries the frozen scorer and contract so remote workers can
# import them. The candidate source is passed in as a string per call.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("requests")
    .add_local_python_source("strategy_types", "strategy", "backtest")
)


@app.function(image=image, timeout=120)
def score_strategy_source(source: str, split: str) -> dict:
    """Score one candidate's source on one split, in an isolated remote container."""
    import importlib.util
    import sys
    import tempfile
    from pathlib import Path as _Path

    from backtest import backtest, load_cases

    with tempfile.TemporaryDirectory() as tmp:
        candidate_path = _Path(tmp) / "candidate_strategy.py"
        candidate_path.write_text(source, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("candidate_strategy", candidate_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["candidate_strategy"] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        metrics = backtest(module.decide, split=split, cases=load_cases())

    return {"split": split, "metrics": metrics.to_dict()}


def score_sources_parallel(
    sources_with_splits: Sequence[tuple[str, str]],
    *,
    manage_app: bool = True,
) -> list[dict]:
    """Fan out (source, split) scoring jobs across Modal containers via starmap."""
    pairs = list(sources_with_splits)
    if not pairs:
        raise ValueError("At least one (source, split) pair is required.")

    if not manage_app:
        return list(score_strategy_source.starmap(pairs))

    with app.run():
        return list(score_strategy_source.starmap(pairs))


def evaluate_candidates_parallel(
    strategy_ids: Iterable[str],
    *,
    splits: tuple[str, ...] = ("train", "val"),
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    manage_app: bool = True,
) -> dict[str, dict[str, dict]]:
    """Score many saved candidates over many splits in parallel, grouped by strategy id."""
    index: list[tuple[str, str]] = []
    pairs: list[tuple[str, str]] = []
    for strategy_id in strategy_ids:
        candidate = load_strategy_candidate(strategy_id, registry_path=registry_path)
        source = (candidate.path / "strategy.py").read_text(encoding="utf-8")
        for split in splits:
            index.append((strategy_id, split))
            pairs.append((source, split))

    results = score_sources_parallel(pairs, manage_app=manage_app)

    grouped: dict[str, dict[str, dict]] = {}
    for (strategy_id, _split), result in zip(index, results):
        grouped.setdefault(strategy_id, {})[result["split"]] = result["metrics"]
    return grouped


def generate_candidates_parallel(
    contexts: Sequence[WorkerContext],
    *,
    worker: CodexModalWorker | None = None,
    max_workers: int = 4,
) -> list[dict]:
    """Run several Codex sandboxes concurrently, each producing one candidate.

    Each CodexModalWorker.generate() spins up its own disposable Modal Sandbox, so
    running them on a thread pool yields genuinely parallel sandboxed generation.
    """
    active_worker = worker or CodexModalWorker()
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(active_worker.generate, contexts))
    return [
        {"rationale": result.rationale, "worker_type": result.worker_type, "source": result.source}
        for result in results
    ]


@app.local_entrypoint()
def main(strategy_ids: str, splits: str = "train,val") -> None:
    ids = [item.strip() for item in strategy_ids.split(",") if item.strip()]
    split_tuple = tuple(item.strip() for item in splits.split(",") if item.strip())
    grouped = evaluate_candidates_parallel(ids, splits=split_tuple, manage_app=False)
    print(json.dumps(grouped, indent=2, sort_keys=True))
