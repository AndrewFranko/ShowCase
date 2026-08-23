"""Narrow the write-route guardrail (per validation plan change control), amend
the plan, and append the action-layer test suite."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ---- 1. guardrail tests -----------------------------------------------------
p = ROOT / "tests" / "test_spine.py"
s = p.read_text(encoding="utf-8")

OLD = '''def test_api_exposes_no_write_routes():
    """Read-only by construction. A write path, or any endpoint that dispositions
    a case, would move this from production/QMS software under Computer Software
    Assurance into device software under a different regime entirely."""
    for route in app.routes:
        methods = getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}
        assert methods <= {"GET"}, f"{route.path} exposes {methods}"'''

NEW = '''def test_write_routes_are_confined_to_the_action_layer():
    """The narrowed rule, re-assessed per the validation plan's change control
    (section 9): the SPINE surface stays GET-only - no endpoint may write to a
    case, a result, or the warehouse the metrics read. Writes exist ONLY on the
    action layer (finding workflow + evidence signatures), which persists to a
    separate store. Acknowledging a FINDING is QMS workflow; dispositioning a
    CASE is device software and remains forbidden."""
    WRITABLE_PREFIXES = ("/api/actions", "/api/evidence/")
    for route in app.routes:
        methods = getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}
        path = getattr(route, "path", "")
        if methods - {"GET"}:
            assert methods == {"POST"}, f"{path} exposes {methods}"
            assert path.startswith(WRITABLE_PREFIXES), \\
                f"write route {path} outside the action layer"
            # a write route must never take a case identifier
            assert "case" not in path, f"{path} writes against a case"


def test_action_store_is_not_the_spine():
    """The write path and the warehouse must be different files, and the spine
    dependency must stay read-only in source - the property that keeps every
    metric untouched by the workflow layer."""
    import inspect
    from app import main as app_main
    from spine import actions as act
    assert act.ACTIONS_DB.resolve() != app_main.DB.resolve()
    assert "read_only=True" in inspect.getsource(app_main.db)'''

assert OLD in s, "guardrail anchor missing"
s = s.replace(OLD, NEW, 1)

SUITE = '''

# ------------------------------------------------------------------ action layer
import pathlib as _pathlib  # noqa: E402

from spine import actions as actions_mod  # noqa: E402


@pytest.fixture()
def action_store(tmp_path, monkeypatch):
    """Isolated action store per test - the real one is live workflow state."""
    monkeypatch.setattr(actions_mod, "ACTIONS_DB", tmp_path / "actions.duckdb")
    return actions_mod


def test_sync_is_idempotent_and_typed(action_store, con):
    first = action_store.sync_findings(con)
    assert first["total_items"] > 0
    kinds = {c["kind"] for c in first["created"]}
    assert kinds <= set(action_store.KINDS)
    again = action_store.sync_findings(con)
    assert again["created"] == [], "sync resurrected or duplicated items"


def test_lifecycle_enforces_the_state_machine(action_store, con):
    aid = action_store.sync_findings(con)["created"][0]["action_id"]
    with pytest.raises(ValueError):
        action_store.transition(aid, "investigating", "a", "skip not allowed")
    action_store.transition(aid, "acknowledged", "andrii", "triaging")
    action_store.transition(aid, "resolved", "andrii", "fixed upstream")
    with pytest.raises(ValueError):
        action_store.transition(aid, "acknowledged", "andrii", "terminal only reopens")
    action_store.transition(aid, "open", "andrii", "reopening - fix regressed")


def test_audit_requires_actor_and_note(action_store, con):
    """An anonymous or unexplained transition is not an audit trail."""
    aid = action_store.sync_findings(con)["created"][0]["action_id"]
    with pytest.raises(ValueError):
        action_store.transition(aid, "acknowledged", "", "note")
    with pytest.raises(ValueError):
        action_store.transition(aid, "acknowledged", "andrii", "  ")


def test_audit_trail_is_complete_and_ordered(action_store, con):
    aid = action_store.sync_findings(con)["created"][0]["action_id"]
    action_store.transition(aid, "acknowledged", "a1", "n1")
    action_store.transition(aid, "investigating", "a2", "n2")
    trail = action_store.audit_trail(aid)
    assert [e["to_state"] for e in trail] == ["open", "acknowledged", "investigating"]
    assert all(e["note"] for e in trail)


def test_items_pin_the_warehouse_state(action_store, con):
    from spine import evidence as ev
    action_store.sync_findings(con)
    items = action_store.list_actions()
    grain = ev.spine_fingerprint(con)["grain_sha256"][:16]
    assert all(i["grain_sha"] == grain for i in items), \\
        "work items must record the warehouse state they were raised from"


def test_signature_refuses_an_unverifiable_pack(action_store, con):
    from spine import evidence as ev
    pack = ev.build_frontier_pack(con)
    tampered = json.loads(json.dumps(pack, default=str))
    tampered["content"]["result"]["volume_share"] = 0.99
    with pytest.raises(ValueError):
        action_store.sign_pack(tampered, "andrii", "qe", "should fail")


def test_signature_roundtrip_verifies_on_read(action_store, con, tmp_path, monkeypatch):
    from spine import evidence as ev
    monkeypatch.setattr(ev, "EVIDENCE_DIR", tmp_path / "evidence")
    pack = ev.build_frontier_pack(con)
    sig = action_store.sign_pack(pack, "andrii", "quality engineer", "release review")
    listed = action_store.list_signed()
    assert listed[0]["verification"] == "verified"
    assert listed[0]["manifest_sha"] == pack["manifest_sha256"]
    # break the frozen file: the list must SAY so, not hide it
    path = _pathlib.Path(sig["pack_path"])
    broken = json.loads(path.read_text(encoding="utf-8"))
    broken["content"]["claim"] = "edited after signing"
    path.write_text(json.dumps(broken), encoding="utf-8")
    assert "BROKEN" in action_store.list_signed()[0]["verification"]


def test_briefing_is_a_complete_artifact(client):
    html = client.get("/api/briefing").text
    for section in ("Findings requiring action", "Signed evidence",
                    "Subgroup escalations", "warehouse grain"):
        assert section in html
    dl = client.get("/api/briefing", params={"download": "true"})
    assert "attachment" in dl.headers.get("content-disposition", "")
'''
s = s.rstrip() + "\n" + SUITE
p.write_text(s, encoding="utf-8")
print("guardrails narrowed + action suite appended")

# ---- 2. validation plan amendment ------------------------------------------
vp = ROOT / "validation" / "csa-validation-plan.md"
v = vp.read_text(encoding="utf-8")
anchor = "*Prepared as a reference artifact"
assert anchor in v
v = v.replace(anchor, """## 9. Amendment A — the action layer (change-control re-assessment)

