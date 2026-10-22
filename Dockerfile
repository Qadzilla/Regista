# Regista service: the clip viewer, the Librarian, on-demand rendering, and the agent pipeline over HTTP.
#
#   docker build -t regista .
#   docker run -p 8000:8000 regista
#   open http://localhost:8000
#
# ffmpeg comes from the imageio-ffmpeg wheel; DejaVu provides the font the renderer falls back to on Linux.
FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY data/synthetic ./data/synthetic
COPY data/season/league.json ./data/season/league.json
RUN pip install --no-cache-dir ".[cloud]"
# The Regista League's 30 matches, regenerated from the committed definition (deterministic; tracks come on demand)
RUN python -m regista.season --league data/season/league.json --root data/season/matches build

ENV REGISTA_DATA=/app/data/synthetic/sample \
    REGISTA_CACHE=/app/data/clips \
    REGISTA_FEEDBACK_DIR=/app/data/feedback \
    REGISTA_PRERENDER=1 \
    REGISTA_SEASON=/app/data/season/league.json \
    REGISTA_SEASON_ROOT=/app/data/season/matches \
    AZURE_MCP_COLLECT_TELEMETRY=false \
    PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1
CMD ["uvicorn", "regista.api:app", "--host", "0.0.0.0", "--port", "8000"]
