import os

from src.core.config import Settings


def test_settings_accept_release_debug_value() -> None:
    previous_debug = os.environ.get("DEBUG")
    try:
        os.environ["DEBUG"] = "release"
        settings = Settings(
            database_url="postgresql://postgres:postgres@localhost:5432/test_db",
            _env_file=None,
        )
    finally:
        if previous_debug is None:
            os.environ.pop("DEBUG", None)
        else:
            os.environ["DEBUG"] = previous_debug

    assert settings.debug is False
