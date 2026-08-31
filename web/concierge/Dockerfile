FROM node:22-alpine AS frontend-build

WORKDIR /workspace/web/concierge/frontend
COPY web/concierge/frontend/package.json web/concierge/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/concierge/frontend/ ./
RUN npm run build

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md constraints.txt ./
COPY agent ./agent
COPY control_plane ./control_plane
COPY scripts ./scripts
COPY web ./web

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -c constraints.txt -e .

COPY --from=frontend-build /workspace/web/concierge/frontend/dist /app/web/concierge/frontend/dist

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8090
CMD ["uvicorn", "web.concierge.app:app", "--host", "0.0.0.0", "--port", "8090"]
