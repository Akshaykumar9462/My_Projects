"""Build a Django database configuration from a private connection URL."""

from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured


def database_configuration(database_url, sqlite_path, default_ssl_mode="require"):
    """Use SQLite locally or PostgreSQL when ``DATABASE_URL`` is configured.

    Credentials stay in the environment. This function parses settings only;
    it does not connect to or modify any database.
    """
    if not database_url:
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(sqlite_path),
        }

    try:
        parsed = urlsplit(database_url)
        if parsed.scheme not in {"postgres", "postgresql"}:
            raise ImproperlyConfigured(
                "DATABASE_URL must use a postgres:// or postgresql:// URL."
            )
        database_name = unquote(parsed.path.lstrip("/"))
        if not parsed.hostname or not database_name:
            raise ImproperlyConfigured(
                "DATABASE_URL must include a database host and database name."
            )
        port = parsed.port
    except ValueError as error:
        raise ImproperlyConfigured("DATABASE_URL contains an invalid connection URL.") from error

    query_options = parse_qs(parsed.query)
    ssl_mode = query_options.get("sslmode", [default_ssl_mode])[0]
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database_name,
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": str(port or 5432),
        "OPTIONS": {"sslmode": ssl_mode},
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }

