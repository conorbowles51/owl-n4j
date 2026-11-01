"""Stage A3: assemble the committed results from the per-report counts (a3_extract.py), the extraInfo pass
(a3_extrainfo.py) and the cross-phone pass (a3_cross.py).

usage: python3 -I a3_report.py <corpus.json> <a3_dir> <catalogue-14-phones.json> <out_dir> [<counter_dir>]

Writes to <out_dir> (docs/cellebrite/measurements/a3/):
  P01.json .. P14.json   per-report counts as written by a3_extract.py plus the extraInfo result (already
                         guarded; the seed detail is replaced by its comparison with the catalogue)
  cross.json             cross-phone measures
  summary.json           the aggregate tables each spec section records
Run a3_guard_check.py over <out_dir> before committing.
"""
import collections
import json
import os
import sys

BASIC = {"String", "TimeStamp", "Boolean", "Int64", "Int32", "Double", "TimeSpan", "Guid", "UInt32"}


def load(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def related_from_counter(counter_dir, label):
    """Per type, models under a RelatedModels element, and their (owner type, child type) relations, from the
    counter's per-path element counts (a3_extract.py walks only modelField and multiModelField nesting)."""
    import re
    p = os.path.join(counter_dir, label + "-lxml.json")
    types, rel = collections.Counter(), set()
    if not os.path.exists(p):
        return types, rel
    for k, v in load(p)["paths"].items():
        parts = k.split("/")
        m = re.match(r"model\[(.*)\]$", parts[-1])
        if m and "RelatedModels" in parts:
            types[m.group(1)] += v["elements"]
            if parts[-2] == "RelatedModels":
                o = re.match(r"model\[(.*)\]$", parts[-3])
                if o:
                    rel.add((o.group(1), "RelatedModels", "RelatedModels", m.group(1)))
    return types, rel


def seed_compare(counts, cat, counter_dir=None):
    """02-U2: the seed recomputed from the server reports against the catalogue, per report and in total."""
    per = {}
    tot_types = collections.Counter()
    tot_fields = set()
    tot_sets = collections.defaultdict(set)
    tot_nest = set()
    cat_types = collections.Counter()
    cat_fields = set()
    cat_sets = collections.defaultdict(set)
    for label, c in sorted(counts.items()):
        s = c["seed"]
        ph = cat.get(label)
        types = collections.Counter(s["types"])
        rel_types, rel_nest = related_from_counter(counter_dir, label) if counter_dir else (collections.Counter(), set())
        types.update(rel_types)
        fields = {(t, f, k, vt) for t, f, k, vt, n in s["fields"] if vt is not None}
        sets = {k: set(v) for k, v in s["named_sets"].items()}
        for k, v in types.items():
            tot_types[k] += v
        tot_fields |= fields
        for k, v in sets.items():
            tot_sets[k] |= v
        tot_nest |= {(a, b, cc, d) for a, b, cc, d, n in s["nesting"]} | rel_nest
        entry = {"types": len(types), "records": sum(types.values()), "field_rows": len(fields),
                 "named_sets": len([k for k in sets if k != "DecodingSourceOptions"]),
                 "named_set_values": sum(len(v) for k, v in sets.items() if k != "DecodingSourceOptions"),
                 "nesting_relations": len(s["nesting"]) + len(rel_nest),
                 "related_models": sum(rel_types.values())}
        if ph:
            ct = ph["model_types"]
            cf = {(t, f, k, vt) for t, f, k, d in ph["catalog"] for vt in d}
            cs = {k: set(v) for k, v in ph["enums"].items() if k not in BASIC}
            for k, v in ct.items():
                cat_types[k] += v
            cat_fields |= cf
            for k, v in cs.items():
                cat_sets[k] |= v
            entry["catalogue"] = {"types": len(ct), "records": sum(ct.values()), "field_rows": len(cf),
                                  "named_sets": len(cs), "named_set_values": sum(len(v) for v in cs.values())}
            entry["types_with_different_count"] = sum(1 for k in set(ct) | set(types) if ct.get(k, 0) != types.get(k, 0))
            entry["record_difference"] = sum(types.values()) - sum(ct.values())
            entry["types_only_in_report"] = len(set(types) - set(ct))
            entry["types_only_in_catalogue"] = len(set(ct) - set(types))
            entry["field_rows_only_in_report"] = len(fields - cf)
            entry["field_rows_only_in_catalogue"] = len(cf - fields)
            entry["named_set_values_only_in_report"] = sum(len(sets.get(k, set()) - cs.get(k, set())) for k in sets if k != "DecodingSourceOptions")
            entry["named_set_values_only_in_catalogue"] = sum(len(cs[k] - sets.get(k, set())) for k in cs)
            diffs = sorted(((k, types.get(k, 0) - ct.get(k, 0)) for k in set(ct) | set(types) if ct.get(k, 0) != types.get(k, 0)),
                           key=lambda x: -abs(x[1]))
            entry["largest_type_differences"] = diffs[:8]
        per[label] = entry
    named = {k: v for k, v in tot_sets.items() if k != "DecodingSourceOptions"}
    cnamed = dict(cat_sets)
    total = {
        "report": {"types": len(tot_types), "records": sum(tot_types.values()), "field_rows": len(tot_fields),
                   "field_rows_over_type_field_kind": len({x[:3] for x in tot_fields}),
                   "named_sets": len(named), "named_set_values": sum(len(v) for v in named.values()),
                   "decoding_source_options": sorted(tot_sets.get("DecodingSourceOptions", ())),
                   "nesting_relations": len(tot_nest)},
        "catalogue_same_14": {"types": len(cat_types), "records": sum(cat_types.values()), "field_rows": len(cat_fields),
                              "named_sets": len(cnamed), "named_set_values": sum(len(v) for v in cnamed.values())},
        "types_only_in_reports": sorted(set(tot_types) - set(cat_types)),
        "types_only_in_catalogue": sorted(set(cat_types) - set(tot_types)),
        "field_rows_only_in_reports": len(tot_fields - cat_fields),
        "field_rows_only_in_catalogue": len(cat_fields - tot_fields),
        "named_sets_only_in_reports": sorted(set(named) - set(cnamed)),
        "named_set_values_only_in_reports": sum(len(v - cnamed.get(k, set())) for k, v in named.items()),
        "named_set_values_only_in_catalogue": sum(len(v - named.get(k, set())) for k, v in cnamed.items()),
        "nesting_relations_list": sorted([list(x) for x in tot_nest]),
        "value_type_drift_fields": sorted("%s.%s" % k[:2] for k, n in collections.Counter(x[:3] for x in tot_fields).items() if n > 1),
    }
    return per, total


NUM_RE = None


def bucket_numbers(measures):
    """Location Precision values read '<word>: <number>'; the number is replaced by its log bucket so no exact
    reading is committed (04 section 13: values become shapes or histograms)."""
    import math
    import re
    num = re.compile(r"-?\d+(?:\.\d+)?")

    def b(m):
        x = abs(float(m.group(0)))
        if x < 1:
            return "<1"
        e = int(math.floor(math.log10(x)))
        return "%d-%d" % (10 ** e, 10 ** (e + 1) - 1)
    for name in ("m5_location_precision", "m2_location_type_category_precision_source"):
        if name in measures:
            out = collections.Counter()
            for k, v in measures[name].items():
                out[num.sub(b, k).strip()] += v
            measures[name] = dict(sorted(out.items()))


def short_comparison(rel):
    import re
    if rel and "field_comparison" in rel:
        rel["field_comparison"] = {re.sub(r"fields equal (\S+) / differing (\S+) / one side only (\S+)",
                                          r"equal \1 | differing \2 | one side \3", k): v
                                   for k, v in rel["field_comparison"].items()}
    return rel


def main(argv):
    corpus = load(argv[0])
    a3 = argv[1]
    cat = {p["p_label"]: p for p in load(argv[2])["phones"]}
    out = argv[3]
    os.makedirs(out, exist_ok=True)
    counts = {}
    for label in sorted(corpus):
        p = os.path.join(a3, label + ".counts.json")
        if os.path.exists(p):
            counts[label] = load(p)
    per_seed, tot_seed = seed_compare(counts, cat, argv[4] if len(argv) > 4 else None)
    summary = {"what": "Stage A3 server measurement batch (06 section 5): aggregates over the 14 server reports. "
                       "Counts, schema names and guarded values only.",
               "reports": sorted(counts), "seed_02_U2": {"total": tot_seed, "per_report": per_seed}}
    zone, dup, media, cp, m12, m11 = {}, {}, collections.Counter(), collections.Counter(), {}, {}
    styled = collections.Counter()
    for label, c in counts.items():
        zone[label] = c["d3_zone"]
        dup[label] = c["d4_duplicates"]
        for k, v in c["counts"].get("d7_media", {}).items():
            media[k] += v
        for k, v in c["d6_codepoints"]["totals"].items():
            cp[k] += v
        for k, v in c["d6_codepoints"]["styled"].items():
            styled[k] += v
        m12[label] = c["m12"]
        m11[label] = c["m11"]
        ei = os.path.join(a3, label + ".extrainfo.json")
        if os.path.exists(ei):
            c["extrainfo"] = load(ei)
        rl = os.path.join(a3, label + ".related.json")
        if os.path.exists(rl):
            c["related_models"] = load(rl)
        c = dict(c)
        bucket_numbers(c["guarded"])
        if "related_models" in c:
            c["related_models"] = short_comparison(c["related_models"])
        c["seed"] = per_seed[label]
        with open(os.path.join(out, label + ".json"), "w", encoding="utf-8") as fh:
            json.dump(c, fh, indent=1, sort_keys=True)
            fh.write("\n")
    summary["d3_zone"] = zone
    summary["d4_duplicates"] = dup
    summary["d6_codepoints"] = {"totals": dict(cp), "styled": dict(sorted(styled.items()))}
    summary["d7_media"] = dict(sorted(media.items()))
    summary["m11"] = m11
    summary["m12"] = m12
    cross = os.path.join(a3, "cross.json")
    if os.path.exists(cross):
        with open(os.path.join(out, "cross.json"), "w", encoding="utf-8") as fh:
            json.dump(load(cross), fh, indent=1, sort_keys=True)
            fh.write("\n")
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(json.dumps({"reports": len(counts), "seed_total": tot_seed["report"]}))


if __name__ == "__main__":
    main(sys.argv[1:])
