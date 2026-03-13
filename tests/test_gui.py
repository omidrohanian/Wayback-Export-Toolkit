from __future__ import annotations

import pytest

from wayback_export.gui import (
    build_selection_from_indexes,
    format_candidate_row,
    get_help_text,
    parse_int_field,
)
from wayback_export.models import CandidateFile


@pytest.fixture
def candidates() -> list[CandidateFile]:
    return [
        CandidateFile(
            title="A",
            archived_url="https://web.archive.org/web/20200101010101/http://example.com/a.csv",
            original_url="http://example.com/a.csv",
            detected_type="csv",
            confidence=0.8,
            reason="extension:.csv",
            estimated_filename="a.csv",
        ),
        CandidateFile(
            title="B",
            archived_url="https://web.archive.org/web/20200101010101/http://example.com/b.zip",
            original_url="http://example.com/b.zip",
            detected_type="zip",
            confidence=0.9,
            reason="extension:.zip",
            estimated_filename="b.zip",
        ),
    ]


def test_parse_int_field_valid() -> None:
    assert parse_int_field(" 10 ", "Max Pages", 1) == 10


def test_parse_int_field_invalid_number() -> None:
    with pytest.raises(ValueError, match="integer"):
        parse_int_field("abc", "Timeout", 1)


def test_parse_int_field_below_minimum() -> None:
    with pytest.raises(ValueError, match=">= 0"):
        parse_int_field("-1", "Max Depth", 0)


def test_format_candidate_row(candidates: list[CandidateFile]) -> None:
    row = format_candidate_row(1, candidates[0])
    assert "csv" in row
    assert "a.csv" in row


def test_build_selection_from_indexes_selected(candidates: list[CandidateFile]) -> None:
    chosen = build_selection_from_indexes(candidates, [1], all_selected=False)
    assert len(chosen) == 1
    assert chosen[0].estimated_filename == "b.zip"


def test_build_selection_from_indexes_all(candidates: list[CandidateFile]) -> None:
    chosen = build_selection_from_indexes(candidates, [], all_selected=True)
    assert len(chosen) == 2


def test_build_selection_from_indexes_invalid(candidates: list[CandidateFile]) -> None:
    with pytest.raises(ValueError, match="invalid index"):
        build_selection_from_indexes(candidates, [3], all_selected=False)


def test_help_text_manifest_only_explains_behavior() -> None:
    text = get_help_text("manifest_only")
    assert "manifest" in text.lower()
    assert "skip actual file downloads" in text.lower()
