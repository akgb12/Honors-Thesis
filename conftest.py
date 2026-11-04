import pytest


@pytest.fixture(autouse=True)
def _no_real_model_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    # Backend settings load .env on import, so keep real credentials out of every test
    for name in (
        "ANTHROPIC_API_KEY",
        "MODEL_INPUT_USD_PER_MTOK",
        "MODEL_OUTPUT_USD_PER_MTOK",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
