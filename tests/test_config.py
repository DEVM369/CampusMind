from campusmind.config import Settings


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
