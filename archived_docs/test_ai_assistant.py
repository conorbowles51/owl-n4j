#!/usr/bin/env python3
"""
AI Assistant Hardening Test Suite
Tests the RAG pipeline across multiple models and query types.
Generates a comprehensive HTML report with screenshots, comparison matrices,
and detailed evaluations.
"""

import json
import time
import urllib.request
import urllib.error
import os
from datetime import datetime

# Configuration
API_BASE = "http://localhost:5173/api"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJuZWlsLmJ5cm5lQGdtYWlsLmNvbSIsImV4cCI6MTc3Mjk5NDczMn0.mQw0IHUC0MXXjg3v1o5suESjPiF79oE_z72SaNogjl8"
SILVER_BRIDGE_ID = "60b9367c-ec0a-4619-b3ba-eb18ddb91bfb"
NB_CASE_ID = "5b1b41c6-8003-4472-b050-1a7a5ba40ac9"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

# Models to test
MODELS = [
    {"id": "gpt-4o", "name": "GPT-4o", "gen": "4.x"},
    {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "gen": "4.x"},
    {"id": "gpt-5", "name": "GPT-5", "gen": "5.x"},
    {"id": "gpt-5.1", "name": "GPT-5.1", "gen": "5.x"},
    {"id": "gpt-5.2", "name": "GPT-5.2", "gen": "5.x"},
]

# Test queries
QUERIES = [
    {"id": "Q1", "text": "Who are the key suspects in this case and what evidence links them?", "type": "broad_investigative"},
    {"id": "Q2", "text": "What financial transactions appear suspicious and why?", "type": "financial_analysis"},
    {"id": "Q3", "text": "What connections exist between the shell companies identified in this investigation?", "type": "entity_relationships"},
    {"id": "Q4", "text": "Are there any offshore accounts or international money transfers?", "type": "specific_factual"},
    {"id": "Q5", "text": "What timeline of events can be constructed from the evidence?", "type": "temporal_analysis"},
    {"id": "Q6", "text": "What new investigative leads should be pursued based on the current evidence?", "type": "inferential"},
]

# Cross-case isolation query
ISOLATION_QUERY = "Tell me about every person and organization you know about in any case"


def run_query(question, model_id, case_id, selected_keys=None):
    """Run a single query and return detailed results."""
    payload = {
        "question": question,
        "selected_keys": selected_keys,
        "model": model_id,
        "provider": "openai",
        "confidence_threshold": None,
        "case_id": case_id,
    }

    start = time.time()
    try:
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{API_BASE}/chat",
            data=req_data,
            headers=HEADERS,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            elapsed = time.time() - start
            resp_body = resp.read().decode("utf-8")
            status_code = resp.status

        if status_code != 200:
            return {
                "status": status_code,
                "error": resp_body[:500],
                "elapsed_s": round(elapsed, 2),
            }

        data = json.loads(resp_body)
        nodes = data.get("result_graph", {}).get("nodes", [])
        links = data.get("result_graph", {}).get("links", [])

        # Analyse nodes
        mentioned = [n for n in nodes if n.get("mentioned") is True]
        unmentioned = [n for n in nodes if n.get("mentioned") is False]
        confs = [n.get("confidence", 0) for n in nodes]

        # Analyse links
        weights = [l.get("weight", 0) for l in links]

        # Entity type breakdown
        types = {}
        for n in nodes:
            t = n.get("type", "Unknown")
            types[t] = types.get(t, 0) + 1

        return {
            "status": 200,
            "elapsed_s": round(elapsed, 2),
            "answer": data.get("answer", ""),
            "answer_length": len(data.get("answer", "")),
            "context_mode": data.get("context_mode"),
            "context_description": data.get("context_description"),
            "model_info": data.get("model_info"),
            "total_nodes": len(nodes),
            "total_links": len(links),
            "mentioned_count": len(mentioned),
            "unmentioned_count": len(unmentioned),
            "mentioned_names": [n.get("name") for n in mentioned],
            "unmentioned_names": [n.get("name") for n in unmentioned][:20],
            "all_node_names": [n.get("name") for n in nodes],
            "avg_confidence": round(sum(confs) / len(confs), 4) if confs else 0,
            "max_confidence": round(max(confs), 4) if confs else 0,
            "min_confidence": round(min(confs), 4) if confs else 0,
            "conf_distribution": {
                "high_0.5+": len([c for c in confs if c >= 0.5]),
                "med_0.3_0.5": len([c for c in confs if 0.3 <= c < 0.5]),
                "low_0.15_0.3": len([c for c in confs if 0.15 <= c < 0.3]),
            },
            "weight_distribution": {
                "strong_0.8+": len([w for w in weights if w >= 0.8]),
                "medium_0.4_0.8": len([w for w in weights if 0.4 <= w < 0.8]),
                "weak_0_0.4": len([w for w in weights if w < 0.4]),
            },
            "entity_types": types,
            "error": None,
        }
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start
        body = ""
        try:
            body = e.read().decode("utf-8")[:500]
        except Exception:
            pass
        return {
            "status": e.code,
            "error": f"HTTP {e.code}: {body}",
            "elapsed_s": round(elapsed, 2),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "elapsed_s": round(time.time() - start, 2),
        }


