FROM python:3.12-slim

# uv is installed with pip rather than copied from ghcr.io/astral-sh/uv: one fewer registry
# to authenticate against, and a stale ghcr credential in a developer's docker config makes
# that COPY fail with an opaque "denied: denied".
RUN pip install --no-cache-dir uv==0.12.3

WORKDIR /srv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock README.md ./
COPY app ./app
RUN uv sync --frozen

COPY . .

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
