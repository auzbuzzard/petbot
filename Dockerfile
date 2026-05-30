# PetBot runtime image.
FROM python:3.12-slim

# FFmpeg is a system binary (used for voice playback); not a pip dependency.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY petbot ./petbot

RUN pip install --no-cache-dir .

# Secrets are provided at runtime via the environment (e.g. 1Password `op run`,
# a mounted .env, or orchestrator secrets) — never baked into the image.
ENTRYPOINT ["python", "-m", "petbot"]
