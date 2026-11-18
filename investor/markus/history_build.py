"""Price development: earliest archived FlorAccess price vs. the 18.11.2026 price, same plant in the same pot size.
Today's side is the cheapest current offer of that plant and pot (conservative: understates rises; for Kerrii it is
the single leaf, because archived Kerrii offers can't be told apart from leaves).

    python3 investor/markus/history_build.py archive.json investor/markus/site/data.json investor/markus/site/history.json
"""

import json
import statistics
import sys
from pathlib import Path

archive = json.load(open(sys.argv[1]))
data = json.load(open(sys.argv[2]))
now = [o for o in data["offers"] if o["shop"] == "FlorAccess" and o["net"]]
norm = lambda p: (p or "").replace(",", ".").strip()

first = {}
for r in archive:
    k = (r["plant_key"], norm(r["pot"]))
    if r["net"] and k not in first:
        first[k] = r
pairs = []
for (pk, pot), r in first.items():
    cur = [o for o in now if o["plant_key"] == pk and norm(o["pot"]) == pot]
    if not cur:
        continue
    c = min(cur, key=lambda o: o["net"])
    pairs.append({"plant": c["plant"], "pot": pot, "then_day": r["day"], "then": r["net"], "now": c["net"],
                  "change": c["net"] / r["net"] - 1})
pairs.sort(key=lambda p: -p["change"])
ch = [p["change"] for p in pairs]
out = {"day": data["day"], "pairs": pairs, "median_change": statistics.median(ch),
       "cheaper": sum(c < 0 for c in ch), "n": len(ch)}
Path(sys.argv[3]).write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(f"{len(pairs)} pairs, median {out['median_change']:+.1%}, cheaper {out['cheaper']}")
for p in pairs:
    print(f"  {p['plant'][:34]:34} {p['pot']:8} {p['then_day']} {p['then']:6.2f} -> {p['now']:6.2f} {p['change']:+.0%}")
