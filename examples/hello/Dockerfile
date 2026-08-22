# Hello-world rundle worker. Build from the repo root (context must include src/):
#   docker build --platform linux/amd64 -f examples/hello/Dockerfile -t dburenok/rundle-hello .
FROM python:3.12-slim

WORKDIR /app

# install rundle[worker] from this repo (PyPI release lags the source)
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[worker]"

COPY examples/hello/model.py .
CMD ["python", "-m", "rundle.worker", "model:predict"]
