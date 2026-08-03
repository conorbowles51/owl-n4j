import re
exec(open("fitlens.py").read().split("# ---------- candidate formulas ----------")[0])

FLOOR = 5
A = {v.lower(): k for k, v in axis_names.items()}
def n(s):
    for k, v in A.items():
        if k.startswith(s.lower()):
            return v
    raise KeyError(s)

# ---- Two new profiles, built from documented industry practice ----
NEW = {
"Corporate intelligence & business investigations": dict(
  # Kroll / Control Risks / S-RM / K2 / Nardello tier + boutiques. Work: due diligence,
  # asset tracing & recovery, fraud & corruption, litigation intelligence, sanctions &
  # supply-chain, reputational risk. Inputs: corporate registries, court records, media
  # archives, sanctions lists, property registers, human sources + client documents.
  na=["Certifications", "Evidence acquisition", "Analytics", "Acquisition &"],
  gates=[("Commercial accessibility", 5), ("Deployment control", 5)],
  core={"OSINT": 8, "Link /": 7, "Financial": 7, "Auto-built": 6, "Cross-source": 6,
        "Whole-corpus": 6, "Per-claim": 7, "Timeline": 5, "Processing": 6,
        "Case & investigation": 6, "Collaboration": 6, "Durable": 6, "Cited": 6,
        "Agentic": 5, "Proven": 5, "Ecosystem": 4, "Vendor": 6, "Commercial": 5,
        "Deployment": 5}),

"Litigation support & disputes — investigative tier": dict(
  # Forensic accounting & disputes boutiques, expert witnesses, investigative litigation
  # support serving law firms. Work: financial analysis for disputes, damages, asset
  # tracing in litigation, chronology & exhibit prep, expert reports that face
  # cross-examination. Inputs: disclosure sets, bank records, accounting exports, email,
  # chat, occasional device extractions.
  na=["Certifications", "Evidence acquisition", "Geospatial"],
  gates=[("Commercial accessibility", 5), ("Deployment control", 4)],
  core={"Financial": 8, "Per-claim": 8, "Timeline": 7, "Durable": 7, "Cited": 7,
        "Cross-source": 6, "Auto-built": 5, "Whole-corpus": 6, "Processing": 7,
        "Review workflow": 5, "Disclosure": 5, "Collaboration": 6, "Defensibility": 7,
        "Acquisition &": 5, "Ecosystem": 5, "Proven": 6, "Vendor": 6, "Commercial": 6,
        "Deployment": 5, "Agentic": 5}),
}
for t, p in NEW.items():
    p["na_n"] = [n(x) for x in p["na"]]
    p["core_n"] = {n(k): v for k, v in p["core"].items()}
    p["gates_n"] = [(n(k), v) for k, v in p["gates"]]

def fit(pl, p):
    s = scores[pl]
    vals = [min(s[a-1] / p["core_n"].get(a, FLOOR), 1.0)
            for a in range(1, 31) if a not in p["na_n"]]
    return 100 * sum(vals) / len(vals)
def met(pl, p):
    return sum(1 for a, r in p["core_n"].items() if scores[pl][a-1] >= r)
def fails(pl, p):
    return [axis_names[a] for a, r in p["gates_n"] if scores[pl][a-1] < r]

ALL = {**profiles, **NEW}
print("=" * 100)
print("RECOMPUTED ON ONE FORMULA — Loupe across all 17 markets")
print("=" * 100)
rows = []
for t, p in ALL.items():
    ranked = sorted(scores, key=lambda x: -fit(x, p))
    rows.append((t, fit("Loupe", p), ranked.index("Loupe") + 1, met("Loupe", p),
                 len(p["core_n"]), fails("Loupe", p),
                 sum(1 for x in scores if not fails(x, p))))
for t, f, r, m, c, gf, clear in sorted(rows, key=lambda x: -x[1]):
    tag = "NEW  " if t in NEW else "     "
    print(f"{tag}{t:52s} fit {f:5.1f}%  rank {r:2d}/47  core {m:2d}/{c:2d}  "
          f"gates {'FAIL: ' + ', '.join(gf) if gf else 'clear'}  ({clear} clear)")

