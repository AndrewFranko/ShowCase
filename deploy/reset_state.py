"""Reset WORKFLOW state so every UX-assessment cycle starts identically.

Deletes only the mutable process state:
  - data/actions.duckdb        (work items, investigations, signatures index)
  - data/investigations/       (sealed investigation records)

Never touches the spine warehouse, the raw fixtures, or evidence/ packs frozen by
earlier iterations - those are inputs and history, not cycle state.
"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    targets = [ROOT / "data" / "actions.duckdb",
               ROOT / "data" / "investigations"]
    for t in targets:
        if t.is_dir():
            shutil.rmtree(t)
            print(f"  removed dir  {t.relative_to(ROOT)}")
        elif t.exists():
            t.unlink()
            print(f"  removed file {t.relative_to(ROOT)}")
        else:
            print(f"  absent       {t.relative_to(ROOT)}")
    print("workflow state reset (spine untouched)")


if __name__ == "__main__":
    main()
