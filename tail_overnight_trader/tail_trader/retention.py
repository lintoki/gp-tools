from pathlib import Path
from typing import Iterable, Set


DEFAULT_RETENTION_LIMIT = 10


def prepare_output_file(path: Path, pattern: str, keep: int = DEFAULT_RETENTION_LIMIT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if keep <= 0:
        prune_generated_files(path.parent, pattern, keep=0, exclude={path})
        return
    prune_generated_files(path.parent, pattern, keep=max(0, keep - 1), exclude={path})


def prune_generated_files(
    directory: Path,
    pattern: str,
    keep: int = DEFAULT_RETENTION_LIMIT,
    exclude: Iterable[Path] = (),
) -> None:
    if not directory.exists():
        return

    excluded: Set[Path] = {path.resolve() for path in exclude}
    files = sorted(
        (path for path in directory.glob(pattern) if path.is_file() and path.resolve() not in excluded),
        key=lambda path: path.name,
    )
    delete_count = max(0, len(files) - max(0, keep))
    for path in files[:delete_count]:
        path.unlink(missing_ok=True)


def trim_jsonl_file(path: Path, keep: int = DEFAULT_RETENTION_LIMIT) -> None:
    if not path.exists():
        return
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    retained = lines[-max(0, keep) :] if keep > 0 else []
    path.write_text(("\n".join(retained) + "\n") if retained else "", encoding="utf-8")
