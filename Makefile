PY := .venv/Scripts/python.exe
ifeq ($(OS),)
PY := .venv/bin/python
endif

# Dagster lives in its own venv (heavy dependency tree; the app's pins stay untouched).
# Bootstrap: python -m venv .venv-dagster && .venv-dagster/Scripts/python -m pip install dagster duckdb
DAGSTER := .venv-dagster/Scripts/dagster.exe
ifeq ($(OS),)
DAGSTER := .venv-dagster/bin/dagster
endif

.PHONY: help venv seed build check test e2e e2e-deployed test-all mcp serve deploy deploy-down deploy-status dagster all clean

help:
	@echo "make all       seed fixture, build spine, run every check and test"
	@echo "make seed      generate the local source-system fixture"
	@echo "make build     run the SQL models into data/spine.duckdb"
	@echo "make check     build + data tests"
	@echo "make test      fast suite: unit, contract, guardrail, MCP (~4s)"
	@echo "make dagster   materialize the spine via Dagster (needs .venv-dagster)"
	@echo "make e2e       browser suite: Playwright against a live server (~25s)"
	@echo "make test-all  both suites, in separate processes"
	@echo "make serve     run the API on http://127.0.0.1:8000"
	@echo "make mcp       run the MCP server on stdio"
	@echo ""
	@echo "make deploy        local deploy: build spine, start, health-gate, smoke every route"
	@echo "make deploy-status show deploy state"
	@echo "make deploy-down   reclaim the port"
	@echo "make e2e-deployed  Playwright against the running deploy (not an in-process server)"

venv:
	python -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"

seed:
	$(PY) -m spine.generate

build:
	$(PY) -m spine.build

check:
	$(PY) -m spine.build --check

test:
	$(PY) -m pytest -q

e2e:
	$(PY) -m playwright install chromium
	$(PY) -m pytest tests/e2e -q

# Separate processes on purpose: Playwright's sync API and the anyio async tests
# cannot share an event loop. See the note in pyproject.toml.
test-all: test e2e

mcp:
	$(PY) -m mcp_server.server

# Materialize the spine through Dagster (verified path - see workflow/07-dagster-execution.md).
# Not `dagster asset materialize --select "*"`: Click glob-expands `*` on Windows.
dagster:
	$(DAGSTER) job execute -m orchestration.definitions -j build_spine

deploy:
	$(PY) -m deploy.local_deploy up

deploy-status:
	$(PY) -m deploy.local_deploy status

deploy-down:
	$(PY) -m deploy.local_deploy down

reset-state:
	$(PY) -m deploy.reset_state

ux-measure:
	$(PY) tests/ux/measure_tasks.py

# Drives whatever is actually deployed, across a real process boundary. Skips
# cleanly if nothing is up, so it never blocks the fast path.
e2e-deployed:
	$(PY) -m pytest tests/e2e/test_deployed.py -q

serve:
	$(PY) -m uvicorn app.main:app --reload --port 8000

all: seed check test
	@echo ""
	@echo "spine built and verified."
	@echo "  make serve     then open http://127.0.0.1:8000"
	@echo "  make e2e       browser suite (downloads Chromium on first run)"

clean:
	rm -rf data/raw data/spine.duckdb .pytest_cache

caseops-up:
	docker compose -f caseops/docker-compose.yml up -d --wait
	$(PY) -m caseops.ingest bootstrap
	$(PY) -m caseops.ingest meshes

caseops-serve:
	$(PY) -m uvicorn caseops.app:app --port 8095

caseops-tick:
	$(PY) -m caseops.ingest tick
	$(PY) -m caseops.ingest meshes

caseops-test:
	$(PY) -m pytest tests/test_caseops.py -q
