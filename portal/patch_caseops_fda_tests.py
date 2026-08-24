"""Append device-stats + FDA-monitor tests to tests/test_caseops.py."""
import pathlib

P = pathlib.Path(__file__).resolve().parents[1] / "tests" / "test_caseops.py"
s = P.read_text(encoding="utf-8")
assert "test_fda_signals_read_from_cache_only" not in s

s += '''

# ------------------------------------------------------------- device stats + FDA monitor
def test_device_stats_cover_the_fleet(client):
    stats = client.get("/api/devices/stats").json()
    assert len(stats) >= 4
    top = stats[0]
    assert top["tickets"] > 0 and top["fleet"] > 0
    assert top["mean_change_pct"] is None or 0 < float(top["mean_change_pct"]) <= 100


def test_fda_signals_read_from_cache_only(client, rig):
    """The monitor reads the cache - inserting a synthetic signal must surface
    it without any network call."""
    con = rig["con"]
    from caseops import fda as fda_mod
    con.execute(fda_mod.DDL)
    cur = con.cursor()
    payload = ('{"term":"TEST","maude_total":7,"recall_total":1,'
               '"top_problems":[{"problem":"Imaging artifact","count":5}],'
               '"recent_events":[],'
               '"recalls":[{"date":"2026-01-01","status":"Open","product":"x","reason":"y"}]}')
    cur.execute("""INSERT INTO fda_signal (make, model, payload)
                   VALUES ('Test', 'Scanner', %s)
                   ON CONFLICT (make, model) DO UPDATE SET payload = EXCLUDED.payload""",
                (payload,))
    con.commit()
    sig = client.get("/api/fda/signals").json()
    row = next(x for x in sig["signals"] if x["make"] == "Test")
    assert row["payload"]["maude_total"] == 7
    assert "unvalidated" in sig["disclaimer"]
    cur.execute("DELETE FROM fda_signal WHERE make = 'Test'")
    con.commit()


def test_fda_refresh_fails_soft_without_network(client, monkeypatch):
    """A dead network must degrade to 'errors reported', never a 500."""
    import urllib.error
    from caseops import fda as fda_mod

    def _down(*a, **k):
        raise urllib.error.URLError("no network in tests")

    monkeypatch.setattr(fda_mod.urllib.request, "urlopen", _down)
    r = client.post("/api/fda/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["updated"] == 0 and body["errors"] == body["models"] > 0
'''
P.write_text(s, encoding="utf-8")
print("tests appended")
