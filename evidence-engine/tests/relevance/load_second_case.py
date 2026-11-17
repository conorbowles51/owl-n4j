"""Load the second invented case's uploaded files through the app's own routes (lx-relevancetest A).

After the phones (journeys/live-phone-upload.mjs --case second) and the documents and statements folders
(journeys/live-demo-upload.mjs --case second) are uploaded, this makes the two calls a person makes on the pages:
- Evidence page, select the documents, Process: POST /api/evidence/process/background {case_id, file_ids};
- Financial page, Add statements from Evidence: POST /api/financial/statement-import/selection/resolve, then
  POST /api/financial/statement-import/batches (the call EvidenceFinancialPicker makes), for the statement PDFs.
Signed in once with the jobs login (it owns the case). Refuses any case but the second invented case. Prints counts.
    python3 evidence-engine/tests/relevance/load_second_case.py documents|statements|status
(documents: every unprocessed document and statement file, as the demo's were processed)
"""
from __future__ import annotations

import http.cookiejar
import json
import sys
import urllib.error
import urllib.request
import uuid

CASE = "3f3489a0-b8ee-4e1a-9ec4-83e8ca327d4c"
TITLE = "Demo 2: State v. Priya Halloran (synthetic)"


class Client:
    def __init__(self, login="/root/.config/loupe-jobs/login"):
        cfg = dict(line.split("=", 1) for line in open(login).read().splitlines() if "=" in line)
        self.url = cfg["url"]
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.token = self.call("POST", "/api/auth/login", {"username": cfg["email"], "password": cfg["password"]})[
            "access_token"]

    def call(self, method, path, body=None):
        headers = {"Content-Type": "application/json", "Origin": getattr(self, "url", "")}
        if getattr(self, "token", None):
            headers["Authorization"] = "Bearer " + self.token
        req = urllib.request.Request(self.url + path, method=method, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with self.op.open(req, timeout=300) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            raise SystemExit("%s %s: %s %s" % (method, path.split("?")[0], e.code, e.read()[:400].decode("utf8", "replace")))


def files(c):
    data = c.call("GET", "/api/evidence?case_id=%s" % CASE)
    return data.get("files") or data.get("items") or []


def main(step):
    c = Client()
    case = c.call("GET", "/api/cases/%s" % CASE)
    if case.get("title") != TITLE:
        raise SystemExit("refused: %s is not the second invented case" % CASE)
    fs = files(c)
    name = lambda f: f.get("original_filename") or f.get("filename") or ""
    path = lambda f: (f.get("folder_path") or "") + "/" + name(f)
    if step == "status":
        by = {}
        for f in fs:
            by.setdefault(f.get("status"), []).append(name(f))
        print(json.dumps({k: len(v) for k, v in by.items()}), len(fs), "files")
        return
    if step == "documents":
        # Every uploaded document and statement file is processed on the Evidence page, as the demo case's were
        # (its 43 statement files are processed evidence too); the statements are then read on the Financial page.
        ids = [f["id"] for f in fs if f.get("status") == "unprocessed" and name(f).endswith((".pdf", ".docx", ".csv"))]
        print("processing %d documents" % len(ids))
        if ids:
            print(json.dumps(c.call("POST", "/api/evidence/process/background", {"case_id": CASE, "file_ids": ids}))[:400])
        return
    if step == "statements":
        ids = [f["id"] for f in fs if name(f).startswith(("practice-", "pell-2024", "halloran-2024", "exhibit-b"))]
        print("statements %d" % len(ids))
        sel = c.call("POST", "/api/financial/statement-import/selection/resolve?case_id=%s" % CASE,
                     {"file_ids": ids, "folder_ids": [], "include_other_formats": True})
        pdfs = [f["id"] for f in sel.get("files") or []]
        print("selection resolved: %d files" % len(pdfs))
        batch = c.call("POST", "/api/financial/statement-import/batches?case_id=%s" % CASE,
                       {"request_id": str(uuid.uuid4()), "file_ids": pdfs, "folder_ids": [], "start_new": False})
        print("batch", batch.get("id"), batch.get("status"))
        return
    raise SystemExit("step: documents|statements|status")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "status")
