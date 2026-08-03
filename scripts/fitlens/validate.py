import re
exec(open("fitlens.py").read().split("# ---------- candidate formulas ----------")[0])

FLOOR = 5
def fit(platform, p):
    s = scores[platform]
    vals = []
    for a in range(1, 31):
        if a in p["na_n"]:
            continue
        req = p["core_n"].get(a, FLOOR)
        vals.append(min(s[a - 1] / req, 1.0))
    return 100 * sum(vals) / len(vals)

def met(platform, p):
    s = scores[platform]
    return sum(1 for a, r in p["core_n"].items() if s[a - 1] >= r)

def gate_fails(platform, p):
    s = scores[platform]
    return [axis_names[a] for a, r in p["gates_n"] if s[a - 1] < r]

print(f"{'Market':46s} {'met':>9s} {'fit(pub/calc)':>16s} {'rank(pub/calc)':>15s}")
met_ok = rank_err = 0
for t, p in profiles.items():
    ranked = sorted(scores, key=lambda pl: -fit(pl, p))
    r = ranked.index("Loupe") + 1
    m, f = met(t and "Loupe", p), fit("Loupe", p)
    pub = p["published"]
    ok = "OK" if m == pub["met"] else "**MISMATCH**"
    met_ok += (m == pub["met"])
    rank_err += abs(r - pub["rank"])
    print(f"{t:46s} {m:2d}/{len(p['core_n']):2d} {ok:6s} {pub['fit']:3d}/{f:5.1f} {pub['rank']:6d}/{r:3d}")
print(f"\ncore-met exact matches: {met_ok}/15   total rank error: {rank_err}")
