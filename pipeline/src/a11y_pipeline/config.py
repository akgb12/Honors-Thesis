from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,
    )

    model_provider: Literal["fake", "anthropic"] = "fake"
    anthropic_api_key: SecretStr | None = None
    generator_model: str = "claude-sonnet-5-5"
    model_input_usd_per_mtok: float | None = None
    model_output_usd_per_mtok: float | None = None
    model_max_output_tokens: int = 1000
    model_cache_dir: Path = Path(".cache/model_responses")
    run_dollar_cap_low: float = 0.50
    run_dollar_cap_medium: float = 1.50
    run_dollar_cap_high: float = 3.00
    floor_a: float = 60
    floor_f: float = 90
    concept_coverage_threshold: float = 0.75
    element_repair_limit: int = 2
    runs_dir: Path = Path("runs")
    tex_engine: str = "pdflatex"
    compile_timeout_seconds: int = 180
    default_lang: str = "en-US"
    verapdf_path: Path | None = None

    @field_validator("anthropic_api_key", mode="before")
    @classmethod
    def empty_secret_is_missing(cls, value: object) -> object:
        # Treat a blank model secret as absent
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("model_input_usd_per_mtok", "model_output_usd_per_mtok", mode="before")
    @classmethod
    def empty_price_is_missing(cls, value: object) -> object:
        # Treat blank environment prices as missing values
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_anthropic_settings(self) -> "Settings":
        # Require credentials and prices for real model runs
        if self.model_provider != "anthropic":
            return self
        if self.anthropic_api_key is None:
            raise ValueError("ANTHROPIC_API_KEY is required when MODEL_PROVIDER=anthropic")
        if not self.anthropic_api_key.get_secret_value().strip():
            raise ValueError("ANTHROPIC_API_KEY is required when MODEL_PROVIDER=anthropic")
        if self.model_input_usd_per_mtok is None or self.model_input_usd_per_mtok <= 0:
            raise ValueError("MODEL_INPUT_USD_PER_MTOK is required when MODEL_PROVIDER=anthropic")
        if self.model_output_usd_per_mtok is None or self.model_output_usd_per_mtok <= 0:
            raise ValueError("MODEL_OUTPUT_USD_PER_MTOK is required when MODEL_PROVIDER=anthropic")
        return self
