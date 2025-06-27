"""
This module has three purposes:

1. It defines all the variables (including secrets) needed to configure the application.

2. It can be imported by any module that needs access to configuration variables (and secrets). Call
   ``get_settings()`` to get a pydantic dictionary with all the variables obtained from the
   environment. Secrets are read from files.

3. It can also be run as a standalone script that generates a ``.env`` example/testing file with
   default values for all the configuration variables (no secrets, though).

It uses the *magic* of ``pydantic_settings`` package, so everything is very declarative. Look at
from https://fastapi.tiangolo.com/advanced/settings to understand how it works.
"""

import collections.abc
import functools
import typing

import pydantic
import pydantic_settings


class MainSettings(pydantic_settings.BaseSettings):
    """All the variables in this class have a default value, so they can be printed into a file to
    be used as the configuration file for testing.

    The class has custom Pydantic serializers defined that convert all variable names into
    uppercase, and all values into strings, in all dumping/serialization (e.g JSON) scenarios.
    """

    # List of configuration variables read from the environment (var names can be in uppercase):
    db_host: str = "db"
    db_port: int = 5432
    db_name: str = "test"
    db_superadmin_username: str = "postgres"
    db_role_api_service_username: str = "api_service"
    db_locale: str = "es_ES.utf8"
    db_icu_locale: str = "es-ES-x-icu"
    service_offgrid_planner_url: str

    # This makes possible for the MainSettings class to automatically read variables from a file.
    # Environment variables still take precedence.
    model_config = pydantic_settings.SettingsConfigDict(env_file=[".env"])

    @pydantic.field_serializer("db_port", return_type=str)
    def serialize_db_port_as_str(self, db_port: int):
        return str(db_port)

    @pydantic.model_serializer(mode="wrap")
    def serialize_uppercase_var_names(
        self, serializer: collections.abc.Callable[[typing.Any], dict[str, typing.Any]]
    ) -> dict[str, str]:
        original_dict: dict[str, typing.Any] = serializer(self)
        return {key.upper(): value for key, value in original_dict.items()}


@functools.lru_cache  # We memoize the result, because every call to Settings() does I/O.
def _get_main_settings():
    return MainSettings()  # type: ignore (some pydantic_settings magic happening here)


class Settings(MainSettings):
    """This class adds secrets to ``MainSettings``. They have no default value and need to be read
    from files under ``secrets_dir``.

    It inherits custom Pydantic serializers from ``MainSettings``.
    """

    # List of secrets:
    db_superadmin_password: str
    db_role_db_owner_password: str
    db_role_api_service_password: str

    # This makes possible for the Settings class to automatically read secrets from files. Secret
    # files contain only a value, and the key is the filename:
    model_config = pydantic_settings.SettingsConfigDict(
        secrets_dir=["/run/secrets", "./secrets"],
    )


@functools.lru_cache  # We memoize the result, because every call to Settings() does I/O.
def get_settings():
    return Settings()  # type: ignore (some pydantic_settings magic happening here)


def _print_dict_as_lines(data: dict[str, typing.Any]):
    for key, value in data.items():
        print(f"{key}={value}")


def main() -> None:
    main_settings_dict = _get_main_settings().model_dump()
    _print_dict_as_lines(main_settings_dict)


if __name__ == "__main__":
    main()
