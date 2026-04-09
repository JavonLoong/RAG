# Install uv
FROM python:3.12-slim
RUN pip install --no-cache-dir -i https://repo.huaweicloud.com/repository/pypi/simple uv

# Set uv timeout to 10 minutes
ENV UV_HTTP_TIMEOUT=600

# Change the working directory to the `app` directory
WORKDIR /app

# Copy the lockfile and `pyproject.toml` into the image
COPY uv.lock /app/uv.lock
COPY pyproject.toml /app/pyproject.toml

# Install dependencies
RUN uv sync --no-group dev --frozen --prerelease=allow

# Copy the project into the image
COPY . /app

# Sync the project
RUN uv sync --no-group dev --frozen --prerelease=allow

# Set PATH to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Set model, input and output paths
ENV MODEL_PATH="/data/model"
ENV INPUT_PATH="/data/input"
ENV OUTPUT_PATH="/data/output"

CMD [ "python", "-m", "algokit_example.foo" ]
