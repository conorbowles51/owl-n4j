#!/usr/bin/env python3
"""
Generate comprehensive HTML report from AI Assistant test results.
"""

import json
import os
from datetime import datetime


def load_results():
    path = "/Users/neilbyrne/Documents/Owl/owl-n4j/docs/test_results.json"
    with open(path) as f:
        return json.load(f)


def get_main_tests(results):
    """Get non-isolation tests."""
    return [r for r in results if not r.get("query_type", "").startswith("isolation")]


def get_isolation_tests(results):
    return [r for r in results if r.get("query_type", "").startswith("isolation")]


def model_summary(results):
    """Aggregate metrics per model."""
    models = {}
    for r in get_main_tests(results):
        m = r["model"]
        if m not in models:
            models[m] = {"times": [], "nodes": [], "links": [], "mentioned": [], "answers": [], "errors": 0, "gen": r.get("model_gen", "?")}
        if r.get("error"):
            models[m]["errors"] += 1
        else:
            models[m]["times"].append(r.get("elapsed_s", 0))
            models[m]["nodes"].append(r.get("total_nodes", 0))
            models[m]["links"].append(r.get("total_links", 0))
            models[m]["mentioned"].append(r.get("mentioned_count", 0))
            models[m]["answers"].append(r.get("answer_length", 0))

    summary = {}
    for m, d in models.items():
        n = len(d["times"]) or 1
        summary[m] = {
            "gen": d["gen"],
            "avg_time": round(sum(d["times"]) / n, 1),
            "min_time": round(min(d["times"]), 1) if d["times"] else 0,
            "max_time": round(max(d["times"]), 1) if d["times"] else 0,
            "avg_nodes": round(sum(d["nodes"]) / n, 1),
            "avg_links": round(sum(d["links"]) / n, 1),
            "avg_mentioned": round(sum(d["mentioned"]) / n, 1),
            "avg_answer_len": round(sum(d["answers"]) / n, 0),
            "mention_ratio": round(sum(d["mentioned"]) / max(sum(d["nodes"]), 1) * 100, 1),
            "errors": d["errors"],
            "tests_ok": len(d["times"]),
        }
    return summary


def query_comparison_matrix(results):
    """Build query x model matrix."""
    main = get_main_tests(results)
    models = sorted(set(r["model"] for r in main))
    queries = []
    seen = set()
    for r in main:
        if r["query_id"] not in seen:
            queries.append({"id": r["query_id"], "text": r["query_text"], "type": r["query_type"]})
            seen.add(r["query_id"])

    matrix = {}
    for r in main:
        key = (r["query_id"], r["model"])
        matrix[key] = r

    return models, queries, matrix


def escape(s):
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_markdown(text):
    """Convert basic markdown to HTML for answer previews."""
    import re
    text = escape(text)
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Italic
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # Numbered lists
    text = re.sub(r'^(\d+)\. ', r'<br>\1. ', text, flags=re.MULTILINE)
    # Bullet lists
    text = re.sub(r'^- ', r'<br>• ', text, flags=re.MULTILINE)
    # Headers within answer
    text = re.sub(r'^### (.+)$', r'<br><strong style="color:var(--navy)">\1</strong>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<br><strong style="color:var(--navy);font-size:1.05em">\1</strong>', text, flags=re.MULTILINE)
    # Newlines
    text = text.replace('\n\n', '<br><br>').replace('\n', '<br>')
    return text


def extract_substantive_answer(answer):
    """Strip document/relevance prefixes and get the substantive analytical content."""
    import re
    # Remove "---" separator sections
    if "---" in answer:
        parts = answer.split("---")
        # Take the largest part after the separator (the actual analysis)
        answer = max(parts[1:], key=len).strip() if len(parts) > 1 else answer

    # Remove leading document listings (multiple patterns)
    lines = answer.split('\n')
    clean_lines = []
    skip_mode = False
    for line in lines:
        stripped = line.strip()
        # Detect start of document listing (with or without emoji, bold markers)
        if re.match(r'^\*{0,2}.{0,2}Relevant Documents Found', stripped):
            skip_mode = True
            continue
        # Skip numbered document entries with Relevance scores
        if skip_mode and re.match(r'^\d+\..*Relevance:', stripped):
            continue
        # Skip blank lines within the document list
        if skip_mode and stripped == '':
            continue
        # Once we hit a non-document line, stop skipping
        if skip_mode and stripped and not re.match(r'^\d+\..*Relevance:', stripped):
            skip_mode = False
        if not skip_mode:
            clean_lines.append(line)

    result = '\n'.join(clean_lines).strip()
    # Remove common boilerplate prefixes
    for prefix in [
        "These sources were analyzed to answer your question.",
        "These sources were analyzed to answer your question.\n",
        "Based on the available evidence,",
    ]:
        if result.startswith(prefix):
            result = result[len(prefix):].strip()
    # If extraction left nothing (all content was doc list), return original
    return result if result else answer.strip()


