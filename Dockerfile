FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10001 sandbox

COPY schemas.py wire.py /app/
COPY sandbox/runner.py /app/runner.py

USER sandbox

# The submission directory is mounted read-only at /submission by the engine.
CMD ["python", "/app/runner.py"]
