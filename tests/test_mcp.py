"""
MCP server tests.

Two layers, deliberately:

  in-memory  Most tests connect a Client directly to the MCPServer instance. This
             exercises the real protocol - schema generation, validation, dispatch,
             serialisation - without subprocess overhead, so the governance suite
             runs in a second and nobody is tempted to skip it.

  subprocess One test spawns `python -m mcp_server.server` over real stdio and
             completes a handshake, because the in-memory path does not prove the
             module is launchable the way an agent host will launch it.

The governance tests are the point. An MCP surface over a clinical warehouse is a
liability unless it is provably constrained, and "provably" means a test rather
than a paragraph in a README.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="mcp SDK not installed")

from mcp import Client, StdioServerParameters                # noqa: E402
from mcp.client.stdio import stdio_client                    # noqa: E402
from mcp.client.session import ClientSession                 # noqa: E402

from app.main import DB                                      # noqa: E402
from mcp_server.server import mcp                            # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    if not DB.exists():
        pytest.skip("spine not built - run `python -m spine.generate && python -m spine.build`")
    async with Client(mcp) as c:
        yield c


async def call(client: Client, name: str, args: dict | None = None) -> dict:
    """Call a tool and decode its JSON payload the way an agent host would."""
    result = await client.call_tool(name, args or {})
    if getattr(result, "structured_content", None):
        return result.structured_content
    assert result.content, f"{name} returned no content"
    return json.loads(result.content[0].text)


TOOL_NAMES = {
    "spine_overview", "query_metrics", "automation_frontier", "hazard_status",
    "trace_complaint", "compare_releases", "inspect_case",
    # iteration 02
    "subgroup_disparity",
    # iteration 04
    "evidence_pack",
}


# ------------------------------------------------------------------ protocol
async def test_server_advertises_exactly_its_tools(client):
    names = {t.name for t in (await client.list_tools()).tools}
    assert names == TOOL_NAMES


async def test_every_tool_documents_its_semantics(client):
    """A model that does not know 0.80 is the ischemia threshold will pick the
    wrong tool confidently. The description is where that knowledge has to live."""
    for tool in (await client.list_tools()).tools:
        assert tool.description and len(tool.description) > 120, \
            f"{tool.name} is under-described for agent use ({len(tool.description or '')} chars)"
        assert (tool.input_schema or {}).get("type") == "object"


async def test_every_tool_is_annotated_read_only(client):
    """readOnlyHint is the machine-readable form of the regulatory boundary - a
    host can refuse to run anything lacking it."""
    for tool in (await client.list_tools()).tools:
        ann = tool.annotations
        assert ann is not None, f"{tool.name} carries no annotations"
        assert ann.read_only_hint is True, f"{tool.name} is not marked read-only"
        assert ann.destructive_hint is False


async def test_server_instructions_carry_the_key_distinction(client):
    """The cost/safety metric confusion is the most likely way an agent gets this
    domain wrong, so the server states it up front."""
    text = (client.instructions or "").lower()
    assert "actionable_correction_rate" in text
    assert "safety" in text and "cost" in text


# ------------------------------------------------------------------ behaviour
async def test_overview_returns_headline_metrics(client):
    body = await call(client, "spine_overview")
    for key in ("cases", "accepted_cases", "reject_rate",
                "actionable_correction_rate", "complaints"):
        assert key in body
    assert 0.0 <= body["actionable_correction_rate"] <= 1.0


async def test_query_metrics_groups_by_dimension(client):
    body = await call(client, "query_metrics", {
        "measures": ["accepted_cases", "actionable_correction_rate"],
        "group_by": ["model_version"],
    })
    assert body["rows"], "expected grouped rows"
    assert {"model_version", "accepted_cases", "actionable_correction_rate"} <= set(
        body["rows"][0])
    assert body["provenance"]["group_by"] == ["model_version"]


async def test_results_carry_provenance(client):
    """An agent should cite, not assert. Provenance is what it cites."""
    body = await call(client, "query_metrics", {"measures": ["cases"]})
    p = body["provenance"]
    assert p["filter"]
    assert p["definition_source"].startswith("spine/metrics.py")


async def test_frontier_reports_tolerance_and_threshold(client):
    body = await call(client, "automation_frontier", {"tolerance": 0.08})
    at = body["at_tolerance"]
    assert at["eligible_strata"] <= at["total_strata"]
    assert 0.0 <= at["volume_share"] <= 1.0
    assert body["provenance"]["threshold"] == "FFR 0.80"


async def test_trace_complaint_places_the_case_in_a_cohort(client):
    body = await call(client, "trace_complaint", {"complaint_id": 0})
    assert body["complaint"]["case_id"] is not None
    assert body["complaint"]["site_name"]
    assert body["stratum_cohort"]["accepted_cases"] > 0


async def test_compare_releases_gates_on_significance(client):
    body = await call(client, "compare_releases")
    for r in body["comparisons"]:
        if r["signal"] in ("regression", "improved"):
            assert r["p_value"] < 0.05, f"{r['signal']} flagged at p={r['p_value']}"
    assert "unconfirmed" in body["_note"]


async def test_hazard_status_warns_that_a_match_is_not_a_harm(client):
    body = await call(client, "hazard_status")
    assert body["hazards"]
    assert "not a harm" in body["_note"].lower()
    assert body["hazards"][0]["by_release"]


async def test_inspect_case_joins_every_source(client):
    body = await call(client, "inspect_case", {"case_id": 1})
    for key in ("site_name", "scanner_make", "model_version", "stratum", "hazards"):
        assert key in body


# ------------------------------------------------------------------ governance
async def test_there_is_no_sql_tool(client):
    """The single most important assertion in this file.

    A free-text SQL tool over a clinical warehouse makes agent output unauditable,
    lets the model compute a metric three different ways, and gives it a route to
    columns the PHI boundary exists to keep it away from.
    """
    tools = (await client.list_tools()).tools
    names = {t.name for t in tools}
    for banned in ("run_sql", "execute_sql", "sql", "raw_query", "execute", "eval"):
        assert banned not in names

    for tool in tools:
        props = set((tool.input_schema or {}).get("properties", {}))
        leaky = props & {"sql", "query", "statement", "expression", "where", "filter"}
        assert not leaky, f"{tool.name} accepts free-text query input: {leaky}"


async def test_unknown_measure_is_rejected_not_guessed(client):
    body = await call(client, "query_metrics", {"measures": ["profit_margin"]})
    assert "error" in body
    assert "profit_margin" in body["error"]


async def test_unknown_dimension_is_rejected(client):
    body = await call(client, "query_metrics", {
        "measures": ["cases"], "group_by": ["analyst_id"]})
    assert "error" in body


async def test_no_tool_leaks_identifying_fields(client):
    """Sweep every tool's output for anything resembling patient or analyst
    identity. The spine should make this impossible; this proves it."""
    banned = {"patient_id", "mrn", "accession", "accession_number", "study_uid",
              "series_uid", "sop_uid", "patient_name", "analyst_id", "analyst_name",
              "pixel_data"}
    payloads = [
        await call(client, "spine_overview"),
        await call(client, "inspect_case", {"case_id": 1}),
        await call(client, "trace_complaint", {"complaint_id": 0}),
        await call(client, "hazard_status"),
        await call(client, "automation_frontier"),
        await call(client, "compare_releases"),
        await call(client, "query_metrics",
                   {"measures": ["cases"], "group_by": ["stratum"]}),
    ]
    blob = json.dumps(payloads, default=str).lower()
    for field in banned:
        assert field not in blob, f"a tool leaked {field!r}"


async def test_missing_record_errors_rather_than_inventing(client):
    """An agent-facing tool must not return an empty object that reads as
    'no findings' when the real answer is 'that record does not exist'."""
    for tool, args in [("inspect_case", {"case_id": 99999999}),
                       ("trace_complaint", {"complaint_id": 99999999})]:
        body = await call(client, tool, args)
        assert "error" in body, f"{tool} invented a result for a missing record"


async def test_limit_is_capped_at_the_protocol_boundary(client):
    """An agent asking for everything must not be able to pull the whole table.

    The cap is enforced by JSON-Schema validation before the tool body runs, so an
    over-large request is refused at the protocol layer rather than silently
    truncated. That is the stronger guarantee: the agent is told it asked for
    something it cannot have, instead of receiving a partial answer it may treat
    as complete.
    """
    result = await client.call_tool("query_metrics", {
        "measures": ["cases"], "group_by": ["site_id"], "limit": 5000})
    assert result.is_error, "an over-limit request should be refused"
    text = result.content[0].text.lower()
    assert "limit" in text and ("less than" in text or "validation" in text)

    # and the permitted ceiling still works
    ok = await call(client, "query_metrics", {
        "measures": ["cases"], "group_by": ["site_id"], "limit": 500})
    assert len(ok["rows"]) <= 500


# ------------------------------------------------------------------ deployment
async def test_server_launches_over_real_stdio():
    """The in-memory transport does not prove the module is launchable the way an
    agent host launches it. This one spawns the actual subprocess."""
    if not DB.exists():
        pytest.skip("spine not built")
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "mcp_server.server"], cwd=str(ROOT))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = {t.name for t in (await session.list_tools()).tools}
            assert names == TOOL_NAMES
            result = await session.call_tool("spine_overview", {})
            body = (result.structured_content
                    or json.loads(result.content[0].text))
            assert "actionable_correction_rate" in body


# ------------------------------------------------------------------ iterations 02/04
async def test_disparity_tool_warns_against_the_equity_misreading(client):
    """The spine holds no demographics. An agent describing clinical subgroup
    analysis as equity analysis makes a category error with regulatory weight, so
    the tool description has to say so."""
    tools = {t.name: t for t in (await client.list_tools()).tools}
    desc = tools["subgroup_disparity"].description.lower()
    assert "not demographic equity" in desc or "no demographics" in desc
    assert "escalate" in desc and "fdr_significant" in desc


async def test_disparity_tool_separates_significant_from_escalated(client):
    body = await call(client, "subgroup_disparity")
    for finding in body["findings"]:
        for arm in finding["arms"]:
            if arm["escalate"]:
                assert arm["fdr_significant"]
                assert arm["disparity_vs_best"] >= body["policy"]["min_disparity_ratio"]


async def test_evidence_pack_tool_returns_a_verifiable_pack(client):
    from spine import evidence
    body = await call(client, "evidence_pack", {"claim": "automation_frontier"})
    ok, msg = evidence.verify(body)
    assert ok, msg
    assert body["content"]["limitations"]
    assert body["content"]["population"]["reference"]["n"] > 0


async def test_evidence_pack_is_reproducible_through_the_tool(client):
    a = await call(client, "evidence_pack", {"claim": "automation_frontier"})
    b = await call(client, "evidence_pack", {"claim": "automation_frontier"})
    assert a["manifest_sha256"] == b["manifest_sha256"], \
        "identical warehouse state produced two different manifest hashes"


async def test_evidence_pack_rejects_an_unknown_claim(client):
    body = await call(client, "evidence_pack", {"claim": "quarterly_revenue"})
    assert "error" in body and "available" in body
