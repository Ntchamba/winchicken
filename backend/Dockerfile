# --- build stage: install Python deps into a venv -------------------------
FROM python:3.12-slim AS build

WORKDIR /app
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# --- runtime stage ----------------------------------------------------------
FROM python:3.12-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser

WORKDIR /app
COPY --from=build /venv /venv
ENV PATH="/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --chown=appuser:appuser . .

# /app/logs (factory-reset audit trail, config/settings.py LOGGING) is a named volume in
# docker-compose.yml, not part of the source tree — created+owned here so that when Docker
# first mounts a fresh empty named volume over this path, it seeds the volume from this
# image layer's content *and ownership* (documented Docker behavior), giving appuser write
# access from the start instead of the volume defaulting to root:root.
RUN mkdir -p /app/logs && chown appuser:appuser /app/logs

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -f http://localhost:8000/api/health/ || exit 1

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
