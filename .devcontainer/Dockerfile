FROM mcr.microsoft.com/devcontainers/python:1-3.13-bookworm

# Install uv from the official Docker image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install Debian packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates

# Install https://just.systems/
RUN pipx install rust-just
