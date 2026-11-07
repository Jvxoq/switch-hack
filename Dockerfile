# One image for the containment service, the detector and the demo agent.
# Each compose service picks its own command; the code is the same.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first, so code edits do not reinstall them. --locked fails if uv.lock is stale.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY tripwire ./tripwire
COPY demo_agent ./demo_agent
COPY tripwire.yaml ./

# Unprivileged user. /state is the shared volume for incidents.json and flags.json.
RUN groupadd --system tripwire \
    && useradd --system --gid tripwire --home-dir /app tripwire \
    && mkdir -p /state \
    && chown tripwire:tripwire /state
USER tripwire

EXPOSE 8700
CMD ["uvicorn", "--factory", "tripwire.containment.app:create_default_app", "--host", "0.0.0.0", "--port", "8700", "--workers", "1"]