def run_all_tests():
    """Run the complete test suite."""
    results = []
    total = len(MODELS) * len(QUERIES)
    done = 0

    print(f"\n{'='*80}")
    print(f"AI ASSISTANT HARDENING TEST SUITE")
    print(f"Case: Operation Silver Bridge")
    print(f"Models: {len(MODELS)} | Queries: {len(QUERIES)} | Total tests: {total}")
    print(f"{'='*80}\n")

    for model in MODELS:
        print(f"\n--- Testing {model['name']} ({model['id']}) ---")
        for query in QUERIES:
            done += 1
            print(f"  [{done}/{total}] {query['id']}: {query['text'][:60]}...", end=" ", flush=True)

            result = run_query(query["text"], model["id"], SILVER_BRIDGE_ID)
            result["model"] = model["name"]
            result["model_id"] = model["id"]
            result["model_gen"] = model["gen"]
            result["query_id"] = query["id"]
            result["query_text"] = query["text"]
            result["query_type"] = query["type"]

            if result.get("error"):
                print(f"ERROR: {result['error'][:80]}")
            else:
                print(f"OK ({result['elapsed_s']}s, {result['total_nodes']} nodes, {result['mentioned_count']} mentioned)")

            results.append(result)

    # Cross-case isolation test
    print(f"\n--- Cross-Case Isolation Test ---")
    for model in MODELS[:2]:  # Test with 2 models
        print(f"  Testing isolation with {model['name']}...", end=" ", flush=True)

        # Query Silver Bridge
        r1 = run_query(ISOLATION_QUERY, model["id"], SILVER_BRIDGE_ID)
        r1["model"] = model["name"]
        r1["model_id"] = model["id"]
        r1["query_id"] = "ISO_SB"
        r1["query_text"] = ISOLATION_QUERY
        r1["query_type"] = "isolation_silverbridge"

        # Query nb case with same question
        r2 = run_query(ISOLATION_QUERY, model["id"], NB_CASE_ID)
        r2["model"] = model["name"]
        r2["model_id"] = model["id"]
        r2["query_id"] = "ISO_NB"
        r2["query_text"] = ISOLATION_QUERY
        r2["query_type"] = "isolation_nb"

        # Check for leakage
        sb_names = set(r1.get("all_node_names", []))
        nb_names = set(r2.get("all_node_names", []))
        overlap = sb_names & nb_names

        r1["isolation_overlap"] = list(overlap)
        r2["isolation_overlap"] = list(overlap)

        results.append(r1)
        results.append(r2)

        print(f"SB: {r1.get('total_nodes', 0)} nodes, NB: {r2.get('total_nodes', 0)} nodes, Overlap: {len(overlap)}")

    return results


def save_results(results):
    """Save raw results to JSON."""
    outpath = "/Users/neilbyrne/Documents/Owl/owl-n4j/docs/test_results.json"
    with open(outpath, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nRaw results saved to {outpath}")
    return outpath


if __name__ == "__main__":
    results = run_all_tests()
    save_results(results)
    print(f"\nTotal tests completed: {len(results)}")
    print("Run generate_report.py next to create the HTML report.")
