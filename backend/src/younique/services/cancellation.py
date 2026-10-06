_runs: set[str] = set()


def mark(run_id: str) -> None:
    _runs.add(run_id)


def is_marked(run_id: str) -> bool:
    return run_id in _runs
