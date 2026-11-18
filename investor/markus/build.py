"""Merges the frozen export with the origin table (import / wild collection) into site/data.json.

    python3 investor/markus/build.py export.json investor/markus/site/data.json
"""

import json
import sys
from pathlib import Path

here = Path(__file__).parent
data = json.load(open(sys.argv[1]))
table = json.load(open(here / "import_table.json"))
fa = [o for o in data["offers"] if o["shop"] == "FlorAccess"]


def key(s):
    return s.lower().replace("'", "").replace(" ", "")


rows = []
for r in table:
    same_name = [o for o in fa if key(o["name"]) == key(r["name"])]
    match = min(same_name, key=lambda o: abs(o["net"] - r["net"])) if same_name else None
    # Prices and formats from our own data (same day); the assessment columns from the origin note.
    rows.append(dict(r, net=match["net"] if match else r["net"], stock=match["stock"] if match else None,
                     plant=match["plant"] if match else r["name"], counted=bool(match)))
data["origin"] = rows
Path(sys.argv[2]).write_text(json.dumps(data, ensure_ascii=False))
print(f"{len(rows)} origin rows, {sum(r['counted'] for r in rows)} matched to counted offers")
