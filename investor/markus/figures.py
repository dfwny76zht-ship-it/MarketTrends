"""Print figures for Section 5.5 of the business plan (Pages): 16.8 cm wide, Carlito, greys only, PDF (vector) + PNG 300 dpi.
Data: site/data.json (frozen 18.11.2026) and site/history.json (archived FlorAccess prices vs. today).

    python figures.py <carlito-regular.ttf> <carlito-bold.ttf> <out-dir>     (needs matplotlib)
"""

import json
import statistics
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

here = Path(__file__).parent
reg, bold, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
for f in (reg, bold):
    font_manager.fontManager.addfont(f)
plt.rcParams.update({"font.family": "Carlito", "font.size": 9.5, "pdf.fonttype": 42, "svg.fonttype": "none",
                     "axes.edgecolor": "none", "figure.facecolor": "white", "axes.facecolor": "white"})
CM = 1 / 2.54
W = 16.8 * CM
DARK, LIGHT, INK, MUTED = "#4a4a4a", "#b3b3b3", "#1f1f1f", "#707070"


def pct(v):  # 51 %, half up like the report text
    return f"{Decimal(str(v * 100)).quantize(Decimal('1'), ROUND_HALF_UP)} %"


def eur(v):
    return f"{Decimal(str(v)).quantize(Decimal('0.01'), ROUND_HALF_UP)}".replace(".", ",") + " €"


def header(fig, title, sub=None):
    fig.text(0, 1, title, fontsize=10.5, fontweight="bold", color=INK, va="top", ha="left")
    if sub:
        fig.text(0, 1 - 0.55 * CM / fig.get_figheight(), sub, fontsize=9, color=MUTED, va="top", ha="left")


def footer(fig, text):
    fig.text(0, 0, text, fontsize=8.5, color=MUTED, va="bottom", ha="left")


def save(fig, name):
    for ext in ("pdf", "png"):
        fig.savefig(out / f"{name}.{ext}", dpi=300, facecolor="white")
    plt.close(fig)


# ---------- Grafik 1: Pflanzen und Warenwert je Gruppe ----------
data = json.load(open(here / "site/data.json"))
par = {g["id"]: g["parent"] for g in data["groups"]}
lab = {g["id"]: g["label"] for g in data["groups"]}
FA = [o for o in data["offers"] if o["shop"] == "FlorAccess"]
top = lambda o: "other" if o["group"] is None else (par[o["group"]] or o["group"])
gid = lambda word: next(i for i, l in lab.items() if l.lower().startswith(word) and par[i] is None)
leaf = next(i for i in lab if par[i] is not None)
S = sum(o["stock"] or 0 for o in FA)
V = sum((o["stock"] or 0) * o["net"] for o in FA)
rows = [("Carnosa-artig", lambda o: top(o) == gid("carnosa")),
        ("Kerrii-artig", lambda o: top(o) == gid("kerrii")),
        ("davon Einzelblätter ohne Knoten", lambda o: o["group"] == leaf),
        ("Wayettii-artig", lambda o: top(o) == gid("wayet")),
        ("Übrige Arten", lambda o: top(o) == "other")]
vals = []
for name, f in rows:
    xs = [o for o in FA if f(o)]
    vals.append((name, sum(o["stock"] or 0 for o in xs) / S, sum((o["stock"] or 0) * o["net"] for o in xs) / V,
                 statistics.median(o["net"] for o in xs)))

fig = plt.figure(figsize=(W, 6 * CM))
ax = fig.add_axes([0.30, 0.13, 0.52, 0.64])
bh = 0.36
for i, (name, s, v, m) in enumerate(vals):
    y = -i
    ax.barh(y + bh / 2, s, height=bh, color=DARK)
    ax.barh(y - bh / 2, v, height=bh, color=LIGHT)
    ax.text(s + 0.008, y + bh / 2, pct(s), va="center", fontsize=9, color=INK)
    ax.text(v + 0.008, y - bh / 2, pct(v), va="center", fontsize=9, color=INK)
    sub = name.startswith("davon")
    yt = ax.get_yaxis_transform()
    ax.text(-0.02, y, name, transform=yt, ha="right", va="center", fontsize=9.5, clip_on=False,
            color=MUTED if sub else INK, style="italic" if sub else "normal")
    ax.text(1 + 0.18 / 0.52, y, eur(m), transform=yt, ha="right", va="center", fontsize=9.5, color=INK, clip_on=False)