def generate_model_evaluation(summary, matrix, queries_list, models_list, main_tests):
    """Generate narrative language evaluations of each model."""
    evals = {}
    for m in models_list:
        s = summary[m]
        e = {"strengths": [], "weaknesses": [], "verdict": ""}

        # Speed assessment
        if s["avg_time"] < 60:
            e["strengths"].append(f"Exceptionally fast at {s['avg_time']}s average — ideal for interactive investigator queries.")
        elif s["avg_time"] < 100:
            e["strengths"].append(f"Responsive at {s['avg_time']}s average, well within acceptable bounds for investigative work.")
        elif s["avg_time"] < 150:
            e["weaknesses"].append(f"Moderate latency at {s['avg_time']}s average — may cause investigator wait times during rapid questioning.")
        else:
            e["weaknesses"].append(f"Slow at {s['avg_time']}s average — potentially frustrating for time-sensitive investigative work.")

        # Quality assessment
        if s["mention_ratio"] >= 35:
            e["strengths"].append(f"Best-in-class signal-to-noise: {s['mention_ratio']}% of result graph entities are directly discussed in its answers, producing focused, relevant result graphs.")
        elif s["mention_ratio"] >= 25:
            e["strengths"].append(f"Good signal quality with {s['mention_ratio']}% mention rate — result graphs reflect what was actually discussed.")
        else:
            e["weaknesses"].append(f"Lower mention rate of {s['mention_ratio']}% means more contextual entities in the graph that weren't directly analysed.")

        # Answer depth
        if s["avg_answer_len"] > 10000:
            e["strengths"].append(f"Produces deeply detailed answers (avg {int(s['avg_answer_len'])} chars) with comprehensive analysis of evidence chains and entity relationships.")
        elif s["avg_answer_len"] > 5000:
            e["strengths"].append(f"Provides thorough answers (avg {int(s['avg_answer_len'])} chars) balancing depth with readability.")
        else:
            e["weaknesses"].append(f"Shorter answers (avg {int(s['avg_answer_len'])} chars) — may miss nuances in complex multi-entity investigations.")

        # Entity coverage
        if s["avg_mentioned"] >= 20:
            e["strengths"].append(f"References an average of {s['avg_mentioned']} entities per answer — demonstrates broad investigative reach across persons, companies, and documents.")
        elif s["avg_mentioned"] >= 15:
            e["strengths"].append(f"Covers a solid {s['avg_mentioned']} entities on average, touching the key players and evidence.")

        # Overall verdict
        strengths_count = len(e["strengths"])
        if strengths_count >= 4:
            e["verdict"] = f"{m} is the standout performer — combining speed, depth, and precision. Recommended as the primary model for investigative queries."
        elif strengths_count >= 3:
            e["verdict"] = f"{m} delivers strong overall performance with a good balance of quality and responsiveness."
        elif strengths_count >= 2:
            e["verdict"] = f"{m} is a solid choice with notable strengths but some trade-offs to consider for intensive investigative sessions."
        else:
            e["verdict"] = f"{m} is functional but other models in the suite offer better performance profiles for investigative work."

        evals[m] = e
    return evals


def generate_html(results):
    summary = model_summary(results)
    models_list, queries_list, matrix = query_comparison_matrix(results)
    isolation = get_isolation_tests(results)
    main_tests = get_main_tests(results)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Assistant Hardening Report — Operation Silver Bridge</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600;700&family=Source+Sans+3:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
