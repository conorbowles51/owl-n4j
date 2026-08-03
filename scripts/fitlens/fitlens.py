"""Parse the market-fit lens and recover the fit formula, then score new profiles."""
import re, json, itertools, statistics

SRC = "/home/conorbowles51/app-v3/owl-n4j/18-market-fit-lens-narrative.md"
text = open(SRC).read()

# ---------- Appendix A: axis names in order ----------
axA = text.split("## A. The thirty axes")[1].split("## B.")[0]
axis_names = {}
for line in axA.splitlines():
    m = re.match(r"\|\s*(\d+)\s*\|\s*[A-E]\s*\|\s*\*\*(.+?)\*\*\s*\|", line)
    if m:
        axis_names[int(m.group(1))] = m.group(2).strip()
assert len(axis_names) == 30, len(axis_names)
name_to_num = {v.lower(): k for k, v in axis_names.items()}

# ---------- Appendix C: 47 x 30 matrix ----------
axC = text.split("## C. Full score matrix")[1].split("## D.")[0]
scores = {}
for line in axC.splitlines():
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) == 31 and all(re.fullmatch(r"\d+", c) for c in cells[1:]):
        scores[cells[0].replace("**", "").strip()] = [int(c) for c in cells[1:]]
scores.pop("Platform", None)
print(f"platforms parsed: {len(scores)}")

# ---------- Appendix D: profiles ----------
axD = text.split("## D. Market profiles")[1]
profiles = {}
blocks = re.split(r"\n### ", axD)
for b in blocks[1:]:
    title = b.splitlines()[0].strip()
    gates, na, core = [], [], {}
    mg = re.search(r"\*\*Gates:\*\*(.+)", b)
    if mg and "none" not in mg.group(1).lower():
        for g in mg.group(1).split(","):
            gm = re.search(r"(.+?)\s*≥\s*(\d+)", g)
            if gm:
                gates.append((gm.group(1).strip(), int(gm.group(2))))
    mn = re.search(r"\*\*Not applicable here:\*\*(.+)", b)
    if mn:
        na = [x.strip() for x in mn.group(1).split(",") if x.strip()]
    mc = re.search(r"\*\*Core requirements \((\d+)\):\*\*(.+)", b)
    if mc:
        for c in mc.group(2).split(","):
            cm = re.search(r"(.+?)\s*≥\s*(\d+)", c)
            if cm:
                core[cm.group(1).strip()] = int(cm.group(2))
        assert len(core) == int(mc.group(1)), (title, len(core), mc.group(1))
    ml = re.search(r"\*\*Loupe:\*\* fit \*\*(\d+)%\*\*, core met (\d+)/(\d+), rank \*\*(\d+) of 47\*\*", b)
    published = None
    if ml:
        published = dict(fit=int(ml.group(1)), met=int(ml.group(2)), rank=int(ml.group(4)))
    profiles[title] = dict(gates=gates, na=na, core=core, published=published)

def num(label):
    l = label.lower().strip()
    if l in name_to_num:
        return name_to_num[l]
    for k, v in name_to_num.items():
        if k.startswith(l) or l.startswith(k):
            return v
    raise KeyError(label)

for t, p in profiles.items():
    p["na_n"] = [num(x) for x in p["na"]]
    p["core_n"] = {num(k): v for k, v in p["core"].items()}
    p["gates_n"] = [(num(k), v) for k, v in p["gates"]]
    print(f"{t:45s} na={len(p['na_n']):2d} core={len(p['core_n']):2d} gates={len(p['gates_n'])} pub={p['published']}")

# ---------- candidate formulas ----------
def fit(platform, p, mode, floor):
    s = scores[platform]
    applicable = [a for a in range(1, 31) if a not in p["na_n"]]
    if mode == "mean_ratio":
        vals = []
        for a in applicable:
            req = p["core_n"].get(a, floor)
            vals.append(min(s[a - 1] / req, 1.0) if req else 1.0)
        return 100 * sum(vals) / len(vals)
    if mode == "capped_sum":
        n_ = d_ = 0
        for a in applicable:
            req = p["core_n"].get(a, floor)
            n_ += min(s[a - 1], req); d_ += req
        return 100 * n_ / d_
    if mode == "weighted":
        n_ = d_ = 0
        for a in applicable:
            w = p["core_n"].get(a, floor)
            n_ += w * s[a - 1]; d_ += w * 10
        return 100 * n_ / d_

print("\n--- formula search against 15 published Loupe fits ---")
best = None
for mode in ("mean_ratio", "capped_sum", "weighted"):
    for floor in range(1, 11):
        errs = []
        for t, p in profiles.items():
            if p["published"]:
                errs.append(abs(fit("Loupe", p, mode, floor) - p["published"]["fit"]))
        mae = sum(errs) / len(errs); mx = max(errs)
        if best is None or mae < best[0]:
            best = (mae, mode, floor, mx)
        print(f"{mode:12s} floor={floor:2d}  MAE={mae:5.2f}  max={mx:5.2f}")
print(f"\nBEST: {best}")
