# Case Spine — production image.
#
# Multi-stage so the runtime layer carries no build toolchain and no test
# dependencies. The spine is BUILT AT IMAGE BUILD TIME into a read-only DuckDB
# file baked into the image, which makes the container immutable and startup
# instant. In the real deployment this stage is replaced by a Redshift connection
# string and the runtime becomes stateless; here it keeps the whole thing runnable
# with no external service.
#
# Regulatory note: the runtime runs as a non-root user with a read-only root
# filesystem and no write path to the data. The API is read-only by design (see
# validation/csa-validation-plan.md); the container enforces that rather than
# trusting it.

# ---------------------------------------------------------------- build stage
FROM python:3.11-slim AS build

WORKDIR /build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml README.md ./
COPY spine ./spine
COPY app ./app
COPY orchestration ./orchestration
COPY mcp_server ./mcp_server

RUN pip install --no-cache-dir --target=/deps duckdb fastapi "uvicorn[standard]"

# Seed the fixture and materialise the spine. --check runs the 11 data tests, so a
# build that produces a bad warehouse FAILS THE IMAGE BUILD rather than shipping.
ENV PYTHONPATH=/deps:/build
RUN python -m spine.generate \
 && python -m spine.build --check

# ---------------------------------------------------------------- runtime stage
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="Case Spine" \
      org.opencontainers.image.description="Read-only analytics over an AI analysis pipeline" \
      io.heartflow.regulatory-class="csa-production-quality-system" \
      io.heartflow.data-class="no-phi"

# non-root, fixed uid so volume permissions are predictable
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin spine

WORKDIR /srv
ENV PYTHONPATH=/deps \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

COPY --from=build /deps /deps
COPY --from=build --chown=root:root /build/spine   /srv/spine
COPY --from=build --chown=root:root /build/app     /srv/app
COPY --from=build --chown=root:root /build/mcp_server /srv/mcp_server
# the materialised warehouse, owned by root and read-only to the app user
COPY --from=build --chown=root:root /build/data    /srv/data

# Writable state for the action layer and signed evidence. The rootfs is
# read-only; this directory is the ONE declared write surface, mounted as a
# volume by compose so workflow state survives container replacement. Created
# here (owned by the app user) so a named volume inherits the ownership.
RUN mkdir -p /state && chown spine:spine /state
ENV ACTIONS_DB=/state/actions.duckdb     EVIDENCE_DIR=/state/evidence     INVESTIGATION_DIR=/state/investigations

USER spine
EXPOSE 8000

# The API's own overview endpoint is the health check: it exercises the DuckDB
# connection and the metric layer, so a green health check means the stack works
# rather than merely that a socket is open.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/overview', timeout=4).status==200 else 1)"

# No --reload. Multiple workers. This is a production server, not a dev server.
CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--log-level", "info", "--access-log"]
