import pytest

from campusmind.config import Settings, _model_setting


def test_database_url_uses_configured_values():
    settings = Settings(
        _env_file=None,
        postgres_host="10.0.0.2",
        postgres_port=5432,
        postgres_db="campusmind",
        postgres_user="campusmind",
        postgres_password="secret",
    )
    assert settings.sqlalchemy_database_url == (
        "postgresql+psycopg://campusmind:secret@10.0.0.2:5432/campusmind"
    )


def test_model_environment_takes_precedence_over_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=synthetic-file-key\n", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-environment-key")
    assert _model_setting("DEEPSEEK_API_KEY") == "synthetic-environment-key"


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_model_environment_uses_dotenv(monkeypatch, tmp_path, value):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=synthetic-file-key\n", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", value)
    assert _model_setting("DEEPSEEK_API_KEY") == "synthetic-file-key"


def test_model_placeholder_uses_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=synthetic-file-key\n", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "not-configured")
    assert _model_setting("DEEPSEEK_API_KEY") == "synthetic-file-key"


def test_missing_model_configuration_returns_none(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert _model_setting("DEEPSEEK_API_KEY") is None
