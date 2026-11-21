"""Ingest configuration, read from CARDWISE_* environment variables or .env."""

from typing import Annotated, Self

from pydantic import Field, HttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Ratio = Annotated[float, Field(ge=0, le=1)]


class IngestSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CARDWISE_",
        env_file=".env",
        env_ignore_empty=True,  # GitHub Actions expands unset secrets to ""
        extra="ignore",
        frozen=True,
    )

    database_url: SecretStr | None = None
    """Session pooler URL (port 5432) on hosted Supabase; GitHub runners have no IPv6."""

    storage_s3_endpoint: HttpUrl | None = None
    storage_s3_region: str | None = None
    storage_s3_access_key_id: SecretStr | None = None
    storage_s3_secret_access_key: SecretStr | None = None
    storage_bucket: str = "raw-snapshots"
    raw_snapshots_kept: Annotated[int, Field(ge=1)] = 4

    bulk_index_url: HttpUrl = HttpUrl("https://api.scryfall.com/bulk-data")
    user_agent: str = "Cardwise/0.1 (github.com/Cardwise-ai)"

    min_cards: Annotated[int, Field(ge=0)] = 30_000
    min_tags: Annotated[int, Field(ge=0)] = 3_000
    min_rulings: Annotated[int, Field(ge=0)] = 50_000
    max_card_count_drift: Ratio = 0.05
    """Largest allowed change in card count against the active snapshot."""
    max_quarantine_ratio: Ratio = 0.005
    """Largest share of records per source that may be quarantined before the run fails."""

    @property
    def s3_configured(self) -> bool:
        return self.storage_s3_endpoint is not None

    @model_validator(mode="after")
    def _s3_all_or_nothing(self) -> Self:
        s3 = (
            self.storage_s3_endpoint,
            self.storage_s3_region,
            self.storage_s3_access_key_id,
            self.storage_s3_secret_access_key,
        )
        if any(v is not None for v in s3) and not all(v is not None for v in s3):
            raise ValueError(
                "set all of CARDWISE_STORAGE_S3_ENDPOINT, _REGION, _ACCESS_KEY_ID and"
                " _SECRET_ACCESS_KEY, or none of them"
            )
        return self