ax.set_xlim(0, 0.70)
ax.set_ylim(-len(vals) + 0.45, 0.55)
ax.axis("off")
fig.text(1, 0.80, "Medianpreis netto", ha="right", va="bottom", fontsize=8.5, color=MUTED)
header(fig, "Pflanzen und Warenwert je Gruppe")
lx = 0.0
for color, label in ((DARK, "Anteil an den Pflanzen"), (LIGHT, "Anteil am Warenwert zu Verkaufspreisen")):
    fig.patches.append(matplotlib.patches.Rectangle((lx, 0.805), 0.012, 0.035, transform=fig.transFigure, color=color))
    fig.text(lx + 0.018, 0.822, label, va="center", fontsize=8.5, color=INK)
    lx += 0.04 + len(label) * 0.0105
footer(fig, f"FlorAccess, eigene Auswertung, Stand 18.11.2026 ({len(FA)} Angebote, "
            f"{len({o['species_key'] for o in FA})} Arten, {f'{S:,}'.replace(',', '.')} Pflanzen)")
save(fig, "grafik1_pflanzen_warenwert")

# ---------- Grafik 2: Großhandelspreise seit 2019 ----------
h = json.load(open(here / "site/history.json"))
pairs = sorted(h["pairs"], key=lambda p: p["change"])  # bottom-up: smallest first, largest on top
n, cheaper = h["n"], h["cheaper"]
med = h["median_change"]
assert (n, cheaper, round(med * 100)) == (20, 6, 24), (n, cheaper, med)


def label(p):
    name = p["plant"].replace("Hoya ", "").replace("'", "’").replace("’", "‘", 1)
    return f"{name} {p['pot'].replace(' cm', '').replace('.', ',')} cm ({p['then_day'][:4]})"


fig = plt.figure(figsize=(W, 11.5 * CM))
ax = fig.add_axes([0.42, 0.07, 0.36, 0.82])
for i, p in enumerate(pairs):
    c = p["change"] * 100
    ax.barh(i, c, height=0.66, color=LIGHT if c < 0 else DARK)
    sign = "+" if c > 0 else "−"
    ax.text(c + (4 if c >= 0 else -4), i, f"{sign}{abs(round(c))} %", va="center", ha="left" if c >= 0 else "right", fontsize=8.5,
            color=INK, zorder=5, bbox=dict(facecolor="white", edgecolor="none", pad=0.6))
    yt = ax.get_yaxis_transform()
    ax.text(-0.02, i, label(p), transform=yt, ha="right", va="center", fontsize=9, color=INK, clip_on=False)
    ax.text(1 + 0.22 / 0.36, i, f"{eur(p['then'])} → {eur(p['now'])}", transform=yt, ha="right", va="center", fontsize=9, color=INK, clip_on=False)
ax.axvline(0, color=MUTED, lw=0.6)
ax.axvline(med * 100, color=INK, lw=0.9, ls=(0, (4, 3)), zorder=1)
ax.text(med * 100 + 3, len(pairs) - 0.2, f"Median +{round(med * 100)} %", fontsize=8.5, color=INK, va="bottom")
ax.set_xlim(-95, 300)
ax.set_ylim(-0.6, len(pairs) + 0.5)
ax.axis("off")
header(fig, "Großhandelspreise seit 2019: gleiche Art und Topfgröße, ältester Archivpreis gegen heute",
       f"{n} Paare: {n - cheaper} teurer (dunkelgrau), {cheaper} günstiger (hellgrau)")
footer(fig, "FlorAccess, Internet Archive, eigene Auswertung · Stand 18.11.2026 · Preise netto; heute je das günstigste Angebot gleicher Topfgröße")
save(fig, "grafik2_preisentwicklung")
print("ok", [(v[0], pct(v[1]), pct(v[2]), eur(v[3])) for v in vals])
