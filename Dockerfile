# 🏗️ Stage 1: Build the Application
FROM python:3.13-slim-bookworm AS builder

# Install:
# - git, needed for version calculation
# - gcc + libpq, needed for psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Disable Python downloads, because we want to use the system interpreter across both images. If
# using a managed Python version, it needs to be copied from the build image into the final image;
ENV UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install dependencies
#
# We don't use --no-dev because it's a testing image and we need dev deps to create faker data
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project

# We need to copy the full workdir, as the build relies on being in a git repository, even if we
# should ideally only need the ./database/postgres-setup.d/ and ./src dirs.
ADD . /app

# Build app
#
# We don't use --no-dev because it's a testing image and we need dev deps to create faker data
RUN uv sync --frozen



# 🚀 Stage 2: Final Image
FROM python:3.13-slim-bookworm AS runner

# Install:
# - libpq, needed for psycopg
# - gnupg, needed for installing psql
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gnupg \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Install up-to-date version of psql
RUN apt-get update && apt-get install -y wget ca-certificates && \
    echo "deb http://apt.postgresql.org/pub/repos/apt $(grep VERSION_CODENAME /etc/os-release | cut -d= -f2)-pgdg main" | tee /etc/apt/sources.list.d/pgdg.list && \
    wget -qO - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add - && \
    apt-get update && apt-get install -y --no-install-recommends postgresql-client-17 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder --chown=app:app /app/src /app/src

COPY --from=builder --chown=app:app /app/database/postgres-setup.d /app/database/postgres-setup.d

COPY --from=builder --chown=app:app /app/.venv /app/.venv

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

WORKDIR /app

# Run the FastAPI application by default
CMD [ "sh", "-c", "sleep 0 \
    && python src/scripts/db_run_sql_files.py /app/database/postgres-setup.d \
    && python src/scripts/db_load_data.py --tables exploration simulation cluster \
    && uvicorn main:api --app-dir src/app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
