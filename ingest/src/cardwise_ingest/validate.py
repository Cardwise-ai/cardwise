"""Decide whether a built corpus is fit to replace the live one (B4)."""

from dataclasses import dataclass

from cardwise_ingest.settings import IngestSettings
from cardwise_ingest.transform import Corpus, Source


@dataclass(frozen=True, slots=True)
class Report:
    errors: tuple[str, ...]
    counts: dict[str, int]
    quarantined: dict[Source, int]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate(
    corpus: Corpus,
    settings: IngestSettings,
    *,
    previous_card_count: int | None,
    allow_count_drift: bool = False,
) -> Report:
    errors = list(corpus.errors)

    floors = {
        "cards": (len(corpus.cards), settings.min_cards),
        "tags": (len(corpus.tags), settings.min_tags),
        "rulings": (len(corpus.rulings), settings.min_rulings),
    }
    for name, (count, floor) in floors.items():
        if count < floor:
            errors.append(f"only {count} {name}; expected at least {floor}")

    quarantined: dict[Source, int] = {}
    for source, seen in corpus.seen.items():
        bad = corpus.quarantined(source)
        quarantined[source] = bad
        if seen and bad / seen > settings.max_quarantine_ratio:
            errors.append(
                f"{bad} of {seen} {source} records quarantined"
                f" (limit {settings.max_quarantine_ratio:.1%})"
            )

    if previous_card_count and not allow_count_drift:
        drift = abs(len(corpus.cards) - previous_card_count) / previous_card_count
        if drift > settings.max_card_count_drift:
            errors.append(
                f"card count moved {drift:.1%} ({previous_card_count} -> {len(corpus.cards)});"
                f" limit {settings.max_card_count_drift:.0%}. Rerun with --allow-count-drift"
                " after checking the data."
            )

    counts = {
        "cards": len(corpus.cards),
        "faces": len(corpus.faces),
        "rulings": len(corpus.rulings),
        "tags": len(corpus.tags),
        "tag_edges": len(corpus.tag_edges),
        "card_tags": len(corpus.card_tags),
    }
    return Report(tuple(errors), counts, quarantined)
