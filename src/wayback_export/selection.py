from __future__ import annotations

from typing import List, Sequence

from .models import CandidateFile


def parse_selection_expression(expression: str, total: int) -> List[int]:
    expr = expression.strip().lower()
    if expr in {"all", "*"}:
        return list(range(total))
    selected = set()
    for part in expr.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start = int(start_s)
            end = int(end_s)
            if start < 1 or end > total or start > end:
                raise ValueError(f"Invalid range: {part}")
            for idx in range(start - 1, end):
                selected.add(idx)
        else:
            value = int(part)
            if value < 1 or value > total:
                raise ValueError(f"Invalid index: {part}")
            selected.add(value - 1)
    return sorted(selected)


def prompt_select_candidates(candidates: Sequence[CandidateFile]) -> List[CandidateFile]:
    if not candidates:
        return []
    _print_candidates(candidates)
    raw = input("Select items (e.g. 1,2-4 or 'all'): ").strip()
    indexes = parse_selection_expression(raw or "all", total=len(candidates))
    return [candidates[i] for i in indexes]


def _print_candidates(candidates: Sequence[CandidateFile]) -> None:
    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(title="Discovered candidates")
        table.add_column("#", justify="right")
        table.add_column("Type")
        table.add_column("Confidence")
        table.add_column("Filename")
        table.add_column("URL")
        for idx, candidate in enumerate(candidates, start=1):
            table.add_row(
                str(idx),
                candidate.detected_type,
                f"{candidate.confidence:.2f}",
                candidate.estimated_filename,
                candidate.archived_url,
            )
        Console().print(table)
        return
    except ImportError:
        pass

    for idx, candidate in enumerate(candidates, start=1):
        print(
            f"{idx:>3}. [{candidate.detected_type}] {candidate.estimated_filename} "
            f"(score={candidate.confidence:.2f})"
        )
        print(f"     {candidate.archived_url}")
