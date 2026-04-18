FROM python:3.12-slim

RUN pip install --no-cache-dir -i https://repo.huaweicloud.com/repository/pypi/simple uv

ENV UV_HTTP_TIMEOUT=600

WORKDIR /app

COPY uv.lock /app/uv.lock
COPY pyproject.toml /app/pyproject.toml

RUN uv sync --no-group dev --frozen --prerelease=allow

COPY . /app

RUN uv sync --no-group dev --frozen --prerelease=allow

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/apps/jiwenlong-rag-console/chroma_rag_poc/src"

WORKDIR /app/apps/jiwenlong-rag-console

EXPOSE 8000

CMD ["python", "server.py"]