for t, p in NEW.items():
    print("\n" + "=" * 100)
    print(f"{t}   —   leaderboard")
    print("=" * 100)
    ranked = sorted(scores, key=lambda x: -fit(x, p))
    for i, pl in enumerate(ranked[:14], 1):
        gf = fails(pl, p)
        mark = " <<<" if pl == "Loupe" else ""
        print(f"{i:2d}. {pl:34s} {fit(pl,p):5.1f}%  core {met(pl,p):2d}/{len(p['core_n'])}  "
              f"{'FAILS: ' + ', '.join(gf) if gf else 'clears'}{mark}")
    if "Loupe" not in ranked[:14]:
        i = ranked.index("Loupe") + 1
        print(f"{i:2d}. {'Loupe':34s} {fit('Loupe',p):5.1f}%  core {met('Loupe',p):2d}/{len(p['core_n'])} <<<")
    print("\n  Loupe fails these core requirements:")
    for a, r in sorted(p["core_n"].items()):
        if scores["Loupe"][a-1] < r:
            print(f"    axis {a:2d} {axis_names[a]:38s} needs {r}, Loupe {scores['Loupe'][a-1]}")

print("\n" + "=" * 100)
print("RANK AMONG BUYABLE PLATFORMS (gate-clearing only)")
print("=" * 100)
for t, p in NEW.items():
    clear = [x for x in scores if not fails(x, p)]
    rk = sorted(clear, key=lambda x: -fit(x, p))
    print(f"\n{t}  —  {len(clear)} of 47 buyable")
    for i, pl in enumerate(rk[:6], 1):
        print(f"  {i}. {pl:32s} {fit(pl,p):5.1f}%{'  <<<' if pl=='Loupe' else ''}")

print("\n" + "=" * 100)
print("SENSITIVITY — what closing each gap buys, in the two new markets + criminal defence")
print("=" * 100)
import copy
base = scores["Loupe"][:]
targets = {11: ("OSINT & external enrichment", 7), 12: ("Processing & format breadth", 8),
           13: ("Case & investigation workflow", 7), 17: ("Collaboration & permissions", 7),
           14: ("Review workflow at scale", 6), 15: ("Disclosure & production", 6),
           24: ("Ecosystem integrations", 6), 23: ("Proven scale", 6),
           28: ("Vendor viability", 6), 26: ("Parsing validation", 6)}
mkts = {**{k: NEW[k] for k in NEW}, "Criminal defence & PI": profiles["Criminal defence & PI"]}
print(f"{'Gap closed':44s}" + "".join(f"{k[:26]:>28s}" for k in mkts))
for a, (nm, to) in targets.items():
    scores["Loupe"] = base[:]; scores["Loupe"][a-1] = to
    cells = ""
    for k, p in mkts.items():
        rk = sorted(scores, key=lambda x: -fit(x, p)).index("Loupe") + 1
        cells += f"{fit('Loupe',p):20.1f}% (#{rk:2d})"
    print(f"axis {a:2d} {nm:30s} {base[a-1]}->{to} " + cells)
scores["Loupe"] = base[:]
cells = ""
for k, p in mkts.items():
    rk = sorted(scores, key=lambda x: -fit(x, p)).index("Loupe") + 1
    cells += f"{fit('Loupe',p):20.1f}% (#{rk:2d})"
print(f"{'BASELINE (today)':44s}" + cells)
# combined: OSINT + workflow + collaboration
scores["Loupe"] = base[:]
for a, v in ((11, 7), (13, 7), (17, 7)):
    scores["Loupe"][a-1] = v
cells = ""
for k, p in mkts.items():
    rk = sorted(scores, key=lambda x: -fit(x, p)).index("Loupe") + 1
    cells += f"{fit('Loupe',p):20.1f}% (#{rk:2d})"
print(f"{'COMBINED OSINT+workflow+collab':44s}" + cells)
