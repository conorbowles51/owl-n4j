"""05 section 11.6 perceptual-tier gate, pass 1: per phone, media messages with salted attachment MD5s.

usage: python3 -I p8_extract.py <corpus.json> <data_dir> <label>

Reuses the stage A3 report parsing (a3_extract.py: conv, walk, fv, parties, ts, id_key, direction, Salt).
Writes <data_dir>/<label>.p8.pkl (0600): salted identifier keys, salted MD5s, instants, direction, family,
file category. Prints counts only. No name, number, body, file name, path or identifier is written unsalted.
"""
import collections
import json
import os
import pickle
import resource
import sys
import time
import re
import unicodedata
import xml.etree.ElementTree as ET

sys.path.insert(0, "/mnt/owl-data/fin-wt/cb-media/docs/cellebrite/measurements/scripts")
import a3_extract as A  # noqa: E402


def family(r):
    t = (A.fv(r, "Type") or "").strip()
    if t in ("Sms", "Mms"):
        return "sms"
    if t == "IMessage":
        return "imessage"
    src = (A.fv(r, "Source") or A.fv(r, "SourceApplication") or "").strip().casefold()
    return "app:" + (src or "<none>")


def main(argv):
    corpus = json.load(open(argv[0], encoding="utf-8"))
    data_dir, label = argv[1], argv[2]
    spec = corpus[label]
    salt = A.Salt(os.path.join(data_dir, "salt.bin"))
    root = spec["root"]
    xml = os.path.join(root, spec["report"])
    t0 = time.monotonic()
    owner_keys = set()
    msgs = []          # (family, direction, t, from_key, to_keys, deleted, [attachments]) ; attachment = (fid, has_ref, url_only)
    files = {}         # fid -> (salted md5 or None, category)
    seen_ids = set()
    c = collections.Counter()
    body_occ = collections.Counter()
    ZW = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")

    def nbody(r):
        b = A.fv(r, "Body") or ""
        b = ZW.sub("", unicodedata.normalize("NFKC", b)).casefold()
        return " ".join(b.split())

    def on_model(rec):
        for r, p, f in A.walk(rec):
            if r["t"] == "Party":
                k = A.id_key((A.fv(r, "Identifier") or "").strip())
                if k and A.is_true(A.fv(r, "IsPhoneOwner")):
                    owner_keys.add(salt.h("id", k))
            if r["t"] != "InstantMessage":
                continue
            if r["id"] and r["id"] in seen_ids:
                c["instantmessage duplicate id skipped"] += 1
                continue
            if r["id"]:
                seen_ids.add(r["id"])
            c["instantmessage"] += 1
            nb = nbody(r)
            bh = salt.h("body", nb) if nb else None
            if bh:
                body_occ[bh] += 1
            atts = []
            for fld in ("Attachment", "Attachments"):
                for a in r["m"].get(fld, []):
                    if a["t"] != "Attachment":
                        continue
                    fids = [a["fid"]] if a["fid"] else []
                    fids += [tg for ism, tg in a["jt"] if ism == "false" and tg]
                    has_local = any(A.fv(a, n) for n in ("Filename", "ContentType", "attachment_extracted_path"))
                    url_only = (not fids) and (not has_local) and bool(A.fv(a, "URL"))
                    atts.append((tuple(dict.fromkeys(fids)), url_only))
            msg_jt = tuple(tg for ism, tg in r["jt"] if ism == "false" and tg)
            if not atts and not msg_jt:
                continue
            c["instantmessage with attachment model or file jump target"] += 1
            secs, _ = A.ts(A.fv(r, "TimeStamp"))
            d, _ = A.Report.direction(None, r)
            frm = A.parties(r, "From")
            fk = A.id_key((A.fv(frm[0], "Identifier") or "").strip()) if frm else None
            tks = set()
            for x in A.parties(r, "To"):
                k = A.id_key((A.fv(x, "Identifier") or "").strip())
                if k:
                    tks.add(salt.h("id", k))
            parts = set()
            if p is not None and p["t"] == "Chat":
                c["media candidate inside a Chat"] += 1
                for x in p["m"].get("Participants", []):
                    k = A.id_key((A.fv(x, "Identifier") or "").strip())
                    if k:
                        parts.add(salt.h("id", k))
            tks = (frozenset(tks), frozenset(parts))
            msgs.append((family(r), d, secs, salt.h("id", fk) if fk else None, tks, r["del"] or "",
                         tuple(atts), msg_jt, bh, len(nb)))

    stack, els = [], []
    with open(xml, "rb") as fh:
        for ev, el in ET.iterparse(fh, events=("start", "end")):
            tag = A.ln(el.tag)
            if ev == "start":
                stack.append(tag)
                els.append(el)
                continue
            stack.pop()
            els.pop()
            parent = stack[-1] if stack else None
            if tag == "model" and parent == "modelType":
                on_model(A.conv(el))
                el.clear()
                els[-1].remove(el)
            elif tag == "file" and parent == "taggedFiles":
                items = {}
                for md in el:
                    if A.ln(md.tag) == "metadata":
                        for it in md:
                            if A.ln(it.tag) == "item":
                                items[it.get("name")] = (it.text or "").strip()
                md5 = (items.get("MD5") or "").lower()
                files[el.get("id")] = (salt.h("md5", md5) if md5 else None, items.get("Tags") or "<none>")
                el.clear()
                els[-1].remove(el)
            elif tag in ("modelType", "taggedFiles", "decodedData", "extraInfos", "carvedFiles", "infectedFiles"):
                el.clear()
            elif parent in ("extraInfos", "carvedFiles", "infectedFiles"):
                el.clear()
                els[-1].remove(el)
    # resolve attachments to files now that all tagged files are known
    out = []
    for fam, d, secs, fk, tks, dele, atts, msg_jt, bh, blen in msgs:
        res = []  # per attachment: (state, md5 or None, category)
        refs = [fids for fids, url_only in atts if not url_only]
        if not atts and msg_jt:
            refs = [(x,) for x in msg_jt]
        for fids in refs:
            hit = [files[x] for x in fids if x in files]
            if not hit:
                res.append(("no_file", None, None))
            else:
                md = [h for h in hit if h[0]]
                res.append(("md5", md[0][0], md[0][1]) if md else ("no_md5", None, hit[0][1]))
        url_only_n = sum(1 for fids, u in atts if u)
        out.append({"fam": fam, "dir": d, "t": secs, "from": fk, "to": tks[0], "chat_parts": tks[1], "del": dele, "att": res,
                    "url_only": url_only_n, "body": bh, "blen": blen})
        c["media candidates (non-URL attachment)" if res else "URL-only attachment messages"] += 1
        if any(a[0] == "md5" for a in res):
            c["media messages (>=1 attachment with tagged file with MD5)"] += 1
    path = os.path.join(data_dir, label + ".p8.pkl")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        pickle.dump({"owner_keys": owner_keys, "msgs": out, "body_occ": body_occ}, fh, protocol=4)
    print(json.dumps({"label": label, "owner_keys": len(owner_keys), "tagged_files": len(files), **c,
                      "seconds": round(time.monotonic() - t0, 1),
                      "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
