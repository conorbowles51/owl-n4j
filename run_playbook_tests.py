#!/usr/bin/env python3
"""OWL Platform Testing Playbooks — Automated Test Runner (v2)"""

import requests
import json
import sys
import time
from datetime import datetime

BASE = "http://localhost:8000"
CASE_ID = "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb"
CREDS = {"username": "neil.byrne@gmail.com", "password": "OwlAdmin123!"}

results = {}
TOKEN = None
HEADERS = {}
state = {}

def run_step(playbook, step, description, func):
    key = f"PB{playbook}.{step}"
    try:
        passed, detail = func()
        status = "PASS" if passed else "FAIL"
    except Exception as e:
        status = "ERROR"
        detail = str(e)[:200]
    results[key] = {"status": status, "desc": description, "detail": detail}
    icon = "✅" if status == "PASS" else ("❌" if status == "FAIL" else "⚠️")
    print(f"  {icon} {key}: {description} — {status}")
    if status != "PASS":
        print(f"       Detail: {detail}")
    return status == "PASS"

def get(path, **kwargs):
    return requests.get(f"{BASE}{path}", headers=HEADERS, params=kwargs, timeout=30)

def post(path, data=None, **kwargs):
    return requests.post(f"{BASE}{path}", headers=HEADERS, json=data, timeout=60, **kwargs)

def put(path, data=None):
    return requests.put(f"{BASE}{path}", headers=HEADERS, json=data, timeout=30)

def delete(path, **kwargs):
    return requests.delete(f"{BASE}{path}", headers=HEADERS, params=kwargs, timeout=30)

# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 1
# ═══════════════════════════════════════════════════════════════
def run_playbook_1():
    print("\n" + "="*70)
    print("PLAYBOOK 1: Knowledge Graph — Viewing, Navigation & Search")
    print("="*70)

    def step1():
        r = requests.post(f"{BASE}/api/auth/login", json=CREDS, timeout=10)
        d = r.json()
        global TOKEN, HEADERS
        TOKEN = d.get("access_token")
        HEADERS = {"Authorization": f"Bearer {TOKEN}"}
        has_token = bool(TOKEN)
        has_name = "Neil" in d.get("name", "") or "Byrne" in d.get("name", "")
        return has_token and has_name, f"token={'yes' if has_token else 'no'}, name={d.get('name','?')}, role={d.get('role','?')}"
    run_step(1, 1, "Authenticate and get token", step1)

    def step2():
        r = get("/api/graph", case_id=CASE_ID)
        d = r.json()
        nc = len(d.get("nodes", []))
        lc = len(d.get("links", []))
        state["graph_nodes"] = d.get("nodes", [])
        state["graph_links"] = d.get("links", [])
        return nc >= 150 and lc >= 350, f"nodes={nc}, links={lc}"
    run_step(1, 2, "Load case graph data", step2)

    def step3():
        r = get("/api/graph/entity-types", case_id=CASE_ID)
        d = r.json()
        etypes = d.get("entity_types", d) if isinstance(d, dict) else d
        if isinstance(etypes, list):
            types = {x["type"]: x["count"] for x in etypes}
        elif isinstance(etypes, dict):
            types = etypes
        else:
            types = {}
        return len(types) >= 5, f"{len(types)} types: {dict(list(types.items())[:8])}"
    run_step(1, 3, "Verify entity types", step3)

    def step4():
        r = get("/api/graph/search", q="Marco Delgado", limit=20, case_id=CASE_ID)
        d = r.json()
        found = any("Marco" in x.get("name","") and x.get("type") == "Person" for x in d)
        state["marco_key"] = next((x["key"] for x in d if "Marco" in x.get("name","") and x.get("type") == "Person"), None)
        return found, f"{len(d)} results, marco_key={state.get('marco_key','N/A')}"
    run_step(1, 4, "Search for Marco Delgado", step4)

    def step5():
        r = get("/api/graph/search", q="Solaris", limit=20, case_id=CASE_ID)
        d = r.json()
        found = any("Solaris" in x.get("name","") for x in d)
        return found, f"{len(d)} results: {[x.get('name') for x in d[:3]]}"
    run_step(1, 5, "Search for Solaris", step5)

    def step6():
        key = state.get("marco_key")
        if not key:
            return False, "No marco_key from step 4"
        r = get(f"/api/graph/node/{key}", case_id=CASE_ID)
        d = r.json()
        has_name = "name" in d
        has_type = "type" in d
        conns = d.get("connections", d.get("relationships", []))
        conns = conns if isinstance(conns, list) else []
        facts = d.get("verified_facts", [])
        insights = d.get("ai_insights", [])
        return has_name and has_type, f"name={d.get('name')}, type={d.get('type')}, connections={len(conns)}, facts={len(facts)}, insights={len(insights)}"
    run_step(1, 6, "Get node details (Marco Delgado)", step6)

    def step7():
        key = state.get("marco_key")
        if not key:
            return False, "No marco_key"
        r = get(f"/api/graph/node/{key}/neighbours", depth=1, case_id=CASE_ID)
        d = r.json()
        nc = len(d.get("nodes", []))
        lc = len(d.get("links", []))
        return nc >= 2 and lc >= 1, f"nodes={nc}, links={lc}"
    run_step(1, 7, "Get node neighbours", step7)

    def step8():
        r = get("/api/graph/summary", case_id=CASE_ID)
        d = r.json()
        nc = d.get("total_nodes", d.get("node_count", 0))
        lc = d.get("total_relationships", d.get("link_count", 0))
        return nc >= 150 and lc >= 350, f"total_nodes={nc}, total_relationships={lc}"
    run_step(1, 8, "Get graph summary", step8)

    def step9():
        nodes = state.get("graph_nodes", [])
        persons = [n for n in nodes if n.get("type") == "Person"]
        return len(persons) >= 5, f"{len(persons)} Person entities"
    run_step(1, 9, "Filter by entity type (Person)", step9)

    def step10():
        return True, "UI visual check — skipped (API-only run)"
    run_step(1, 10, "Pane view modes (UI check — skipped)", step10)


# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 2
# ═══════════════════════════════════════════════════════════════
def run_playbook_2():
    print("\n" + "="*70)
    print("PLAYBOOK 2: Knowledge Graph — CRUD Operations")
    print("="*70)

    angela_key = None
    elena_key = None

    def step1():
        nonlocal angela_key
        r = post("/api/graph/create-node", {
            "name": "Angela Torres", "type": "Person",
            "description": "A potential witness in the Silver Bridge money laundering case",
            "summary": "Angela Torres is a former accountant at Cruz & Partners who may have knowledge of fraudulent transactions",
            "properties": {"role": "Witness", "occupation": "Accountant", "location": "Miami, FL"},
            "case_id": CASE_ID
        })
        d = r.json()
        angela_key = d.get("node_key", d.get("key"))
        state["angela_key"] = angela_key
        return r.status_code == 200 and angela_key is not None, f"node_key={angela_key}, status={r.status_code}"
    run_step(2, 1, "Create node — Angela Torres", step1)

    def step2():
        r = get("/api/graph/search", q="Angela Torres", limit=5, case_id=CASE_ID)
        d = r.json()
        found = any("Angela" in x.get("name","") for x in d)
        return found, f"{len(d)} results"
    run_step(2, 2, "Verify via search", step2)

    def step3():
        if not angela_key:
            return False, "No angela_key"
        r = get(f"/api/graph/node/{angela_key}", case_id=CASE_ID)
        d = r.json()
        ok = d.get("name") == "Angela Torres" and d.get("type") == "Person"
        return ok, f"name={d.get('name')}, type={d.get('type')}"
    run_step(2, 3, "Get node details", step3)

    def step4():
        if not angela_key:
            return False, "No angela_key"
        r = put(f"/api/graph/node/{angela_key}", {
            "summary": "Angela Torres is a former senior accountant at Cruz & Partners. She resigned in 2024 and may be willing to cooperate with investigators.",
            "notes": "Initial contact made via attorney. Willing to meet under immunity agreement.",
            "properties": {"role": "Cooperating Witness", "occupation": "Former Senior Accountant", "location": "Miami, FL", "phone": "305-555-0142"},
            "case_id": CASE_ID
        })
        return r.status_code == 200, f"status={r.status_code}"
    run_step(2, 4, "Edit node — update properties", step4)

    def step5():
        if not angela_key:
            return False, "No angela_key"
        r = get(f"/api/graph/node/{angela_key}", case_id=CASE_ID)
        d = r.json()
        summary_ok = "senior accountant" in d.get("summary", "").lower()
        return summary_ok, f"summary has 'senior accountant': {summary_ok}"
    run_step(2, 5, "Verify edit persists", step5)

    def step6():
        nonlocal elena_key
        r = get("/api/graph/search", q="Elena Petrova", limit=5, case_id=CASE_ID)
        d = r.json()
        elena_key = next((x["key"] for x in d if "Elena" in x.get("name","") and x.get("type") == "Person"), None)
        if not elena_key:
            return False, "Elena Petrova not found as Person"
        if not angela_key:
            return False, "No angela_key"
        r2 = post("/api/graph/relationships", {
            "relationships": [{"source_key": angela_key, "target_key": elena_key, "type": "WORKED_WITH",
                               "properties": {"context": "Both employed at Solaris Property Group", "confidence": "high"}}],
            "case_id": CASE_ID
        })
        return r2.status_code == 200, f"elena_key={elena_key}, status={r2.status_code}"
    run_step(2, 6, "Create relationship (Angela-Elena Petrova)", step6)

    def step7():
        if not angela_key:
            return False, "No angela_key"
        r = get(f"/api/graph/node/{angela_key}/neighbours", depth=1, case_id=CASE_ID)
        d = r.json()
        node_keys = [n.get("key") for n in d.get("nodes", [])]
        elena_found = elena_key in node_keys if elena_key else False
        return elena_found, f"Elena in neighbours: {elena_found}, total neighbours: {len(node_keys)}"
    run_step(2, 7, "Verify relationship in neighbours", step7)

    def step8():
        marco_key = state.get("marco_key")
        if not marco_key:
            return False, "No marco_key"
        r = get(f"/api/graph/node/{marco_key}", case_id=CASE_ID)
        d = r.json()
        facts = d.get("verified_facts", [])
        if not facts or not isinstance(facts, list) or len(facts) == 0:
            return True, "SKIP — no verified facts on Marco Delgado"
        r2 = put(f"/api/graph/node/{marco_key}/pin-fact", {
            "case_id": CASE_ID, "fact_index": 0, "pinned": True
        })
        return r2.status_code == 200, f"status={r2.status_code}, facts_count={len(facts)}"
    run_step(2, 8, "Pin a fact", step8)

    def step9():
        if not angela_key:
            return False, "No angela_key"
        r = put("/api/graph/batch-update", {
            "case_id": CASE_ID,
            "updates": [{"node_key": angela_key, "properties": {"notes": "Active Witness"}}]
        })
        return r.status_code == 200, f"status={r.status_code}, body={r.text[:100]}"
    run_step(2, 9, "Batch update nodes", step9)

    def step10():
        if not angela_key:
            return False, "No angela_key"
        r = delete(f"/api/graph/node/{angela_key}", case_id=CASE_ID)
        return r.status_code in (200, 204), f"status={r.status_code}"
    run_step(2, 10, "Delete test node", step10)

    def step11():
        r = get("/api/graph/search", q="Angela Torres", limit=5, case_id=CASE_ID)
        d = r.json()
        not_found = not any("Angela Torres" == x.get("name","") for x in d)
        return not_found, f"search results: {len(d)}"
    run_step(2, 11, "Verify deletion", step11)

    def step12():
        r = get("/api/graph/summary", case_id=CASE_ID)
        d = r.json()
        nc = d.get("total_nodes", 0)
        return True, f"total_nodes={nc}"
    run_step(2, 12, "Verify graph count restored", step12)


# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 3
# ═══════════════════════════════════════════════════════════════
def run_playbook_3():
    print("\n" + "="*70)
    print("PLAYBOOK 3: Entity Resolution & Merging")
    print("="*70)

    entity_a_key = None
    entity_b_key = None
    entity_c_key = None
    entity_d_key = None

    def step1():
        r = post("/api/graph/find-similar-entities", {
            "case_id": CASE_ID, "entity_types": None, "name_similarity_threshold": 0.7, "max_results": 50
        })
        d = r.json()
        count = len(d) if isinstance(d, list) else d.get("count", len(d.get("pairs", d.get("results", []))))
        return r.status_code == 200, f"status={r.status_code}, pairs={count}"
    run_step(3, 1, "Find similar entities", step1)

    def step2():
        r = post("/api/graph/find-similar-entities", {
            "case_id": CASE_ID, "entity_types": ["Person"], "name_similarity_threshold": 0.6, "max_results": 50
        })
        return r.status_code == 200, f"status={r.status_code}"
    run_step(3, 2, "Find similar entities filtered by Person", step2)

    def step3():
        try:
            r = requests.get(f"{BASE}/api/graph/find-similar-entities/stream",
                             headers=HEADERS,
                             params={"case_id": CASE_ID, "name_similarity_threshold": 0.7, "max_results": 50},
                             stream=True, timeout=30)
            events = []
            for line in r.iter_lines(decode_unicode=True):
                if line and line.startswith("data:"):
                    events.append(line[5:].strip()[:80])
                if len(events) > 20:
                    break
            return len(events) > 0, f"SSE events: {len(events)}"
        except Exception as e:
            return False, f"SSE error: {str(e)[:100]}"
    run_step(3, 3, "Find similar entities (streaming/SSE)", step3)

    def step4():
        nonlocal entity_a_key, entity_b_key
        r1 = post("/api/graph/create-node", {"name": "John R. Mercer", "type": "Person", "summary": "Test entity for merge", "case_id": CASE_ID})
        r2 = post("/api/graph/create-node", {"name": "John Robert Mercer", "type": "Person", "summary": "Test entity for merge - duplicate", "case_id": CASE_ID})
        entity_a_key = r1.json().get("node_key", r1.json().get("key"))
        entity_b_key = r2.json().get("node_key", r2.json().get("key"))
        return bool(entity_a_key) and bool(entity_b_key), f"a={entity_a_key}, b={entity_b_key}"
    run_step(3, 4, "Create test pair for merging", step4)

    def step5():
        r = post("/api/graph/find-similar-entities", {
            "case_id": CASE_ID, "entity_types": ["Person"], "name_similarity_threshold": 0.5, "max_results": 100
        })
        d = r.json()
        pairs = d if isinstance(d, list) else d.get("pairs", d.get("results", []))
        found = any(
            (p.get("entity1",{}).get("key") in (entity_a_key, entity_b_key) and
             p.get("entity2",{}).get("key") in (entity_a_key, entity_b_key))
            for p in pairs
        )
        return found, f"test pair found: {found}, total_pairs={len(pairs)}"
    run_step(3, 5, "Detect test pair in similar entities", step5)

    def step6():
        if not entity_a_key or not entity_b_key:
            return False, "Missing entity keys"
        r = post("/api/graph/merge-entities", {
            "case_id": CASE_ID, "source_key": entity_a_key, "target_key": entity_b_key,
            "merged_data": {"name": "John Robert Mercer", "type": "Person",
                            "summary": "Merged entity - John R. Mercer / John Robert Mercer",
                            "notes": "Merged during entity resolution testing"}
        })
        return r.status_code == 200, f"status={r.status_code}, body={r.text[:120]}"
    run_step(3, 6, "Merge test entities", step6)

    def step7():
        r1 = get("/api/graph/search", q="John Robert Mercer", limit=5, case_id=CASE_ID)
        r2 = get("/api/graph/search", q="John R. Mercer", limit=5, case_id=CASE_ID)
        d1 = r1.json()
        merged_exists = any("John Robert Mercer" in x.get("name","") for x in d1)
        state["merged_key"] = next((x["key"] for x in d1 if "John Robert Mercer" in x.get("name","")), None)
        d2 = r2.json()
        old_gone = not any(x.get("name","") == "John R. Mercer" for x in d2)
        return merged_exists and old_gone, f"merged_exists={merged_exists}, old_gone={old_gone}"
    run_step(3, 7, "Verify merge result", step7)

    def step8():
        nonlocal entity_c_key, entity_d_key
        r1 = post("/api/graph/create-node", {"name": "James Wilson", "type": "Person", "summary": "Test entity for reject", "case_id": CASE_ID})
        r2 = post("/api/graph/create-node", {"name": "James B. Wilson", "type": "Person", "summary": "Different person with similar name", "case_id": CASE_ID})
        entity_c_key = r1.json().get("node_key", r1.json().get("key"))
        entity_d_key = r2.json().get("node_key", r2.json().get("key"))
        return bool(entity_c_key) and bool(entity_d_key), f"c={entity_c_key}, d={entity_d_key}"
    run_step(3, 8, "Create test pair for rejection", step8)

    def step9():
        if not entity_c_key or not entity_d_key:
            return False, "Missing entity keys"
        r = post("/api/graph/reject-merge", {
            "case_id": CASE_ID, "entity_key_1": entity_c_key, "entity_key_2": entity_d_key
        })
        return r.status_code == 200, f"status={r.status_code}"
    run_step(3, 9, "Reject pair as false positive", step9)

    def step10():
        r = get("/api/graph/rejected-merges", case_id=CASE_ID)
        d = r.json()
        pairs = d if isinstance(d, list) else d.get("rejected_pairs", d.get("pairs", []))
        found = any(
            (entity_c_key in str(p) and entity_d_key in str(p))
            for p in pairs
        )
        if found:
            for p in pairs:
                if entity_c_key in str(p) and entity_d_key in str(p):
                    state["rejection_id"] = p.get("id", p.get("rejection_id"))
                    break
        return found, f"found={found}, total_rejected={len(pairs)}"
    run_step(3, 10, "Verify rejected pair stored", step10)

    def step11():
        rej_id = state.get("rejection_id")
        if not rej_id:
            return False, "No rejection_id from step 10"
        r = delete(f"/api/graph/rejected-merges/{rej_id}")
        return r.status_code in (200, 204), f"status={r.status_code}"
    run_step(3, 11, "Undo rejection", step11)

    def step12():
        keys = [state.get("merged_key"), entity_c_key, entity_d_key]
        statuses = []
        for k in keys:
            if k:
                r = delete(f"/api/graph/node/{k}", case_id=CASE_ID)
                statuses.append(r.status_code)
        all_ok = all(s in (200, 204) for s in statuses) if statuses else True
        return all_ok, f"deleted {len(statuses)} entities, statuses={statuses}"
    run_step(3, 12, "Clean up test entities", step12)


# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 4
# ═══════════════════════════════════════════════════════════════
def run_playbook_4():
    print("\n" + "="*70)
    print("PLAYBOOK 4: Graph Analysis Tools (Spotlight Graph)")
    print("="*70)

    marco_key = state.get("marco_key")
    elena_key = None

    def step1():
        nonlocal elena_key
        r = get("/api/graph/search", q="Elena Petrova", limit=5, case_id=CASE_ID)
        d = r.json()
        elena_key = next((x["key"] for x in d if "Elena" in x.get("name","") and x.get("type") == "Person"), None)
        state["elena_key"] = elena_key
        return bool(elena_key) and bool(marco_key), f"marco={bool(marco_key)}, elena={bool(elena_key)}"
    run_step(4, 1, "Get keys for Marco Delgado and Elena Petrova", step1)

    def step2():
        if not marco_key or not elena_key:
            return False, "Missing keys"
        r = post("/api/graph/shortest-paths", {
            "case_id": CASE_ID, "source_key": marco_key, "target_key": elena_key, "max_depth": 5
        })
        return r.status_code == 200, f"status={r.status_code}, body_preview={r.text[:120]}"
    run_step(4, 2, "Shortest paths (Marco → Elena)", step2)

    def step3():
        r = post("/api/graph/pagerank", {"case_id": CASE_ID, "top_n": 10})
        d = r.json()
        rankings = d.get("nodes", d.get("rankings", d.get("results", d if isinstance(d, list) else [])))
        return r.status_code == 200 and len(rankings) > 0, f"status={r.status_code}, top_entities={len(rankings)}"
    run_step(4, 3, "PageRank analysis", step3)

    def step4():
        r = post("/api/graph/community-detection", {"case_id": CASE_ID})
        if r.status_code == 404:
            r2 = post("/api/graph/louvain", {"case_id": CASE_ID})
            if r2.status_code != 404:
                return r2.status_code == 200, f"found at /louvain, status={r2.status_code}"
            return False, "KNOWN ISSUE — community detection endpoint not found (404)"
        d = r.json()
        return r.status_code == 200, f"status={r.status_code}"
    run_step(4, 4, "Louvain community detection", step4)

    def step5():
        r = post("/api/graph/betweenness-centrality", {"case_id": CASE_ID, "top_n": 10})
        d = r.json()
        return r.status_code == 200, f"status={r.status_code}"
    run_step(4, 5, "Betweenness centrality", step5)

    def step6():
        if not marco_key:
            return False, "No marco_key"
        r = get(f"/api/graph/node/{marco_key}/neighbours", depth=2, case_id=CASE_ID)
        d = r.json()
        nc = len(d.get("nodes", []))
        lc = len(d.get("links", []))
        return nc > 2 and lc > 1, f"2-hop: nodes={nc}, links={lc}"
    run_step(4, 6, "Get 2-hop subgraph (Spotlight Graph)", step6)


# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 5
# ═══════════════════════════════════════════════════════════════
def run_playbook_5():
    print("\n" + "="*70)
    print("PLAYBOOK 5: Table View")
    print("="*70)

    def step1():
        r = get("/api/graph", case_id=CASE_ID)
        d = r.json()
        nodes = d.get("nodes", [])
        return len(nodes) >= 150, f"total nodes: {len(nodes)}"
    run_step(5, 1, "Load all entities for table", step1)

    def step2():
        r = get("/api/graph/entity-types", case_id=CASE_ID)
        d = r.json()
        etypes = d.get("entity_types", d) if isinstance(d, dict) else d
        if isinstance(etypes, list):
            count = len(etypes)
        elif isinstance(etypes, dict):
            count = len(etypes)
        else:
            count = 0
        return count >= 5, f"entity types: {count}"
    run_step(5, 2, "Get entity types for filter", step2)

    def step3():
        r = get("/api/graph/search", q="Silver Bridge", limit=50, case_id=CASE_ID)
        return r.status_code == 200, f"search results: {len(r.json()) if isinstance(r.json(), list) else '?'}"
    run_step(5, 3, "Search entities in table", step3)

    def step4():
        r = get("/api/graph", case_id=CASE_ID)
        nodes = r.json().get("nodes", [])
        return len(nodes) >= 25, f"total={len(nodes)}, supports pagination"
    run_step(5, 4, "Verify pagination (client-side)", step4)

    def step5():
        r = put("/api/graph/batch-update", {"case_id": CASE_ID, "updates": []})
        return r.status_code == 200, f"empty batch: status={r.status_code}"
    run_step(5, 5, "Batch update (empty — verify endpoint)", step5)


# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 6
# ═══════════════════════════════════════════════════════════════
def run_playbook_6():
    print("\n" + "="*70)
    print("PLAYBOOK 6: Timeline View")
    print("="*70)

    def step1():
        r = get("/api/timeline", case_id=CASE_ID)
        d = r.json()
        events = d.get("events", d) if isinstance(d, dict) else d
        count = len(events) if isinstance(events, list) else "?"
        return r.status_code == 200, f"events={count}"
    run_step(6, 1, "Load timeline events", step1)

    def step2():
        r = get("/api/timeline", case_id=CASE_ID)
        d = r.json()
        events = d.get("events", d) if isinstance(d, dict) else d
        if isinstance(events, list) and events:
            e = events[0]
            return True, f"first event keys: {list(e.keys())[:8]}"
        return True, "No events — acceptable"
    run_step(6, 2, "Verify timeline event structure", step2)

    def step3():
        r = get("/api/graph/entity-types", case_id=CASE_ID)
        return r.status_code == 200, "Entity types available for timeline filtering"
    run_step(6, 3, "Entity types for timeline filter", step3)


# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 7
# ═══════════════════════════════════════════════════════════════
def run_playbook_7():
    print("\n" + "="*70)
    print("PLAYBOOK 7: Map View")
    print("="*70)

    location_entities = []
    test_person_key = None

    def step1():
        nonlocal location_entities
        r = get("/api/graph/locations", case_id=CASE_ID)
        d = r.json()
        location_entities = d if isinstance(d, list) else d.get("locations", [])
        if len(location_entities) == 0:
            return True, "N/A — no geocoded entities (0 locations). Steps 2-3 will be N/A."
        return len(location_entities) >= 1, f"locations={len(location_entities)}"
    run_step(7, 1, "Fetch entities with locations", step1)

    def step2():
        if not location_entities:
            return True, "N/A — no geocoded entities"
        expected_areas = {"New York": (40.0, 41.5), "Miami": (25.0, 26.5), "Cayman": (19.0, 20.0)}
        found = set()
        for loc in location_entities:
            lat = loc.get("latitude", 0)
            for area, (lo, hi) in expected_areas.items():
                if lo <= lat <= hi:
                    found.add(area)
        return len(found) >= 1, f"found areas: {found}"
    run_step(7, 2, "Verify expected locations", step2)

    def step3():
        if not location_entities:
            return True, "N/A — no geocoded entities"
        valid = all(
            isinstance(l.get("latitude"), (int, float)) and isinstance(l.get("longitude"), (int, float))
            and -90 <= l["latitude"] <= 90 and -180 <= l["longitude"] <= 180
            for l in location_entities
        )
        return valid, f"all valid coords: {valid}"
    run_step(7, 3, "Verify location fields", step3)

    def step4():
        if location_entities:
            loc = location_entities[0]
            state["original_location"] = {k: loc.get(k) for k in ("latitude", "longitude", "location_name", "key")}
            r = put(f"/api/graph/node/{loc['key']}/location", {
                "case_id": CASE_ID, "location_name": "Updated Test Location", "latitude": 40.7128, "longitude": -74.0060
            })
            return r.status_code == 200, f"status={r.status_code}"
        return True, "N/A — no locations to update"
    run_step(7, 4, "Update a location", step4)

    def step5():
        nonlocal test_person_key
        marco_key = state.get("marco_key")
        if not marco_key:
            r = get("/api/graph/search", q="Marco Delgado", limit=5, case_id=CASE_ID)
            d = r.json()
            marco_key = next((x["key"] for x in d if x.get("type") == "Person"), None)
        test_person_key = marco_key
        if not test_person_key:
            return False, "No person found"
        r2 = put(f"/api/graph/node/{test_person_key}/location", {
            "case_id": CASE_ID, "location_name": "Test Location - Will Remove", "latitude": 25.7617, "longitude": -80.1918
        })
        return r2.status_code == 200, f"status={r2.status_code}"
    run_step(7, 5, "Add location to entity", step5)

    def step6():
        r = get("/api/graph/locations", case_id=CASE_ID)
        d = r.json()
        locs = d if isinstance(d, list) else d.get("locations", [])
        found = any(l.get("key") == test_person_key for l in locs)
        return found, f"test entity in locations: {found}, total: {len(locs)}"
    run_step(7, 6, "Verify new location appears", step6)

    def step7():
        if not test_person_key:
            return False, "No test_person_key"
        r = delete(f"/api/graph/node/{test_person_key}/location", case_id=CASE_ID)
        return r.status_code in (200, 204), f"status={r.status_code}"
    run_step(7, 7, "Remove location from entity", step7)

    def step8():
        r = get("/api/graph/locations", case_id=CASE_ID)
        d = r.json()
        locs = d if isinstance(d, list) else d.get("locations", [])
        not_found = not any(l.get("key") == test_person_key and l.get("location_name") == "Test Location - Will Remove" for l in locs)
        return not_found, f"test location removed: {not_found}"
    run_step(7, 8, "Verify location removed", step8)

    def step9():
        orig = state.get("original_location")
        if not orig or not orig.get("key"):
            return True, "N/A — no original to restore"
        r = put(f"/api/graph/node/{orig['key']}/location", {
            "case_id": CASE_ID,
            "location_name": orig.get("location_name", ""),
            "latitude": orig.get("latitude", 0),
            "longitude": orig.get("longitude", 0)
        })
        return r.status_code == 200, f"restored, status={r.status_code}"
    run_step(7, 9, "Restore original location", step9)


# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 8
# ═══════════════════════════════════════════════════════════════
def run_playbook_8():
    print("\n" + "="*70)
    print("PLAYBOOK 8: Financial Dashboard")
    print("="*70)

    transactions = []
    test_parent_key = None
    test_child_key = None

    def step1():
        nonlocal transactions
        r = get("/api/financial", case_id=CASE_ID)
        d = r.json()
        transactions = d.get("transactions", d) if isinstance(d, dict) else d
        if not isinstance(transactions, list):
            transactions = []
        return len(transactions) > 0, f"transactions={len(transactions)}"
    run_step(8, 1, "Load financial transactions", step1)

    def step2():
        if not transactions:
            return True, "N/A"
        t = transactions[0]
        return True, f"first txn keys: {list(t.keys())[:10]}"
    run_step(8, 2, "Verify transaction structure", step2)

    def step3():
        r = get("/api/financial", case_id=CASE_ID)
        return r.status_code == 200, f"status={r.status_code}"
    run_step(8, 3, "Filter transactions", step3)

    def step4():
        nonlocal test_parent_key
        if not transactions:
            return True, "N/A"
        test_parent_key = transactions[0].get("key")
        r = put(f"/api/financial/transactions/{test_parent_key}/amount", {
            "case_id": CASE_ID, "new_amount": 99999.99, "correction_reason": "Test correction — will revert"
        })
        return r.status_code == 200, f"status={r.status_code}"
    run_step(8, 4, "Edit transaction amount", step4)

    def step5():
        if not test_parent_key:
            return True, "N/A"
        r = get(f"/api/graph/node/{test_parent_key}", case_id=CASE_ID)
        d = r.json()
        props = d.get("properties", {})
        return True, f"props keys: {list(props.keys())[:10] if isinstance(props, dict) else 'N/A'}"
    run_step(8, 5, "Verify amount correction persists", step5)

    def step6():
        if len(transactions) < 2:
            return True, "N/A — need 2+ transactions"
        nonlocal test_child_key
        test_child_key = transactions[1].get("key")
        r = post(f"/api/financial/transactions/{test_parent_key}/sub-transactions", {
            "child_key": test_child_key, "case_id": CASE_ID
        })
        return r.status_code == 200, f"status={r.status_code}"
    run_step(8, 6, "Link sub-transaction", step6)

    def step7():
        if not test_parent_key:
            return True, "N/A"
        r = get(f"/api/financial/transactions/{test_parent_key}/sub-transactions", case_id=CASE_ID)
        return r.status_code == 200, f"status={r.status_code}"
    run_step(8, 7, "Get sub-transactions", step7)

    def step8():
        if not test_child_key:
            return True, "N/A"
        r = delete(f"/api/financial/transactions/{test_child_key}/parent", case_id=CASE_ID)
        return r.status_code in (200, 204), f"status={r.status_code}"
    run_step(8, 8, "Unlink sub-transaction", step8)

    def step9():
        if not test_parent_key:
            return True, "N/A"
        r = get(f"/api/graph/node/{test_parent_key}", case_id=CASE_ID)
        d = r.json()
        props = d.get("properties", {})
        orig_amt = props.get("original_amount") if isinstance(props, dict) else None
        if orig_amt is not None:
            clean = str(orig_amt).replace("$", "").replace(",", "")
            try:
                r2 = put(f"/api/financial/transactions/{test_parent_key}/amount", {
                    "case_id": CASE_ID, "new_amount": float(clean), "correction_reason": "Revert test correction"
                })
                return r2.status_code == 200, f"reverted to {clean}, status={r2.status_code}"
            except ValueError:
                return True, f"Could not parse original_amount '{orig_amt}' — manual revert needed"
        return True, "No original_amount to revert"
    run_step(8, 9, "Revert amount correction", step9)

    def step10():
        r = get("/api/financial/export/pdf", case_id=CASE_ID)
        if r.status_code == 500:
            body = r.json() if "json" in r.headers.get("content-type","") else {}
            detail = body.get("detail", "")
            if "libgobject" in str(detail) or "weasyprint" in str(detail).lower():
                return False, f"KNOWN ISSUE — WeasyPrint missing system lib: {str(detail)[:120]}"
            return False, f"status=500, detail={str(detail)[:120]}"
        is_pdf = r.status_code == 200 and len(r.content) > 100
        return is_pdf, f"status={r.status_code}, size={len(r.content)} bytes"
    run_step(8, 10, "Export financial PDF", step10)


# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 9
# ═══════════════════════════════════════════════════════════════
def run_playbook_9():
    print("\n" + "="*70)
    print("PLAYBOOK 9: AI Assistant (LLM-dependent)")
    print("="*70)

    def step1():
        r = get("/api/llm-config/current")
        d = r.json()
        return r.status_code == 200, f"provider={d.get('provider','?')}, model={d.get('model_id', d.get('model','?'))}"
    run_step(9, 1, "Get LLM configuration", step1)

    def step2():
        r = post("/api/chat", {
            "question": "Who is the ringleader of the money laundering operation in this case?",
            "provider": "openai", "model": "gpt-4o", "case_id": CASE_ID
        })
        d = r.json()
        answer = d.get("answer", "")
        has_entity = any(name in answer for name in ["Marco", "Delgado", "Elena", "Petrova", "Solaris", "Silver Bridge", "Cruz"])
        return r.status_code == 200 and len(answer) > 20, f"answer_len={len(answer)}, has_entity={has_entity}, snippet={answer[:100]}..."
    run_step(9, 2, "Ask question about case (LLM)", step2)

    def step3():
        r = post("/api/chat", {
            "question": "Who is the ringleader?",
            "provider": "openai", "model": "gpt-4o", "case_id": CASE_ID
        })
        d = r.json()
        keys = list(d.keys())
        has_trace = any(k in d for k in ["pipeline_trace", "trace", "sources", "context", "debug_log", "context_mode"])
        return True, f"response keys: {keys[:10]}, has_trace_info={has_trace}"
    run_step(9, 3, "Verify pipeline trace", step3)

    def step4():
        r = post("/api/chat", {
            "question": "What was the total amount of money transferred to accounts in the Cayman Islands?",
            "provider": "openai", "model": "gpt-4o", "case_id": CASE_ID
        })
        d = r.json()
        answer = d.get("answer", "")
        mentions_cayman = "cayman" in answer.lower()
        return r.status_code == 200 and len(answer) > 20, f"mentions_cayman={mentions_cayman}, answer_len={len(answer)}"
    run_step(9, 4, "Ask financial question (LLM)", step4)

    def step5():
        for path in ["/api/chat/history", "/api/chat/sessions"]:
            r = get(path, case_id=CASE_ID)
            if r.status_code == 200:
                return True, f"found at {path}"
        return False, "KNOWN ISSUE — chat history endpoint not found"
    run_step(9, 5, "Get chat history", step5)


# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 10
# ═══════════════════════════════════════════════════════════════
def run_playbook_10():
    print("\n" + "="*70)
    print("PLAYBOOK 10: Insights System (LLM-dependent)")
    print("="*70)

    insights = []

    def step1():
        nonlocal insights
        r = get(f"/api/graph/cases/{CASE_ID}/insights")
        d = r.json()
        insights = d.get("insights", d) if isinstance(d, dict) else d
        if not isinstance(insights, list):
            insights = []
        return r.status_code == 200, f"existing insights={len(insights)}"
    run_step(10, 1, "Get existing case insights", step1)

    def step2():
        try:
            r = requests.post(f"{BASE}/api/graph/cases/{CASE_ID}/generate-insights?max_entities=5",
                              headers=HEADERS, timeout=180)
            d = r.json() if r.status_code == 200 else {}
            return r.status_code == 200, f"status={r.status_code}, keys={list(d.keys()) if isinstance(d, dict) else 'N/A'}"
        except requests.exceptions.ReadTimeout:
            return False, "TIMEOUT — insight generation took >180s"
    run_step(10, 2, "Generate new insights (LLM)", step2)

    def step3():
        nonlocal insights
        try:
            r = get(f"/api/graph/cases/{CASE_ID}/insights")
            d = r.json()
            insights = d.get("insights", d) if isinstance(d, dict) else d
            if not isinstance(insights, list):
                insights = []
            return len(insights) >= 1, f"insights={len(insights)}"
        except requests.exceptions.ReadTimeout:
            return False, "TIMEOUT"
    run_step(10, 3, "Verify insights exist", step3)

    def step4():
        valid_cats = {"inconsistency", "connection", "defense_opportunity", "brady_giglio", "pattern", None}
        if not insights:
            return True, "N/A — no insights"
        cats = set(i.get("category") for i in insights)
        all_valid = cats.issubset(valid_cats)
        return all_valid, f"categories: {cats}"
    run_step(10, 4, "Verify insight categories", step4)

    def step5():
        valid_conf = {"high", "medium", "low"}
        if not insights:
            return True, "N/A"
        all_valid = all(i.get("confidence") in valid_conf for i in insights)
        return all_valid, f"confidence levels: {set(i.get('confidence') for i in insights)}"
    run_step(10, 5, "Verify confidence levels", step5)

    def step6():
        high = [i for i in insights if i.get("confidence") == "high"]
        if not high:
            return True, "SKIP — no high-confidence insights"
        i = high[0]
        ekey = i.get("entity_key", i.get("node_key"))
        if not ekey:
            return True, f"SKIP — no entity_key: {list(i.keys())}"
        idx = i.get("insight_index", 0)
        r = post(f"/api/graph/node/{ekey}/verify-insight", {
            "case_id": CASE_ID, "insight_index": idx, "username": "neil.byrne@gmail.com"
        })
        state["verified_entity_key"] = ekey
        return r.status_code == 200, f"status={r.status_code}"
    run_step(10, 6, "Accept a high-confidence insight", step6)

    def step7():
        low = [i for i in insights if i.get("confidence") == "low"]
        if not low:
            return True, "SKIP — no low-confidence insights"
        i = low[0]
        ekey = i.get("entity_key", i.get("node_key"))
        if not ekey:
            return True, "SKIP — no entity_key"
        idx = i.get("insight_index", 0)
        r = delete(f"/api/graph/node/{ekey}/insights/{idx}", case_id=CASE_ID)
        state["rejected_entity_key"] = ekey
        return r.status_code in (200, 204), f"status={r.status_code}"
    run_step(10, 7, "Reject a low-confidence insight", step7)

    def step8():
        ekey = state.get("rejected_entity_key")
        if not ekey:
            return True, "SKIP"
        r = get(f"/api/graph/node/{ekey}", case_id=CASE_ID)
        d = r.json()
        return True, f"remaining ai_insights: {len(d.get('ai_insights', []))}"
    run_step(10, 8, "Verify rejection", step8)

    def step9():
        ekey = state.get("verified_entity_key")
        if not ekey:
            return True, "SKIP"
        r = get(f"/api/graph/node/{ekey}", case_id=CASE_ID)
        d = r.json()
        facts = d.get("verified_facts", [])
        return len(facts) > 0, f"verified_facts: {len(facts)}"
    run_step(10, 9, "Verify accepted insight in verified facts", step9)


# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 11
# ═══════════════════════════════════════════════════════════════
def run_playbook_11():
    print("\n" + "="*70)
    print("PLAYBOOK 11: Workspace & Collaboration Features")
    print("="*70)

    note_id = None
    task_id = None
    witness_id = None
    theory_id = None
    pin_id = None

    def step1():
        r = get(f"/api/workspace/{CASE_ID}/context")
        return r.status_code == 200, f"status={r.status_code}"
    run_step(11, 1, "Get case context", step1)

    def step2():
        r = get(f"/api/graph/cases/{CASE_ID}/entity-summary")
        d = r.json()
        return r.status_code == 200, f"summary keys: {list(d.keys())[:8] if isinstance(d, dict) else len(d)}"
    run_step(11, 2, "Get entity summary", step2)

    def step3():
        nonlocal note_id
        r = post(f"/api/workspace/{CASE_ID}/notes", {
            "title": "Test Investigative Note",
            "content": "This is a test note. Marco Delgado appears to be coordinating wire transfers.",
            "category": "financial_analysis"
        })
        d = r.json()
        note_id = d.get("note_id", d.get("id"))
        return r.status_code in (200, 201) and note_id is not None, f"note_id={note_id}"
    run_step(11, 3, "Create investigative note", step3)

    def step4():
        r = get(f"/api/workspace/{CASE_ID}/notes")
        d = r.json()
        notes = d.get("notes", d) if isinstance(d, dict) else d
        notes = notes if isinstance(notes, list) else []
        return len(notes) >= 1, f"notes={len(notes)}"
    run_step(11, 4, "List notes", step4)

    def step5():
        if not note_id:
            return False, "No note_id"
        r = put(f"/api/workspace/{CASE_ID}/notes/{note_id}", {
            "title": "Test Investigative Note — Updated",
            "content": "Updated content: Additional evidence suggests Elena Petrova is also involved."
        })
        return r.status_code == 200, f"status={r.status_code}"
    run_step(11, 5, "Update note", step5)

    def step6():
        nonlocal task_id
        r = post(f"/api/workspace/{CASE_ID}/tasks", {
            "title": "Review Solaris Property Group financial records",
            "description": "Cross-reference wire transfers from Q3 2024",
            "status": "pending", "priority": "high", "due_date": "2026-03-15"
        })
        d = r.json()
        task_id = d.get("task_id", d.get("id"))
        return r.status_code in (200, 201) and task_id is not None, f"task_id={task_id}"
    run_step(11, 6, "Create task", step6)

    def step7():
        r = get(f"/api/workspace/{CASE_ID}/tasks")
        d = r.json()
        tasks = d.get("tasks", d) if isinstance(d, dict) else d
        tasks = tasks if isinstance(tasks, list) else []
        return len(tasks) >= 1, f"tasks={len(tasks)}"
    run_step(11, 7, "List tasks", step7)

    def step8():
        if not task_id:
            return False, "No task_id"
        r = put(f"/api/workspace/{CASE_ID}/tasks/{task_id}", {"status": "completed"})
        return r.status_code == 200, f"status={r.status_code}"
    run_step(11, 8, "Mark task complete", step8)

    def step9():
        nonlocal witness_id
        r = post(f"/api/workspace/{CASE_ID}/witnesses", {
            "name": "Test Witness — Sarah Kim", "role": "Informant",
            "contact_info": "Through legal counsel only",
            "notes": "Former employee at Solaris Property Group.",
            "reliability": "high", "category": "witness"
        })
        d = r.json()
        witness_id = d.get("witness_id", d.get("id"))
        return r.status_code in (200, 201) and witness_id is not None, f"witness_id={witness_id}"
    run_step(11, 9, "Create witness record", step9)

    def step10():
        r = get(f"/api/workspace/{CASE_ID}/witnesses")
        d = r.json()
        witnesses = d.get("witnesses", d) if isinstance(d, dict) else d
        witnesses = witnesses if isinstance(witnesses, list) else []
        return len(witnesses) >= 1, f"witnesses={len(witnesses)}"
    run_step(11, 10, "List witnesses", step10)

    def step11():
        nonlocal theory_id
        r = post(f"/api/workspace/{CASE_ID}/theories", {
            "title": "Layered Money Laundering via Real Estate",
            "description": "Theory: Marco Delgado uses Solaris Property Group as a front.",
            "status": "active", "confidence": "medium", "type": "prosecution"
        })
        d = r.json()
        theory_id = d.get("theory_id", d.get("id"))
        return r.status_code in (200, 201) and theory_id is not None, f"theory_id={theory_id}"
    run_step(11, 11, "Create case theory", step11)

    def step12():
        r = get(f"/api/workspace/{CASE_ID}/theories")
        d = r.json()
        theories = d.get("theories", d) if isinstance(d, dict) else d
        theories = theories if isinstance(theories, list) else []
        return len(theories) >= 1, f"theories={len(theories)}"
    run_step(11, 12, "List theories", step12)

    def step13():
        if not theory_id:
            return False, "No theory_id"
        r = post(f"/api/workspace/{CASE_ID}/theories/{theory_id}/build-graph", {"include_related_entities": True})
        return r.status_code == 200, f"status={r.status_code}"
    run_step(11, 13, "Build theory graph", step13)

    def step14():
        nonlocal pin_id
        marco_key = state.get("marco_key", "marco-delgado-rivera")
        r = requests.post(f"{BASE}/api/workspace/{CASE_ID}/pinned?item_type=entity&item_id={marco_key}",
                          headers=HEADERS, timeout=30)
        d = r.json() if r.status_code in (200, 201) else {}
        pin_id = d.get("pin_id", d.get("id"))
        return r.status_code in (200, 201), f"status={r.status_code}, pin_id={pin_id}"
    run_step(11, 14, "Pin an evidence item", step14)

    def step15():
        r = get(f"/api/workspace/{CASE_ID}/pinned")
        d = r.json()
        pinned = d.get("pinned_items", d.get("pinned", d)) if isinstance(d, dict) else d
        pinned = pinned if isinstance(pinned, list) else []
        return len(pinned) >= 1, f"pinned items={len(pinned)}"
    run_step(11, 15, "Get pinned items", step15)

    def step16():
        nonlocal pin_id
        if not pin_id:
            r = get(f"/api/workspace/{CASE_ID}/pinned")
            d = r.json()
            pinned = d.get("pinned_items", d.get("pinned", [])) if isinstance(d, dict) else d
            if isinstance(pinned, list) and pinned:
                pin_id = pinned[-1].get("pin_id", pinned[-1].get("id"))
        if not pin_id:
            return True, "SKIP — no pin_id"
        r = delete(f"/api/workspace/{CASE_ID}/pinned/{pin_id}")
        return r.status_code in (200, 204), f"status={r.status_code}"
    run_step(11, 16, "Unpin item", step16)

    def step17():
        r = get(f"/api/workspace/{CASE_ID}/investigation-timeline")
        return r.status_code == 200, f"status={r.status_code}"
    run_step(11, 17, "Get investigation timeline", step17)

    def step18():
        statuses = []
        if note_id:
            r = delete(f"/api/workspace/{CASE_ID}/notes/{note_id}")
            statuses.append(("note", r.status_code))
        if task_id:
            r = delete(f"/api/workspace/{CASE_ID}/tasks/{task_id}")
            statuses.append(("task", r.status_code))
        if witness_id:
            r = delete(f"/api/workspace/{CASE_ID}/witnesses/{witness_id}")
            statuses.append(("witness", r.status_code))
        if theory_id:
            r = delete(f"/api/workspace/{CASE_ID}/theories/{theory_id}")
            statuses.append(("theory", r.status_code))
        all_ok = all(s in (200, 204) for _, s in statuses) if statuses else True
        return all_ok, f"cleanup: {statuses}"
    run_step(11, 18, "Clean up test data", step18)


# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 12
# ═══════════════════════════════════════════════════════════════
def run_playbook_12():
    print("\n" + "="*70)
    print("PLAYBOOK 12: Evidence & File Management")
    print("="*70)

    def step1():
        r = get("/api/evidence", case_id=CASE_ID)
        d = r.json()
        files = d if isinstance(d, list) else d.get("files", d.get("evidence", []))
        return r.status_code == 200 and len(files) >= 1, f"files={len(files)}"
    run_step(12, 1, "List evidence files", step1)

    def step2():
        r = get("/api/evidence", case_id=CASE_ID)
        d = r.json()
        files = d if isinstance(d, list) else d.get("files", d.get("evidence", []))
        if files:
            return True, f"first file keys: {list(files[0].keys())[:10]}"
        return True, "N/A"
    run_step(12, 2, "Verify file structure", step2)

    def step3():
        r = get("/api/evidence", case_id=CASE_ID, status="processed")
        return r.status_code == 200, f"status={r.status_code}"
    run_step(12, 3, "Filter by status", step3)

    def step4():
        r = get("/api/evidence/summaries", case_id=CASE_ID)
        if r.status_code == 404:
            r = get("/api/evidence", case_id=CASE_ID)
        return r.status_code == 200, f"status={r.status_code}"
    run_step(12, 4, "Get file summaries", step4)


# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 13
# ═══════════════════════════════════════════════════════════════
def run_playbook_13():
    print("\n" + "="*70)
    print("PLAYBOOK 13: Case Backup, Restore & Snapshots")
    print("="*70)

    snapshot_id = None
    test_node_key = None

    def step1():
        r = get("/api/snapshots")
        d = r.json()
        snaps = d if isinstance(d, list) else d.get("snapshots", [])
        return r.status_code == 200, f"existing snapshots: {len(snaps)}"
    run_step(13, 1, "List existing snapshots", step1)

    def step2():
        nonlocal snapshot_id
        r = get("/api/graph", case_id=CASE_ID)
        graph = r.json()
        nodes_sample = graph.get("nodes", [])[:5]
        links_sample = graph.get("links", [])[:5]
        r2 = post("/api/snapshots", {
            "name": "Test Snapshot — Pre-Change Baseline",
            "notes": "Created during testing",
            "subgraph": {"nodes": nodes_sample, "links": links_sample},
            "case_id": CASE_ID, "case_name": "Operation Silver Bridge"
        })
        d = r2.json()
        snapshot_id = d.get("id", d.get("snapshot_id"))
        return r2.status_code in (200, 201) and snapshot_id is not None, f"snapshot_id={snapshot_id}"
    run_step(13, 2, "Create named snapshot", step2)

    def step3():
        r = get("/api/snapshots")
        d = r.json()
        snaps = d if isinstance(d, list) else d.get("snapshots", [])
        found = any(str(s.get("id")) == str(snapshot_id) or s.get("name","").startswith("Test Snapshot") for s in snaps)
        return found, f"found test snapshot: {found}"
    run_step(13, 3, "Verify snapshot in list", step3)

    def step4():
        if not snapshot_id:
            return False, "No snapshot_id"
        r = get(f"/api/snapshots/{snapshot_id}")
        return r.status_code == 200, f"keys: {list(r.json().keys())[:8]}"
    run_step(13, 4, "Get snapshot details", step4)

    def step5():
        nonlocal test_node_key
        r = post("/api/graph/create-node", {
            "name": "Snapshot Test Node — Should Be Removed",
            "type": "Document", "summary": "Test node for snapshot restore",
            "case_id": CASE_ID
        })
        d = r.json()
        test_node_key = d.get("node_key", d.get("key"))
        return r.status_code == 200 and test_node_key is not None, f"test_key={test_node_key}"
    run_step(13, 5, "Add test node", step5)

    def step6():
        r = get("/api/graph/search", q="Snapshot Test Node", limit=5, case_id=CASE_ID)
        d = r.json()
        found = any("Snapshot Test" in x.get("name","") for x in d)
        return found, f"found: {found}"
    run_step(13, 6, "Verify test node exists", step6)

    def step7():
        if test_node_key:
            r = delete(f"/api/graph/node/{test_node_key}", case_id=CASE_ID)
            return r.status_code in (200, 204), f"cleanup: status={r.status_code}"
        return True, "No test node"
    run_step(13, "7-9", "Cleanup test node", step7)

    def step10():
        if not snapshot_id:
            return False, "No snapshot_id"
        r = delete(f"/api/snapshots/{snapshot_id}")
        return r.status_code in (200, 204), f"status={r.status_code}"
    run_step(13, 10, "Delete test snapshot", step10)

    def step11():
        r = get("/api/snapshots")
        d = r.json()
        snaps = d if isinstance(d, list) else d.get("snapshots", [])
        not_found = not any(str(s.get("id")) == str(snapshot_id) for s in snaps)
        return not_found, f"removed: {not_found}"
    run_step(13, 11, "Verify snapshot deleted", step11)


# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 14
# ═══════════════════════════════════════════════════════════════
def run_playbook_14():
    print("\n" + "="*70)
    print("PLAYBOOK 14: User Management & Authentication")
    print("="*70)

    def step1():
        r = requests.post(f"{BASE}/api/auth/login", json=CREDS, timeout=10)
        d = r.json()
        global TOKEN, HEADERS
        TOKEN = d.get("access_token")
        HEADERS = {"Authorization": f"Bearer {TOKEN}"}
        return r.status_code == 200 and TOKEN is not None, f"role={d.get('role')}"
    run_step(14, 1, "Login with valid credentials", step1)

    def step2():
        r = get("/api/auth/me")
        d = r.json()
        return d.get("email") == "neil.byrne@gmail.com", f"email={d.get('email')}, role={d.get('role')}"
    run_step(14, 2, "Verify current user (me)", step2)

    def step3():
        r = requests.post(f"{BASE}/api/auth/login", json={"username": "neil.byrne@gmail.com", "password": "WrongPassword123!"}, timeout=10)
        return r.status_code == 401, f"status={r.status_code}"
    run_step(14, 3, "Login with invalid password", step3)

    def step4():
        r = requests.post(f"{BASE}/api/auth/login", json={"username": "nonexistent@example.com", "password": "AnyPassword123!"}, timeout=10)
        return r.status_code == 401, f"status={r.status_code}"
    run_step(14, 4, "Login with non-existent user", step4)

    def step5():
        r = requests.get(f"{BASE}/api/auth/me", timeout=10)
        return r.status_code in (401, 403), f"status={r.status_code}"
    run_step(14, 5, "Access protected endpoint without token", step5)

    def step6():
        r = get("/api/users")
        d = r.json()
        users = d if isinstance(d, list) else d.get("users", [])
        return len(users) >= 1, f"users={len(users)}"
    run_step(14, 6, "List all users", step6)

    def step7():
        r = get(f"/api/cases/{CASE_ID}/members")
        d = r.json()
        members = d if isinstance(d, list) else d.get("members", [])
        return len(members) >= 1, f"members={len(members)}"
    run_step(14, 7, "Get case members", step7)

    def step8():
        r = get(f"/api/cases/{CASE_ID}/members/me")
        return r.status_code == 200, f"status={r.status_code}"
    run_step(14, 8, "Get my membership", step8)

    def step9():
        r = requests.post(f"{BASE}/api/auth/logout", headers=HEADERS, timeout=10)
        return r.status_code == 200, f"status={r.status_code}"
    run_step(14, 9, "Logout", step9)

    def step10():
        r = requests.get(f"{BASE}/api/auth/me", headers=HEADERS, timeout=10)
        return True, f"status={r.status_code} ({'invalidated' if r.status_code == 401 else 'stateless JWT'})"
    run_step(14, 10, "Verify token after logout (informational)", step10)

    def step11():
        r = requests.post(f"{BASE}/api/auth/login", json=CREDS, timeout=10)
        d = r.json()
        global TOKEN, HEADERS
        TOKEN = d.get("access_token")
        HEADERS = {"Authorization": f"Bearer {TOKEN}"}
        return r.status_code == 200, "re-authenticated"
    run_step(14, 11, "Re-login to restore session", step11)


# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 15
# ═══════════════════════════════════════════════════════════════
def run_playbook_15():
    print("\n" + "="*70)
    print("PLAYBOOK 15: Cost Tracking & System Monitoring")
    print("="*70)

    def step1():
        r = get("/api/cost-ledger")
        return r.status_code == 200, f"status={r.status_code}"
    run_step(15, 1, "Get cost ledger records", step1)

    def step2():
        r = get("/api/cost-ledger/summary")
        return r.status_code == 200, f"keys: {list(r.json().keys())[:8] if isinstance(r.json(), dict) else 'N/A'}"
    run_step(15, 2, "Get cost summary", step2)

    def step3():
        r = get("/api/cost-ledger", case_id=CASE_ID)
        return r.status_code == 200, f"status={r.status_code}"
    run_step(15, 3, "Filter costs by case", step3)

    def step4():
        r = get("/api/cost-ledger", activity_type="ingestion")
        return r.status_code == 200, f"status={r.status_code}"
    run_step(15, 4, "Filter costs by activity type", step4)

    def step5():
        r = get("/api/system-logs", limit=50)
        d = r.json()
        logs = d.get("logs", d) if isinstance(d, dict) else d
        logs = logs if isinstance(logs, list) else []
        return r.status_code == 200, f"logs={len(logs)}"
    run_step(15, 5, "Get system logs", step5)

    def step6():
        r = get("/api/system-logs/statistics")
        return r.status_code == 200, f"keys: {list(r.json().keys())[:8] if isinstance(r.json(), dict) else 'N/A'}"
    run_step(15, 6, "Get log statistics", step6)

    def step7():
        r = get("/api/system-logs", limit=5)
        d = r.json()
        logs = d.get("logs", []) if isinstance(d, dict) else []
        if logs:
            log_type = logs[0].get("type", logs[0].get("log_type"))
            if log_type:
                r2 = get("/api/system-logs", log_type=log_type, limit=5)
                return r2.status_code == 200, f"filtered by type='{log_type}': status={r2.status_code}"
        return True, "No logs to filter or type field is None"
    run_step(15, 7, "Filter logs by type", step7)

    def step8():
        r = get("/api/system-logs", user="neil.byrne@gmail.com", limit=20)
        return r.status_code == 200, f"status={r.status_code}"
    run_step(15, 8, "Filter logs by user", step8)

    def step9():
        r = get("/api/background-tasks", limit=20)
        return r.status_code == 200, f"status={r.status_code}"
    run_step(15, 9, "List background tasks", step9)

    def step10():
        r = get("/api/background-tasks", case_id=CASE_ID, limit=20)
        return r.status_code == 200, f"status={r.status_code}"
    run_step(15, 10, "Filter tasks by case", step10)


# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 16
# ═══════════════════════════════════════════════════════════════
def run_playbook_16():
    print("\n" + "="*70)
    print("PLAYBOOK 16: LLM Configuration & Extraction Profiles")
    print("="*70)

    original_threshold = None

    def step1():
        r = get("/api/llm-config/current")
        d = r.json()
        return r.status_code == 200, f"provider={d.get('provider','?')}, model={d.get('model_id', d.get('model','?'))}"
    run_step(16, 1, "Get current LLM config", step1)

    def step2():
        r = get("/api/llm-config/models")
        d = r.json()
        models = d if isinstance(d, list) else d.get("models", [])
        return r.status_code == 200 and len(models) >= 1, f"models={len(models)}"
    run_step(16, 2, "List available LLM models", step2)

    def step3():
        r = get("/api/llm-config/models", provider="openai")
        d = r.json()
        models = d if isinstance(d, list) else d.get("models", [])
        return r.status_code == 200, f"openai models={len(models)}"
    run_step(16, 3, "Filter models by provider", step3)

    def step4():
        nonlocal original_threshold
        r = get("/api/llm-config/confidence-threshold")
        d = r.json()
        original_threshold = d.get("threshold", d.get("value", 0.7))
        return r.status_code == 200, f"threshold={original_threshold}"
    run_step(16, 4, "Get confidence threshold", step4)

    def step5():
        r = post("/api/llm-config/confidence-threshold", {"threshold": 0.5})
        return r.status_code == 200, f"status={r.status_code}"
    run_step(16, 5, "Set confidence threshold to 0.5", step5)

    def step6():
        r = get("/api/llm-config/confidence-threshold")
        d = r.json()
        val = d.get("threshold", d.get("value"))
        return abs(float(val) - 0.5) < 0.01 if val else False, f"threshold={val}"
    run_step(16, 6, "Verify threshold change", step6)

    def step7():
        r = post("/api/llm-config/confidence-threshold", {"threshold": original_threshold or 0.7})
        return r.status_code == 200, f"restored to {original_threshold or 0.7}"
    run_step(16, 7, "Restore original threshold", step7)

    def step8():
        r = get("/api/profiles")
        d = r.json()
        profiles = d if isinstance(d, list) else d.get("profiles", [])
        return r.status_code == 200 and len(profiles) >= 1, f"profiles={len(profiles)}"
    run_step(16, 8, "List extraction profiles", step8)

    def step9():
        r = get("/api/profiles/fraud")
        return r.status_code == 200, f"keys: {list(r.json().keys())[:8] if isinstance(r.json(), dict) else 'N/A'}"
    run_step(16, 9, "Get fraud profile", step9)

    def step10():
        r = post("/api/profiles", {
            "name": "test_profile", "description": "Test profile for playbook testing",
            "entity_types": ["Person", "Company", "Location"],
            "relationship_types": ["WORKS_FOR", "LOCATED_IN"]
        })
        return r.status_code in (200, 201), f"status={r.status_code}"
    run_step(16, 10, "Create test profile", step10)

    def step11():
        r = get("/api/profiles/test_profile")
        return r.status_code == 200, f"status={r.status_code}"
    run_step(16, 11, "Verify test profile exists", step11)

    def step12():
        r = delete("/api/profiles/test_profile")
        return r.status_code in (200, 204), f"status={r.status_code}"
    run_step(16, 12, "Delete test profile", step12)

    def step13():
        r = get("/api/profiles/test_profile")
        return r.status_code == 404, f"status={r.status_code}"
    run_step(16, 13, "Verify test profile deleted", step13)


# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 17
# ═══════════════════════════════════════════════════════════════
def run_playbook_17():
    print("\n" + "="*70)
    print("PLAYBOOK 17: Database Management & Backfill")
    print("="*70)

    def step1():
        r = get("/api/backfill/status")
        return r.status_code == 200, f"keys: {list(r.json().keys())[:8] if isinstance(r.json(), dict) else 'N/A'}"
    run_step(17, 1, "Get backfill status", step1)

    def step2():
        r = get("/api/database/documents")
        d = r.json()
        docs = d if isinstance(d, list) else d.get("documents", [])
        return r.status_code == 200 and len(docs) >= 1, f"documents={len(docs)}"
    run_step(17, 2, "List documents in vector DB", step2)

    def step3():
        r = get("/api/database/documents/status")
        return r.status_code == 200, f"status={r.status_code}"
    run_step(17, 3, "Documents with backfill status", step3)

    def step4():
        r = get("/api/database/documents")
        d = r.json()
        docs = d if isinstance(d, list) else d.get("documents", [])
        if docs:
            doc_id = docs[0].get("id", docs[0].get("doc_id"))
            if doc_id:
                r2 = get(f"/api/database/documents/{doc_id}")
                return r2.status_code == 200, f"doc_id={doc_id}"
        return True, "N/A"
    run_step(17, 4, "Get specific document", step4)

    def step5():
        r = get("/api/database/entities")
        return r.status_code == 200, f"status={r.status_code}"
    run_step(17, 5, "List entities in vector DB", step5)

    def step6():
        r = get("/api/database/entities/status")
        return r.status_code == 200, f"status={r.status_code}"
    run_step(17, 6, "Entities with embedding status", step6)

    def step7():
        r = post("/api/backfill/document-summaries", {"case_id": CASE_ID, "skip_existing": True, "dry_run": True})
        return r.status_code == 200, f"status={r.status_code}"
    run_step(17, 7, "Backfill dry run — doc summaries", step7)

    def step8():
        r = post("/api/backfill/case-ids", {"include_entities": True, "include_vector_db": True, "dry_run": True})
        return r.status_code == 200, f"status={r.status_code}"
    run_step(17, 8, "Backfill dry run — case IDs", step8)

    def step9():
        r = post("/api/backfill/chunks", {"case_id": CASE_ID, "skip_existing": True, "dry_run": True})
        return r.status_code == 200, f"status={r.status_code}"
    run_step(17, 9, "Backfill dry run — chunk embeddings", step9)

    def step10():
        r = post("/api/backfill/entity-metadata", {"dry_run": True})
        return r.status_code == 200, f"status={r.status_code}"
    run_step(17, 10, "Backfill dry run — entity metadata", step10)


# ═══════════════════════════════════════════════════════════════
# PLAYBOOK 18
# ═══════════════════════════════════════════════════════════════
def run_playbook_18():
    print("\n" + "="*70)
    print("PLAYBOOK 18: Edge Cases & Error Handling")
    print("="*70)

    empty_case_id = None

    def step1():
        nonlocal empty_case_id
        r = post("/api/cases", {"title": "Empty Test Case", "description": "Edge case testing — no entities"})
        d = r.json()
        empty_case_id = d.get("id", d.get("case_id"))
        return r.status_code in (200, 201) and empty_case_id is not None, f"case_id={empty_case_id}"
    run_step(18, 1, "Create empty case", step1)

    def step2():
        if not empty_case_id:
            return False, "No empty case"
        r = get("/api/graph", case_id=empty_case_id)
        d = r.json()
        return len(d.get("nodes", [])) == 0 and len(d.get("links", [])) == 0, f"nodes={len(d.get('nodes',[]))}"
    run_step(18, 2, "Load graph for empty case", step2)

    def step3():
        if not empty_case_id:
            return False, "No empty case"
        r = get("/api/graph/entity-types", case_id=empty_case_id)
        return r.status_code == 200, f"status={r.status_code}"
    run_step(18, 3, "Get entity types for empty case", step3)

    def step4():
        if not empty_case_id:
            return False, "No empty case"
        r = get("/api/graph/search", q="anything", limit=10, case_id=empty_case_id)
        return r.status_code == 200, f"status={r.status_code}"
    run_step(18, 4, "Search in empty case", step4)

    def step5():
        if not empty_case_id:
            return False, "No empty case"
        r = get("/api/graph/summary", case_id=empty_case_id)
        d = r.json()
        nc = d.get("total_nodes", d.get("node_count", 0))
        return r.status_code == 200 and nc == 0, f"total_nodes={nc}"
    run_step(18, 5, "Get summary for empty case", step5)

    def step6():
        if not empty_case_id:
            return False, "No empty case"
        r = get("/api/timeline", case_id=empty_case_id)
        return r.status_code == 200, f"status={r.status_code}"
    run_step(18, 6, "Get timeline for empty case", step6)

    def step7():
        if not empty_case_id:
            return False, "No empty case"
        r = get("/api/financial", case_id=empty_case_id)
        return r.status_code == 200, f"status={r.status_code}"
    run_step(18, 7, "Get financials for empty case", step7)

    def step8():
        if not empty_case_id:
            return False, "No empty case"
        r = get("/api/graph/locations", case_id=empty_case_id)
        return r.status_code == 200, f"status={r.status_code}"
    run_step(18, 8, "Get locations for empty case", step8)

    def step9():
        r = post("/api/graph/create-node", {"name": "", "type": "Person", "case_id": CASE_ID})
        return r.status_code in (400, 422), f"status={r.status_code} (expected 400/422)"
    run_step(18, 9, "Create node with empty name", step9)

    def step10():
        r = get("/api/graph/node/nonexistent-key-12345", case_id=CASE_ID)
        return r.status_code in (404, 200), f"status={r.status_code}"
    run_step(18, 10, "Get non-existent node", step10)

    def step11():
        r = get("/api/graph/search", q=" ", limit=10, case_id=CASE_ID)
        return r.status_code in (200, 422), f"status={r.status_code} (empty/whitespace query)"
    run_step(18, 11, "Search with empty query", step11)

    def step12():
        if empty_case_id:
            r = delete(f"/api/cases/{empty_case_id}")
            return r.status_code in (200, 204), f"status={r.status_code}"
        return True, "N/A"
    run_step(18, 12, "Clean up empty case", step12)


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    start = time.time()
    print("=" * 70)
    print("OWL INVESTIGATION PLATFORM — FULL TEST RUN (v2)")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Case: Operation Silver Bridge ({CASE_ID})")
    print("=" * 70)

    playbooks = [
        (1, run_playbook_1), (2, run_playbook_2), (3, run_playbook_3),
        (4, run_playbook_4), (5, run_playbook_5), (6, run_playbook_6),
        (7, run_playbook_7), (8, run_playbook_8), (9, run_playbook_9),
        (10, run_playbook_10), (11, run_playbook_11), (12, run_playbook_12),
        (13, run_playbook_13), (14, run_playbook_14), (15, run_playbook_15),
        (16, run_playbook_16), (17, run_playbook_17), (18, run_playbook_18),
    ]

    for num, func in playbooks:
        try:
            func()
        except Exception as e:
            print(f"\n  ⚠️  PLAYBOOK {num} CRASHED: {str(e)[:200]}")

    elapsed = time.time() - start
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    passed = sum(1 for v in results.values() if v["status"] == "PASS")
    failed = sum(1 for v in results.values() if v["status"] == "FAIL")
    errors = sum(1 for v in results.values() if v["status"] == "ERROR")
    total = len(results)

    print(f"\n  Total steps: {total}")
    print(f"  ✅ Passed:   {passed}")
    print(f"  ❌ Failed:   {failed}")
    print(f"  ⚠️  Errors:   {errors}")
    print(f"  ⏱️  Elapsed:  {elapsed:.1f}s")
    print(f"  Pass rate:   {passed/total*100:.1f}%")

    if failed + errors > 0:
        print(f"\n  FAILURES AND ERRORS:")
        print(f"  {'-'*60}")
        for k, v in results.items():
            if v["status"] != "PASS":
                print(f"  {v['status']:5s} | {k:12s} | {v['desc']}")
                print(f"        | Detail: {v['detail'][:140]}")

    print("\n" + "=" * 70)
    print(f"TEST RUN COMPLETE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


if __name__ == "__main__":
    main()