Trigger: §6 item 1 (introduction of non-GET routes). Re-assessed as required.

**Added:** a finding-workflow layer — work items derived from findings (disparity
escalations, confirmed regressions, excess-rejection sites, hazard review), a
five-state lifecycle with mandatory actor and note on every transition, an
append-only event log, evidence-pack signatures (verify-before-sign, re-verify on
every read), and a generated HTML briefing.

**Classification outcome: unchanged — production and quality-system software.**
The write path persists to a separate store (`data/actions.duckdb`); the spine
connection remains read-only in source; no write route accepts a case identifier;
no output reaches a clinician or alters a delivered analysis. Managing findings is
the same software class as complaint handling (ISO 13485 §8.2.2 feedback and §8.5
improvement workflows) — QMS software squarely inside CSA scope. Dispositioning a
*case* remains the forbidden boundary, now enforced by
`test_write_routes_are_confined_to_the_action_layer` and
`test_action_store_is_not_the_spine`.

**Process risk of the additions:** Medium. A wrong workflow state misleads an
internal user; no patient-facing path exists. Assurance: scripted lifecycle tests
(legal and illegal transitions, mandatory audit fields, idempotent sync,
verify-before-sign) run on every commit.

---

*Prepared as a reference artifact""", 1)
vp.write_text(v, encoding="utf-8")
print("validation plan amended")
