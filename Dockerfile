# ── Backend & Frontend Unified Build ───────────────────────────────────
FROM python:3.10-slim as backend-build

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ /app/backend/
COPY config.py /app/backend/ 

# ── Runtime ──────────────────────────────────────────────────────────
FROM python:3.10-slim

WORKDIR /app
COPY --from=backend-build /usr/local/lib/python3.10/site-packages/ /usr/local/lib/python3.10/site-packages/
COPY --from=backend-build /usr/local/bin/ /usr/local/bin/
COPY --from=backend-build /app/backend /app/backend

WORKDIR /app/backend
EXPOSE 8000

# 🔹 PRODUCTION OBSERVABILITY: Docker Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
