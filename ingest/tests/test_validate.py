from pathlib import Path

import pytest

from cardwise_ingest.settings import IngestSettings
from cardwise_ingest.transform import Corpus, build_corpus
from cardwise_ingest.validate import validate

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def corpus() -> Corpus:
    return build_corpus(
        FIXTURES / "cards.jsonl", FIXTURES / "rulings.jsonl", FIXTURES / "oracle_tags.jsonl"
    )


def test_clean_corpus_passes(corpus: Corpus, settings: IngestSettings) -> None:
    report = validate(corpus, settings, previous_card_count=len(corpus.cards))
    assert report.ok, report.errors
    assert report.counts["cards"] == len(corpus.cards)


def test_counts_below_floor_fail(corpus: Corpus) -> None:
    settings = IngestSettings(min_cards=10_000, min_tags=1, min_rulings=1)
    report = validate(corpus, settings, previous_card_count=None)
    assert report.errors == (f"only {len(corpus.cards)} cards; expected at least 10000",)


def test_card_count_drift_fails_unless_allowed(corpus: Corpus, settings: IngestSettings) -> None:
    previous = len(corpus.cards) * 2
    assert not validate(corpus, settings, previous_card_count=previous).ok
    assert validate(corpus, settings, previous_card_count=previous, allow_count_drift=True).ok


def test_too_much_quarantine_fails(corpus: Corpus) -> None:
    for i in range(3):
        corpus.reject("rulings", str(i), "bad", {})
    corpus.seen["rulings"] += 3
    settings = IngestSettings(min_cards=1, min_tags=1, min_rulings=1, max_quarantine_ratio=0.01)
    report = validate(corpus, settings, previous_card_count=None)
    assert report.quarantined["rulings"] == 3
    assert len(report.errors) == 1
    assert "rulings records quarantined" in report.errors[0]


def test_structural_errors_fail(corpus: Corpus, settings: IngestSettings) -> None:
    corpus.errors.append("duplicate oracle_id x")
    assert validate(corpus, settings, previous_card_count=None).errors == ("duplicate oracle_id x",)
