"""Harden the action layer for multi-worker deployment + fix the badge's
accessible-name regression + make boot resilient to action-layer failures."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ---- 1. actions.py: reads are read-only, writes retry on lock contention ----
p = ROOT / "spine" / "actions.py"
s = p.read_text(encoding="utf-8")

OLD_CONNECT = '''def connect() -> duckdb.DuckDBPyConnection:
    ACTIONS_DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(ACTIONS_DB))'''

NEW_CONNECT = '''def connect(read_only: bool = False,
            _retries: int = 8) -> duckdb.DuckDBPyConnection:
    """Open the action store.

    Multi-worker reality: the deploy runs several uvicorn processes, and DuckDB
    allows many read-only processes OR one writer - never both. So reads open
    read-only (they can always coexist with each other), and writers retry with
    backoff for the brief window another worker holds the write lock. Without
    this, two concurrent requests can 500 intermittently, which surfaced as the
    client hydrating to data-ready="error" only under parallel e2e load.
    """
    import time as _time
    ACTIONS_DB.parent.mkdir(parents=True, exist_ok=True)
    if read_only and not ACTIONS_DB.exists():
        # first-ever read before any write: materialise the schema once
        connect(read_only=False).close()
    last: Exception | None = None
    for attempt in range(_retries):
        try:
            con = duckdb.connect(str(ACTIONS_DB), read_only=read_only)
            break
        except duckdb.IOException as exc:      # lock held by a sibling worker
            last = exc
            _time.sleep(0.05 * (attempt + 1))
    else:
        raise last  # type: ignore[misc]
    if read_only:
        return con'''

assert OLD_CONNECT in s
s = s.replace(OLD_CONNECT, NEW_CONNECT, 1)

# reads switch to read_only connections
for fn in ("def list_actions", "def audit_trail", "def list_signed"):
    assert fn in s
s = s.replace('''def list_actions(state: str | None = None) -> list[dict]:
    con = connect()''',
'''def list_actions(state: str | None = None) -> list[dict]:
    con = connect(read_only=True)''', 1)
s = s.replace('''def audit_trail(action_id: str) -> list[dict]:
    con = connect()''',
'''def audit_trail(action_id: str) -> list[dict]:
    con = connect(read_only=True)''', 1)
s = s.replace('''    con = connect()
    try:
        cur = con.execute("SELECT * FROM signatures ORDER BY signed_at DESC")''',
'''    con = connect(read_only=True)
    try:
        cur = con.execute("SELECT * FROM signatures ORDER BY signed_at DESC")''', 1)
p.write_text(s, encoding="utf-8")
print("actions.py hardened")

# ---- 2. client: badge keeps the accessible name; boot survives action-layer --
p = ROOT / "app" / "static" / "index.html"
s = p.read_text(encoding="utf-8")

OLD_BADGE = """  navBtn.innerHTML='Actions'+(openCount?` <span class="tag crit" style="margin-left:4px">${openCount}</span>`:'');"""
NEW_BADGE = """  // aria-hidden keeps the button's ACCESSIBLE NAME exactly "Actions" - the badge
  // is decoration. Without it, get_by_role(name="Actions") stops matching the
  // moment the first work item appears, which is a hard-to-diagnose way for every
  // downstream test and assistive technology to lose the button.
  navBtn.innerHTML='Actions'+(openCount?` <span class="tag crit" aria-hidden="true" style="margin-left:4px">${openCount}</span>`:'');"""
assert OLD_BADGE in s
s = s.replace(OLD_BADGE, NEW_BADGE, 1)

OLD_BOOT = """    wireCrossLinks();wireActions();wireSigning();
    await loadActions();await loadSigned();
    if(location.hash)applyHash();else redraw();"""
NEW_BOOT = """    wireCrossLinks();wireActions();wireSigning();
    // The action layer is auxiliary: if its store is briefly lock-contended the
    // portal must still hydrate, with the failure visible in its own lens rather
    // than taking the whole page to data-ready="error".
    try{await loadActions();await loadSigned();}
    catch(e){$('actionList').innerHTML=
      `<div class="finding">Action store unavailable: ${e.message}. Retry with "Sync findings".</div>`;}
    if(location.hash)applyHash();else redraw();"""
assert OLD_BOOT in s
s = s.replace(OLD_BOOT, NEW_BOOT, 1)
p.write_text(s, encoding="utf-8")
print("client hardened")
