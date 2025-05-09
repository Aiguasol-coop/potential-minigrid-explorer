"""This module declares an alternative entry point for the API service, meant to be called directly
with ``uv run`` or ``python``.

It is not strictly needed. See module ``.main``.
"""

import pathlib

import fastapi_cli.cli


def main() -> None:
    """Alternative entry point for running the API service without the ``fastapi`` executable."""

    print("FastAPI will take control from now on.")
    fastapi_cli.cli.run(pathlib.Path("src/app/main.py"))


if __name__ == "__main__":
    main()
