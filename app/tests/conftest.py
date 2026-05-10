import os


def pytest_configure() -> None:
    os.environ.setdefault(
        "SECRET_KEY",
        "test-secret-key-at-least-32-characters-long!",
    )
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg://minutas:minutas@127.0.0.1:5437/minutas_db",
    )
    os.environ.setdefault(
        "DATABASE_URL_SYNC",
        "postgresql+psycopg2://minutas:minutas@127.0.0.1:5437/minutas_db",
    )