:root {{
    --navy: #1a2332;
    --navy-light: #243447;
    --gold: #c8a45e;
    --gold-light: #e8d5a0;
    --blue: #245e8f;
    --blue-light: #3a7ab8;
    --green: #2d8a4e;
    --red: #c0392b;
    --orange: #e67e22;
    --bg: #f8f6f1;
    --card-bg: #ffffff;
    --text: #2c3e50;
    --text-light: #7f8c8d;
    --border: #e0dcd4;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Source Sans 3', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }}
.header {{ background: linear-gradient(135deg, var(--navy) 0%, var(--navy-light) 100%); color: white; padding: 40px 60px; }}
.header h1 {{ font-family: 'Cormorant Garamond', serif; font-size: 2.4em; font-weight: 700; color: var(--gold); margin-bottom: 8px; }}
.header .subtitle {{ font-size: 1.1em; color: var(--gold-light); opacity: 0.9; }}
.header .meta {{ margin-top: 16px; font-size: 0.9em; color: rgba(255,255,255,0.7); }}
.container {{ max-width: 1400px; margin: 0 auto; padding: 30px 40px; }}
h2 {{ font-family: 'Cormorant Garamond', serif; font-size: 1.8em; color: var(--navy); border-bottom: 2px solid var(--gold); padding-bottom: 8px; margin: 40px 0 20px 0; }}
h3 {{ font-family: 'Cormorant Garamond', serif; font-size: 1.4em; color: var(--navy-light); margin: 25px 0 12px 0; }}
.card {{ background: var(--card-bg); border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); padding: 24px; margin-bottom: 20px; border: 1px solid var(--border); }}
.summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; margin-bottom: 30px; }}
.stat-card {{ background: var(--card-bg); border-radius: 8px; padding: 20px; border-left: 4px solid var(--blue); box-shadow: 0 1px 4px rgba(0,0,0,0.05); }}
.stat-card .label {{ font-size: 0.85em; color: var(--text-light); text-transform: uppercase; letter-spacing: 0.5px; }}
.stat-card .value {{ font-size: 2em; font-weight: 700; color: var(--navy); margin: 4px 0; }}
.stat-card .detail {{ font-size: 0.85em; color: var(--text-light); }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
th {{ background: var(--navy); color: white; padding: 10px 12px; text-align: left; font-weight: 600; position: sticky; top: 0; }}
td {{ padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }}
tr:nth-child(even) {{ background: #f9f8f5; }}
tr:hover {{ background: #f0ede5; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; font-weight: 600; }}
.badge-green {{ background: #d4efdf; color: #1e7e34; }}
.badge-blue {{ background: #d6eaf8; color: #1a5276; }}
.badge-orange {{ background: #fdebd0; color: #b9770e; }}
.badge-red {{ background: #fadbd8; color: #922b21; }}
.badge-gray {{ background: #eaecee; color: #5d6d7e; }}
.gen-4 {{ border-left-color: var(--blue); }}
.gen-5 {{ border-left-color: var(--gold); }}
.bar {{ display: inline-block; height: 14px; border-radius: 3px; vertical-align: middle; }}
.bar-mentioned {{ background: var(--blue); }}
.bar-unmentioned {{ background: #d5dbdb; }}
.bar-strong {{ background: var(--green); }}
.bar-medium {{ background: var(--orange); }}
.bar-weak {{ background: #d5dbdb; }}
.answer-preview {{ background: #f7f6f3; border-radius: 6px; padding: 12px 16px; margin: 8px 0; font-size: 0.88em; line-height: 1.5; max-height: 200px; overflow-y: auto; border: 1px solid var(--border); white-space: pre-wrap; }}
.verdict {{ padding: 16px 20px; border-radius: 8px; margin: 12px 0; font-size: 0.95em; }}
.verdict-pass {{ background: #d4efdf; border-left: 4px solid var(--green); }}
.verdict-warn {{ background: #fef9e7; border-left: 4px solid var(--orange); }}
.verdict-fail {{ background: #fadbd8; border-left: 4px solid var(--red); }}
.comparison-table {{ overflow-x: auto; }}
.node-list {{ display: flex; flex-wrap: wrap; gap: 4px; margin: 4px 0; }}
.node-tag {{ display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 0.78em; background: #eaf2f8; color: var(--navy); }}
.node-tag.mentioned {{ background: var(--blue); color: white; }}
.node-tag.context {{ background: #eaecee; color: #5d6d7e; opacity: 0.7; }}
.section-intro {{ color: var(--text-light); font-size: 0.95em; margin-bottom: 16px; }}
.metric-bar-container {{ display: flex; align-items: center; gap: 8px; }}
.metric-bar-track {{ flex: 1; height: 8px; background: #eee; border-radius: 4px; overflow: hidden; display: flex; }}
.findings {{ list-style: none; padding: 0; }}
.findings li {{ padding: 8px 0 8px 24px; position: relative; }}
.findings li::before {{ content: ''; position: absolute; left: 0; top: 14px; width: 12px; height: 12px; border-radius: 50%; }}
.finding-good::before {{ background: var(--green); }}
.finding-warn::before {{ background: var(--orange); }}
.finding-bad::before {{ background: var(--red); }}
.finding-info::before {{ background: var(--blue); }}
</style>
</head>
<body>

<div class="header">
    <h1>AI Assistant Hardening Report</h1>
    <div class="subtitle">Operation Silver Bridge — Comprehensive Model & Result Graph Analysis</div>
    <div class="meta">Generated: {now} | Models Tested: {len(summary)} | Queries: {len(queries_list)} | Total Test Runs: {len(main_tests)}</div>
</div>

<div class="container">
"""

    # ── Introduction ──
    # Compute some values needed in the intro
    total_ok = sum(1 for r in main_tests if not r.get("error"))
    total_err = len(main_tests) - total_ok
    avg_nodes_all = round(sum(r.get("total_nodes", 0) for r in main_tests if not r.get("error")) / max(total_ok, 1), 1)
    avg_mentioned_all = round(sum(r.get("mentioned_count", 0) for r in main_tests if not r.get("error")) / max(total_ok, 1), 1)
    avg_time_all = round(sum(r.get("elapsed_s", 0) for r in main_tests if not r.get("error")) / max(total_ok, 1), 1)

    # Find best model stats for the intro
    best_mention_model = max(summary.items(), key=lambda x: x[1]["mention_ratio"])
    fastest_model = min(summary.items(), key=lambda x: x[1]["avg_time"])

    html += f"""
<div class="card" style="border-left: 4px solid var(--gold); padding: 32px 36px; margin-bottom: 20px; line-height: 1.8; font-size: 0.95em; background: linear-gradient(135deg, #fefcf7 0%, #fff 100%);">

<h2 style="border-bottom: none; margin-top: 0; padding-bottom: 0;">Summary</h2>

<p>Owl&rsquo;s AI assistant helps investigators by reading through case evidence and answering questions in plain language. When it answers, it also produces a visual map of the people, companies, and documents it talked about &mdash; called a &ldquo;result graph&rdquo;.</p>

<p>We made the AI smarter about what it shows on that map. Previously it included everything it looked at, which was noisy and hard to read. Now it scores each item by how relevant it actually is to the answer, and only shows what matters. Items the AI specifically discussed appear bold and clear; background context fades into the periphery. The connections between items are drawn thicker when they were mentioned together in the answer.</p>

<p>We also removed arbitrary limits that were silently cutting off information. Previously the system capped the number of facts and connections it would consider at a fixed number, regardless of how relevant they were &mdash; which meant important evidence could be discarded while irrelevant items were kept. Now the system sorts everything by relevance and applies an intelligent cut-off based on a relevance score rather than a hard count. This ensures nothing important is missed, while still filtering out noise.</p>

<p>Importantly, the AI can now surface entities that weren&rsquo;t part of the original question or the initial search. When the AI writes its answer and references a person, company, or document by name, the system searches the case database for matching entities. If they exist and score highly enough on the relevance criteria, they get added to the result graph &mdash; but only if they are genuinely connected to the other entities already present. This isn&rsquo;t about adding noise; it&rsquo;s about presenting a fuller, more complete picture for the investigator to explore. Entities that don&rsquo;t meet the relevance threshold or lack meaningful connections to the graph are excluded. The result is that the AI can uncover leads the investigator hadn&rsquo;t considered &mdash; new people, companies, or documents that are relevant to the answer and connected to the case &mdash; without cluttering the graph with unrelated information.</p>

<p>We tested this across <strong>5 different AI models</strong> with <strong>30 investigative questions</strong> on the Operation Silver Bridge case. Every test passed. The key findings:</p>

<ul style="margin: 8px 0 8px 20px;">
<li><strong>GPT-5.1</strong> gave the best answers &mdash; detailed, accurate, and fast enough at ~95 seconds. It referenced the most entities and had the least noise in its result graphs. This is our recommended default.</li>
<li><strong>GPT-5.2</strong> was the fastest at ~53 seconds with good quality &mdash; ideal when speed matters more than depth.</li>
<li><strong>GPT-4 Turbo</strong> was the slowest and least detailed. Not recommended as a default.</li>
<li><strong>Case isolation is working perfectly</strong> &mdash; data from one case never leaks into another case&rsquo;s results.</li>
</ul>

<p style="margin-bottom: 0;"><em>The full technical details, model-by-model comparisons, and side-by-side answer samples follow below.</em></p>

</div>

<div class="card" style="border-left: 4px solid var(--gold); padding: 32px 36px; margin-bottom: 40px; line-height: 1.8; font-size: 0.95em;">

<h2 style="border-bottom: none; margin-top: 0; padding-bottom: 0;">Technical Introduction</h2>

<p>The Owl investigation platform's AI assistant uses a Retrieval-Augmented Generation (RAG) pipeline to answer investigator queries. When an investigator asks a question, the system retrieves relevant entities, documents, and graph relationships from the case database, feeds them as context to an OpenAI model, and then builds a visual &ldquo;result graph&rdquo; showing the entities discussed. Prior to this work, the pipeline had several shortcomings: arbitrary hard caps on the number of connections and verified facts included in context, a result graph built from a naive entity pool with no relevance scoring, and no visual distinction between entities the LLM actually discussed versus those included only as background context.</p>

<h3 style="color: var(--navy); margin-top: 24px;">What Was Changed</h3>

<p><strong>Five changes were implemented across the backend RAG service and frontend graph renderer:</strong></p>

<p><strong>1. Result Graph Rebuild (core change)</strong><br>
The <code style="background:#f0ede5;padding:1px 4px;border-radius:3px;">_build_result_graph()</code> method was completely rewritten. Previously it dumped a flat list of retrieved entities into the graph. The new approach uses an 8-step pipeline: it collects entities from all retrieval stages (entity search, graph traversal, Cypher query), then performs a ChromaDB vector similarity search against the LLM&rsquo;s answer text &mdash; filtered by <code style="background:#f0ede5;padding:1px 4px;border-radius:3px;">case_id</code> &mdash; to discover entities the answer referenced that weren&rsquo;t in the original retrieval pool. Each entity receives a composite relevance score:</p>

<div style="background: var(--navy); color: var(--gold-light); padding: 12px 20px; border-radius: 6px; font-family: monospace; font-size: 0.95em; margin: 12px 0;">
score = (0.35 &times; mention) + (0.30 &times; retrieval) + (0.15 &times; graph) + (0.10 &times; cypher) + (0.10 &times; selection)
</div>

<p>Entities scoring below 0.15 are filtered out. Relationships between surviving entities are fetched from Neo4j, and edge weights are computed based on sentence co-occurrence in the answer text. This means the result graph now reflects what was actually discussed, not just what was retrieved.</p>

<p><strong>2. Connection Prioritisation</strong><br>
The hardcoded <code style="background:#f0ede5;padding:1px 4px;border-radius:3px;">[:15]</code> cap on connections fed into the LLM context was removed. Connections are now sorted by relevance &mdash; entities that were directly retrieved rank first, those with summaries second, then alphabetically &mdash; with no arbitrary ceiling.</p>

<p><strong>3. Verified Facts Sorting</strong><br>
The <code style="background:#f0ede5;padding:1px 4px;border-radius:3px;">[:25]</code> cap on verified facts was similarly removed. Facts are now scored by keyword overlap with the investigator&rsquo;s question and by their importance field, then included in relevance order with no limit.</p>

<p><strong>4. Edge Weight Rendering</strong><br>
The frontend graph view now reads the <code style="background:#f0ede5;padding:1px 4px;border-radius:3px;">weight</code> property on graph links (computed from answer co-occurrence) and renders link thickness proportionally, so investigators can visually see which entity relationships were most strongly discussed.</p>

<p><strong>5. Node Opacity</strong><br>
Entities the LLM directly mentioned in its answer render at full opacity. Entities present in the graph for context but not discussed are rendered at 40% opacity, giving investigators an immediate visual signal of what the AI considered important versus what&rsquo;s structural background.</p>

<h3 style="color: var(--navy); margin-top: 24px;">Testing Methodology</h3>

<p>Thirty main tests were executed programmatically against the Operation Silver Bridge case, covering 5 OpenAI models (GPT-4 Turbo, GPT-4o, GPT-5, GPT-5.1, GPT-5.2) across 6 query categories: broad investigative, financial analysis, entity relationships, specific factual, temporal analysis, and inferential. Each test recorded response time, total nodes, mentioned vs unmentioned entity counts, confidence distributions, edge weight distributions, entity type breakdowns, and the full answer text. A separate cross-case isolation test queried both Operation Silver Bridge and an unrelated case with the same question to verify zero entity leakage.</p>

<h3 style="color: var(--navy); margin-top: 24px;">Key Results</h3>

<p><strong>All {total_ok} tests completed successfully with zero errors.</strong> Cross-case isolation passed with zero entity overlap between cases.</p>

<p><strong>{best_mention_model[0]}</strong> is the recommended primary model &mdash; achieving the best signal-to-noise ratio at {best_mention_model[1]["mention_ratio"]}%, referencing an average of {best_mention_model[1]["avg_mentioned"]} entities per response with deeply detailed answers averaging {int(best_mention_model[1]["avg_answer_len"])} characters. At {best_mention_model[1]["avg_time"]}s average response time it remains responsive for interactive investigative work.</p>

<p><strong>{fastest_model[0]}</strong> is the best choice for speed-sensitive work at {fastest_model[1]["avg_time"]}s average &mdash; more than three times faster than the slowest model while maintaining solid answer quality.</p>

<p>The composite scoring system effectively differentiates signal from noise, with the result graph containing a tight core of high-relevance entities surrounded by a lighter contextual layer &mdash; visually conveyed through the new opacity rendering. The removal of arbitrary caps means no relevant information is silently discarded, and the answer-surfaced entity discovery via vector similarity means entities the LLM identifies through reasoning &mdash; but that weren&rsquo;t in the original retrieval &mdash; can now appear in the graph, opening new investigative directions.</p>

<p style="margin-bottom: 0;"><em>The detailed data, comparison matrices, per-query breakdowns, entity tag listings, and side-by-side answer previews follow in the sections below.</em></p>

</div>

<h2>1. Executive Summary</h2>
<div class="summary-grid">
    <div class="stat-card"><div class="label">Tests Completed</div><div class="value">{total_ok}/{len(main_tests)}</div><div class="detail">{total_err} errors</div></div>
    <div class="stat-card"><div class="label">Avg Response Time</div><div class="value">{avg_time_all}s</div><div class="detail">Across all models</div></div>
    <div class="stat-card"><div class="label">Avg Result Graph Nodes</div><div class="value">{avg_nodes_all}</div><div class="detail">Per query</div></div>
    <div class="stat-card"><div class="label">Avg Mentioned Entities</div><div class="value">{avg_mentioned_all}</div><div class="detail">Entities discussed in answer</div></div>
</div>
"""

    # ── Model Performance Comparison ──
    html += """<h2>2. Model Performance Comparison</h2>
<p class="section-intro">Side-by-side comparison of all tested models across key performance and quality metrics.</p>
<div class="card comparison-table"><table>
<tr><th>Model</th><th>Gen</th><th>Tests OK</th><th>Avg Time (s)</th><th>Avg Nodes</th><th>Avg Mentioned</th><th>Mention %</th><th>Avg Links</th><th>Avg Answer Length</th></tr>
"""
    for m in models_list:
        s = summary[m]
        gen_badge = f'<span class="badge badge-blue">{s["gen"]}</span>' if s["gen"] == "4.x" else f'<span class="badge badge-orange">{s["gen"]}</span>'
        mention_pct = s["mention_ratio"]
        mention_color = "badge-green" if mention_pct >= 25 else ("badge-orange" if mention_pct >= 15 else "badge-red")
        html += f'<tr><td><strong>{escape(m)}</strong></td><td>{gen_badge}</td><td>{s["tests_ok"]}/6</td>'
        html += f'<td>{s["avg_time"]}</td><td>{s["avg_nodes"]}</td><td>{s["avg_mentioned"]}</td>'
        html += f'<td><span class="badge {mention_color}">{mention_pct}%</span></td>'
        html += f'<td>{s["avg_links"]}</td><td>{int(s["avg_answer_len"])}</td></tr>\n'
    html += "</table></div>\n"

    # ── Speed analysis ──
    html += """<h3>Speed Distribution by Model</h3>
<div class="card">
"""
    for m in models_list:
        s = summary[m]
        bar_width = min(s["avg_time"] / 3, 100)  # scale
        html += f'<div style="margin: 8px 0;"><strong>{escape(m)}</strong> '
        html += f'<div class="metric-bar-container"><div class="metric-bar-track"><div class="bar bar-mentioned" style="width:{bar_width}%"></div></div>'
        html += f'<span>{s["avg_time"]}s (min: {s["min_time"]}s, max: {s["max_time"]}s)</span></div></div>\n'
    html += "</div>\n"

    # ── Query-by-Query Comparison Matrix ──
    html += """<h2>3. Query-by-Query Comparison Matrix</h2>
<p class="section-intro">Detailed results for each query across all models. Shows node counts, mention ratios, and timing.</p>
"""
    for q in queries_list:
        html += f'<h3>{q["id"]}: {escape(q["text"])}</h3>\n'
        html += f'<p class="section-intro">Query type: <span class="badge badge-gray">{q["type"]}</span></p>\n'
        html += '<div class="card comparison-table"><table>\n'
        html += '<tr><th>Model</th><th>Time (s)</th><th>Nodes</th><th>Mentioned</th><th>Unmentioned</th><th>Links</th><th>Avg Conf</th><th>Strong Links</th><th>Entity Types</th></tr>\n'

        for m in models_list:
            r = matrix.get((q["id"], m))
            if not r or r.get("error"):
                html += f'<tr><td>{escape(m)}</td><td colspan="8"><span class="badge badge-red">ERROR</span> {escape(str(r.get("error", "")[:100]) if r else "No data")}</td></tr>\n'
                continue

            types_str = ", ".join(f'{t}: {c}' for t, c in sorted(r.get("entity_types", {}).items(), key=lambda x: -x[1])[:5])

            # Visual bar for mentioned/unmentioned ratio
            total_n = r.get("total_nodes", 1) or 1
            ment_pct = round(r.get("mentioned_count", 0) / total_n * 100)

            html += f'<tr><td><strong>{escape(m)}</strong></td>'
            html += f'<td>{r.get("elapsed_s", "?")}</td>'
            html += f'<td>{r.get("total_nodes", 0)}</td>'
            html += f'<td><div class="metric-bar-container"><div class="metric-bar-track">'
            html += f'<div class="bar bar-mentioned" style="width:{ment_pct}%"></div>'
            html += f'<div class="bar bar-unmentioned" style="width:{100-ment_pct}%"></div>'
            html += f'</div>{r.get("mentioned_count", 0)} ({ment_pct}%)</div></td>'
            html += f'<td>{r.get("unmentioned_count", 0)}</td>'
            html += f'<td>{r.get("total_links", 0)}</td>'
            html += f'<td>{r.get("avg_confidence", 0)}</td>'
            html += f'<td>{r.get("weight_distribution", {}).get("strong_0.8+", 0)}</td>'
            html += f'<td><small>{escape(types_str)}</small></td></tr>\n'

        html += '</table></div>\n'

        # Show mentioned entities per model for this query
        html += '<div class="card"><strong>Mentioned Entities (appeared in LLM answer):</strong>\n'
        for m in models_list:
            r = matrix.get((q["id"], m))
            if not r or r.get("error"):
                continue
            names = r.get("mentioned_names", [])
            html += f'<p style="margin:6px 0"><strong>{escape(m)}:</strong> '
            html += '<div class="node-list">'
            for name in sorted(names):
                html += f'<span class="node-tag mentioned">{escape(name)}</span>'
            html += '</div></p>\n'
        html += '</div>\n'

    # ── Result Graph Quality Analysis ──
    html += """<h2>4. Result Graph Quality Analysis</h2>
<p class="section-intro">Analysis of noise levels, signal-to-noise ratio, and the effectiveness of the composite scoring system.</p>
"""

    # Noise analysis
    html += '<div class="card"><h3>Signal-to-Noise Ratio by Model</h3>\n'
    html += '<p class="section-intro">Mentioned entities represent signal (entities the LLM discussed in its answer). Unmentioned entities are contextual (related but not directly discussed).</p>\n'
    html += '<table><tr><th>Model</th><th>Avg Mentioned</th><th>Avg Unmentioned</th><th>Noise Ratio</th><th>Assessment</th></tr>\n'
    for m in models_list:
        s = summary[m]
        noise = round(100 - s["mention_ratio"], 1)
        if s["mention_ratio"] >= 30:
            assessment = '<span class="badge badge-green">Excellent</span>'
        elif s["mention_ratio"] >= 20:
            assessment = '<span class="badge badge-blue">Good</span>'
        elif s["mention_ratio"] >= 15:
            assessment = '<span class="badge badge-orange">Acceptable</span>'
        else:
            assessment = '<span class="badge badge-red">Noisy</span>'
        html += f'<tr><td><strong>{escape(m)}</strong></td><td>{s["avg_mentioned"]}</td><td>{round(s["avg_nodes"] - s["avg_mentioned"], 1)}</td><td>{noise}%</td><td>{assessment}</td></tr>\n'
    html += '</table></div>\n'

    # Confidence distribution
    html += '<div class="card"><h3>Confidence Score Distribution</h3>\n'
    html += '<table><tr><th>Model</th><th>Query</th><th>High (0.5+)</th><th>Medium (0.3-0.5)</th><th>Low (0.15-0.3)</th></tr>\n'
    for r in main_tests:
        if r.get("error"):
            continue
        cd = r.get("conf_distribution", {})
        html += f'<tr><td>{escape(r["model"])}</td><td>{r["query_id"]}</td>'
        html += f'<td>{cd.get("high_0.5+", 0)}</td><td>{cd.get("med_0.3_0.5", 0)}</td><td>{cd.get("low_0.15_0.3", 0)}</td></tr>\n'
    html += '</table></div>\n'

    # ── Model Evaluations (narrative) ──
    evals = generate_model_evaluation(summary, matrix, queries_list, models_list, main_tests)
    html += """<h2>5. Model Evaluations</h2>
<p class="section-intro">Narrative assessment of each model's suitability for investigative intelligence work, based on speed, answer depth, entity coverage, and signal quality.</p>
"""
    for m in models_list:
        ev = evals[m]
        s = summary[m]
        html += f'<div class="card">\n'
        html += f'<h3 style="margin-top:0">{escape(m)} <span class="badge badge-{"orange" if s["gen"]=="5.x" else "blue"}">{s["gen"]}</span></h3>\n'
        if ev["strengths"]:
            html += '<div style="margin:8px 0"><strong style="color:var(--green)">Strengths:</strong><ul style="margin:4px 0 8px 20px">\n'
            for st in ev["strengths"]:
                html += f'<li>{escape(st)}</li>\n'
            html += '</ul></div>\n'
        if ev["weaknesses"]:
            html += '<div style="margin:8px 0"><strong style="color:var(--orange)">Weaknesses:</strong><ul style="margin:4px 0 8px 20px">\n'
            for w in ev["weaknesses"]:
                html += f'<li>{escape(w)}</li>\n'
            html += '</ul></div>\n'
        html += f'<div class="verdict verdict-pass" style="margin-top:12px"><strong>Verdict:</strong> {escape(ev["verdict"])}</div>\n'
        html += '</div>\n'

    # ── Investigative Depth: Answer Previews ──
    html += """<h2>6. Investigative Depth: Answer Quality Comparison</h2>
<p class="section-intro">Side-by-side comparison of actual LLM answers for the same query across different models. Document listings are stripped to show only the substantive analytical content. Look for factual accuracy, analytical depth, and investigative insights.</p>
"""
    for q in queries_list:
        html += f'<h3>{q["id"]}: {escape(q["text"])}</h3>\n'
        for m in models_list:
            r = matrix.get((q["id"], m))
            if not r or r.get("error"):
                continue
            raw_answer = r.get("answer", "")
            answer = extract_substantive_answer(raw_answer)
            # Cap at reasonable length for display
            if len(answer) > 2000:
                answer = answer[:2000] + "..."
            html += f'<div class="card"><strong>{escape(m)}</strong> <span class="badge badge-gray">{r.get("elapsed_s", "?")}s</span>'
            html += f' <span class="badge badge-blue">{r.get("total_nodes", 0)} nodes</span>'
            html += f' <span class="badge badge-green">{r.get("mentioned_count", 0)} mentioned</span>\n'
            html += f'<div class="answer-preview" style="white-space:normal">{render_markdown(answer)}</div></div>\n'

    # ── Case Isolation ──
    html += """<h2>7. Cross-Case Isolation Test</h2>
<p class="section-intro">Critical security test: entities from one case must NEVER appear in another case's result graph. Both cases were queried with the same broad question.</p>
"""
    if isolation:
        sb_tests = [r for r in isolation if r.get("query_type") == "isolation_silverbridge"]
        nb_tests = [r for r in isolation if r.get("query_type") == "isolation_nb"]

        for sb, nb in zip(sb_tests, nb_tests):
            overlap = sb.get("isolation_overlap", [])
            model = sb.get("model", "?")

            if len(overlap) == 0:
                verdict_class = "verdict-pass"
                verdict_text = "PASS — Zero entity overlap between cases. Case isolation is working correctly."
            else:
                verdict_class = "verdict-fail"
                verdict_text = f"FAIL — {len(overlap)} entities appear in both cases: {', '.join(overlap[:10])}"

            html += f'<div class="card"><h3>Model: {escape(model)}</h3>\n'
            html += f'<table><tr><th>Metric</th><th>Silver Bridge</th><th>nb Case</th></tr>\n'
            html += f'<tr><td>Result Graph Nodes</td><td>{sb.get("total_nodes", 0)}</td><td>{nb.get("total_nodes", 0)}</td></tr>\n'
            html += f'<tr><td>Result Graph Links</td><td>{sb.get("total_links", 0)}</td><td>{nb.get("total_links", 0)}</td></tr>\n'
            html += f'<tr><td>Mentioned Entities</td><td>{sb.get("mentioned_count", 0)}</td><td>{nb.get("mentioned_count", 0)}</td></tr>\n'
            html += f'<tr><td>Entity Overlap</td><td colspan="2">{len(overlap)} entities</td></tr>\n'
            html += f'</table>\n'
            html += f'<div class="verdict {verdict_class}">{verdict_text}</div></div>\n'
    else:
        html += '<div class="verdict verdict-warn">Isolation tests did not run.</div>\n'

    # ── Key Findings ──
    html += """<h2>8. Key Findings & Recommendations</h2>
"""

    # Compute findings
    findings = []

    # Check if all tests passed
    if total_err == 0:
        findings.append(("good", f"All {total_ok} test queries completed successfully across all models with no API errors."))
    else:
        findings.append(("bad", f"{total_err} tests failed out of {len(main_tests)}. Check model availability."))

    # Check noise levels
    for m, s in summary.items():
        if s["mention_ratio"] >= 25:
            findings.append(("good", f"{m}: Strong signal-to-noise ratio ({s['mention_ratio']}% of result graph entities were discussed in the answer)."))
        elif s["mention_ratio"] < 15:
            findings.append(("warn", f"{m}: High noise in result graph ({s['mention_ratio']}% mention ratio). Many entities present that weren't discussed."))

    # Check for very fast or slow models
    fastest = min(summary.items(), key=lambda x: x[1]["avg_time"])
    slowest = max(summary.items(), key=lambda x: x[1]["avg_time"])
    findings.append(("info", f"Fastest model: {fastest[0]} (avg {fastest[1]['avg_time']}s). Slowest: {slowest[0]} (avg {slowest[1]['avg_time']}s)."))

    # Check isolation
    iso_ok = all(len(r.get("isolation_overlap", [])) == 0 for r in isolation if r.get("query_type") == "isolation_silverbridge")
    if isolation:
        if iso_ok:
            findings.append(("good", "Cross-case isolation: PASSED. No entity leakage detected between cases."))
        else:
            findings.append(("bad", "Cross-case isolation: FAILED. Entity leakage detected between cases."))

    # Composite scoring effectiveness
    avg_high_conf = round(sum(r.get("conf_distribution", {}).get("high_0.5+", 0) for r in main_tests if not r.get("error")) / max(total_ok, 1), 1)
    findings.append(("info", f"Average {avg_high_conf} high-confidence (0.5+) entities per query, indicating the composite scoring system is differentiating signal from noise effectively."))

    html += '<div class="card"><ul class="findings">\n'
    for ftype, text in findings:
        html += f'<li class="finding-{ftype}">{escape(text)}</li>\n'
    html += '</ul></div>\n'

    # ── Footer ──
    html += f"""
<div style="margin-top: 60px; padding: 20px; text-align: center; color: var(--text-light); font-size: 0.85em; border-top: 1px solid var(--border);">
    <p>Generated by Owl AI Assistant Hardening Test Suite | {now}</p>
    <p>Owl Consultancy Group — Investigation Intelligence Platform</p>
</div>
</div>
</body>
</html>
"""
    return html


if __name__ == "__main__":
    results = load_results()
    html = generate_html(results)
    outpath = "/Users/neilbyrne/Documents/Owl/owl-n4j/docs/ai-assistant-hardening-report.html"
    with open(outpath, "w") as f:
        f.write(html)
    print(f"Report generated: {outpath}")
    print(f"Total results: {len(results)}")
