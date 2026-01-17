"""
Server Cost Analysis: GPU Server (Ollama) vs Non-GPU Server (OpenAI)

This script compares two server scenarios:
1. GPU Server ($2/hour): Uses Ollama locally (slower, lower quality, no API costs)
2. Non-GPU Server ($10/day): Uses OpenAI API (faster, higher quality, API costs)

Tests both scenarios and generates a comprehensive cost analysis report.
"""

import sys
import json
import time
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import math

# Add parent directory to path for imports
_scripts_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_scripts_dir))

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None

from config import OPENAI_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODEL

# Import profile loader
import importlib.util
_profile_loader_path = _scripts_dir / "profile_loader.py"
_profile_loader_spec = importlib.util.spec_from_file_location("cost_analysis_profile_loader", _profile_loader_path)
_profile_loader_module = importlib.util.module_from_spec(_profile_loader_spec)
_profile_loader_spec.loader.exec_module(_profile_loader_module)
get_ingestion_config = _profile_loader_module.get_ingestion_config

# Server costs
GPU_SERVER_COST_PER_HOUR = 2.00  # $2/hour
NON_GPU_SERVER_COST_PER_DAY = 10.00  # $10/day

# OpenAI pricing per 1M tokens
OPENAI_PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "gpt-5.2": {"input": 3.00, "output": 12.00},
    "gpt-5-mini": {"input": 0.20, "output": 0.80},
    "gpt5-nano": {"input": 0.10, "output": 0.40},
    "gpt-5.1": {"input": 3.00, "output": 12.00},
    "gpt-4.1": {"input": 3.00, "output": 12.00},
}

# Test text (fraud case)
FRAUD_CASE_TEXT = """
Fraud Investigation Report - Case #FI-2024-0837
Date: March 15, 2024
Investigator: Sarah Chen

EXECUTIVE SUMMARY

This investigation involves suspicious financial transactions and potential money laundering activities 
linked to Emerald Imports Ltd, a UK-based trading company registered in London. The case was opened 
following an alert from Barclays Bank regarding unusual transaction patterns.

KEY INDIVIDUALS

John Smith, age 45, serves as the Chief Financial Officer (CFO) of Emerald Imports Ltd. His 
employment with the company began in January 2022. Smith previously worked at Morgan Stanley 
as a senior analyst from 2018-2021. He holds a UK passport (GB123456789) and resides at 
Flat 42, 156 High Street, London, SW1A 1AA.

Maria Rodriguez, age 38, is the sole director of Nexus Trading LLC, a shell company 
incorporated in the Cayman Islands on March 10, 2023. Rodriguez also appears as a nominee 
director for several other offshore entities including Crimson Holdings and Blue Ocean Ventures. 
She is a Spanish national with address listed as P.O. Box 1234, George Town, Cayman Islands.

SUSPICIOUS TRANSACTIONS

The following transactions have been flagged for investigation:

1. Payment dated March 3, 2024: £250,000 transferred from Emerald Imports Ltd account 
   (Barclays Bank, Account #987654321) to Nexus Trading LLC account (Swiss Bank Geneva, 
   Account #CH-789456123). The payment was authorized by John Smith and marked as 
   "Trade services invoice #2024-0456". No corresponding goods or services were delivered.

2. Payment dated March 5, 2024: £125,000 transferred from Nexus Trading LLC to Crimson Holdings 
   account (Monaco Bank, Account #MC-456789012). The transaction occurred within 48 hours 
   of the previous payment, suggesting possible layering activity.

3. Payment dated March 8, 2024: €180,000 transferred from Crimson Holdings to a personal 
   account in Monaco belonging to Maria Rodriguez (Account #MR-789456). The funds were 
   withdrawn in cash on March 12, 2024 at a bank branch in Monaco.

COMMUNICATIONS EVIDENCE

Email correspondence obtained from Emerald Imports Ltd servers shows:

- Email from john.smith@emeraldimports.co.uk to maria.rodriguez@nexustrading.ky dated 
  February 28, 2024 at 14:32 GMT: "Maria, please proceed with the March transaction as 
  discussed. Use the usual invoice reference."

- Email from maria.rodriguez@nexustrading.ky to john.smith@emeraldimports.co.uk dated 
  March 2, 2024 at 09:15 GMT: "Confirmed. The payment structure will follow the previous 
  pattern. Funds should be available by March 6."

Phone records indicate multiple calls between John Smith's mobile (+44 7700 900123) and 
Maria Rodriguez's mobile (+1 345 555 6789) during the period February 25 - March 10, 2024. 
Total call duration: 47 minutes across 12 separate calls.

COMPANY STRUCTURE

Emerald Imports Ltd was incorporated in the UK on June 15, 2021 with registration number 
12345678. The company's registered address is Suite 200, 89 Fleet Street, London, EC4Y 1DH. 
According to Companies House records, the company's shareholders are:
- Robert Williams: 60% (beneficial owner, UK resident)
- Sarah Thompson: 40% (beneficial owner, UK resident)

However, banking records suggest that John Smith has signing authority for all transactions 
over £50,000, which is unusual for a CFO position.

Nexus Trading LLC was incorporated in the Cayman Islands with company number KY-987654. 
The registered agent is Global Corporate Services Ltd. No beneficial ownership information 
is publicly available. The company has no physical office or employees.

RED FLAGS IDENTIFIED

1. Threshold structuring: Multiple transactions just below £250,000 reporting threshold
2. Rapid movement of funds: £250,000 moved through three entities in 5 days
3. Shell company usage: Nexus Trading LLC has no operations or assets
4. Nominee director pattern: Maria Rodriguez appears as director of multiple entities
5. Timing anomalies: Transactions scheduled around month-end reporting periods
6. Geographic layering: Funds moved through UK → Cayman Islands → Monaco → Cash withdrawal
7. Unusual CFO authority: John Smith authorized transactions exceeding typical CFO limits

RECOMMENDATION

This case warrants further investigation under UK Money Laundering Regulations 2017. 
Recommendation: File Suspicious Activity Report (SAR) with UK Financial Intelligence Unit.
"""


def test_ollama_extraction(text: str, model_id: str, profile_name: str = "fraud") -> Dict:
    """Test Ollama extraction and return results with timing."""
    profile = get_ingestion_config(profile_name)
    ingestion_config = profile.get("ingestion", {})
    system_context = ingestion_config.get("system_context", "")
    temperature = ingestion_config.get("temperature", 1.0)
    
    # Build prompt (simplified version of llm_client.py prompt)
    prompt = f"""{system_context}

Extract all entities and relationships from the following document excerpt.

Document: test_fraud_case.txt

Text:
\"\"\"{text}\"\"\"

Return ONLY valid JSON with this exact structure (no markdown, no explanation):

{{
  "entities": [
    {{
      "key": "string",
      "type": "string",
      "name": "string",
      "date": "string or null",
      "location": "string or null",
      "verified_facts": [{{"text": "string", "quote": "string", "page": 1, "importance": 4}}],
      "ai_insights": [{{"text": "string", "confidence": "high", "reasoning": "string"}}]
    }}
  ],
  "relationships": [
    {{"from_key": "string", "to_key": "string", "type": "string", "notes": "string"}}
  ]
}}
"""
    
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_context},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": temperature}
    }
    
    start_time = time.time()
    try:
        resp = requests.post(url, json=payload, timeout=(10, 600))
        resp.raise_for_status()
        elapsed_time = time.time() - start_time
        
        data = resp.json()
        content = (data.get("message") or {}).get("content", "") or ""
        
        # Parse result
        try:
            extraction = json.loads(content)
        except json.JSONDecodeError as e:
            extraction = {"error": str(e), "raw_response": content[:500]}
        
        entities = extraction.get("entities", []) if "error" not in extraction else []
        relationships = extraction.get("relationships", []) if "error" not in extraction else []
        
        return {
            "status": "success",
            "elapsed_time_seconds": elapsed_time,
            "extraction": {
                "entities_count": len(entities),
                "relationships_count": len(relationships),
                "entities": entities,
                "relationships": relationships,
            },
            "error": None,
        }
    except Exception as e:
        elapsed_time = time.time() - start_time
        return {
            "status": "error",
            "elapsed_time_seconds": elapsed_time,
            "extraction": None,
            "error": str(e),
        }


def test_openai_extraction(text: str, model_id: str, profile_name: str = "fraud") -> Dict:
    """Test OpenAI extraction and return results with timing and token usage."""
    if not OPENAI_AVAILABLE or not OPENAI_API_KEY:
        return {
            "status": "error",
            "elapsed_time_seconds": 0,
            "token_usage": None,
            "cost_usd": None,
            "extraction": None,
            "error": "OpenAI not available or API key not set",
        }
    
    profile = get_ingestion_config(profile_name)
    ingestion_config = profile.get("ingestion", {})
    system_context = ingestion_config.get("system_context", "")
    temperature = ingestion_config.get("temperature", 1.0)
    
    # Build prompt
    prompt = f"""{system_context}

Extract all entities and relationships from the following document excerpt.

Document: test_fraud_case.txt

Text:
\"\"\"{text}\"\"\"

Return ONLY valid JSON with this exact structure (no markdown, no explanation):

{{
  "entities": [
    {{
      "key": "string",
      "type": "string",
      "name": "string",
      "date": "string or null",
      "location": "string or null",
      "verified_facts": [{{"text": "string", "quote": "string", "page": 1, "importance": 4}}],
      "ai_insights": [{{"text": "string", "confidence": "high", "reasoning": "string"}}]
    }}
  ],
  "relationships": [
    {{"from_key": "string", "to_key": "string", "type": "string", "notes": "string"}}
  ]
}}
"""
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    messages = [
        {"role": "system", "content": system_context},
        {"role": "user", "content": prompt}
    ]
    
    start_time = time.time()
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
            timeout=600,
        )
        elapsed_time = time.time() - start_time
        
        content = response.choices[0].message.content or ""
        usage = response.usage
        
        token_usage = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
        }
        
        # Calculate cost
        pricing = OPENAI_PRICING.get(model_id, OPENAI_PRICING["gpt-4o"])
        cost_usd = (
            (token_usage["prompt_tokens"] / 1_000_000) * pricing["input"] +
            (token_usage["completion_tokens"] / 1_000_000) * pricing["output"]
        )
        
        # Parse result
        try:
            extraction = json.loads(content)
        except json.JSONDecodeError as e:
            extraction = {"error": str(e), "raw_response": content[:500]}
        
        entities = extraction.get("entities", []) if "error" not in extraction else []
        relationships = extraction.get("relationships", []) if "error" not in extraction else []
        
        return {
            "status": "success",
            "elapsed_time_seconds": elapsed_time,
            "token_usage": token_usage,
            "cost_usd": cost_usd,
            "extraction": {
                "entities_count": len(entities),
                "relationships_count": len(relationships),
                "entities": entities,
                "relationships": relationships,
            },
            "error": None,
        }
    except Exception as e:
        elapsed_time = time.time() - start_time
        return {
            "status": "error",
            "elapsed_time_seconds": elapsed_time,
            "token_usage": None,
            "cost_usd": None,
            "extraction": None,
            "error": str(e),
        }


def calculate_monthly_costs(
    documents_per_month: int,
    avg_chunks_per_document: float,
    avg_processing_time_per_chunk_seconds: float,
    server_cost_per_hour: float,
    api_cost_per_chunk: float = 0.0,
    server_uptime_hours_per_day: float = 24.0,
    pay_per_hour: bool = True,
) -> Dict:
    """Calculate monthly costs for a given scenario.
    
    Args:
        pay_per_hour: If True, pay only for actual processing hours. If False, pay for full days needed.
    """
    total_chunks = documents_per_month * avg_chunks_per_document
    total_processing_time_hours = (total_chunks * avg_processing_time_per_chunk_seconds) / 3600
    
    # Server costs
    if server_cost_per_hour > 0:
        if pay_per_hour:
            # Pay only for actual processing hours (e.g., GPU server)
            server_cost = total_processing_time_hours * server_cost_per_hour
        else:
            # Pay for full days needed (e.g., fixed daily cost server)
            days_needed = math.ceil(total_processing_time_hours / server_uptime_hours_per_day)
            server_cost = days_needed * (server_cost_per_hour * server_uptime_hours_per_day)
    else:
        server_cost = 0
    
    # API costs
    api_cost = total_chunks * api_cost_per_chunk
    
    total_cost = server_cost + api_cost
    
    return {
        "documents_per_month": documents_per_month,
        "total_chunks": total_chunks,
        "total_processing_time_hours": total_processing_time_hours,
        "total_processing_time_days": total_processing_time_hours / 24,
        "server_cost": server_cost,
        "api_cost": api_cost,
        "total_cost": total_cost,
        "cost_per_document": total_cost / documents_per_month if documents_per_month > 0 else 0,
    }


def generate_report(
    ollama_results: Dict,
    openai_results: List[Dict],
    documents_per_month: int = 100,
    avg_chunks_per_document: float = 10.0,
) -> str:
    """Generate a comprehensive cost analysis report."""
    
    report_lines = []
    report_lines.append("=" * 100)
    report_lines.append("SERVER COST ANALYSIS REPORT")
    report_lines.append("GPU Server (Ollama) vs Non-GPU Server (OpenAI)")
    report_lines.append("=" * 100)
    report_lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Test Scenario: Processing {documents_per_month} documents/month")
    report_lines.append(f"Average Chunks per Document: {avg_chunks_per_document}")
    report_lines.append("\n" + "=" * 100)
    
    # Scenario 1: GPU Server with Ollama
    report_lines.append("\n## SCENARIO 1: GPU SERVER WITH OLLAMA")
    report_lines.append("-" * 100)
    report_lines.append(f"Server Specs: NVIDIA L4 24GB GPU")
    report_lines.append(f"Server Cost: ${GPU_SERVER_COST_PER_HOUR:.2f}/hour (${GPU_SERVER_COST_PER_HOUR * 24:.2f}/day, ${GPU_SERVER_COST_PER_HOUR * 24 * 30:.2f}/month)")
    report_lines.append(f"LLM: Ollama (local inference)")
    report_lines.append(f"API Costs: $0.00 (no external API calls)")
    report_lines.append(f"Note: Server runs 24/7 regardless of processing volume")
    
    if ollama_results.get("status") == "skipped":
        report_lines.append("\nNote: Ollama tests were skipped - using estimated performance metrics")
    
    if ollama_results.get("status") in ["success", "skipped"]:
        ollama_time = ollama_results["elapsed_time_seconds"]
        ollama_entities = ollama_results["extraction"]["entities_count"]
        ollama_relationships = ollama_results["extraction"]["relationships_count"]
        
        report_lines.append(f"\nTest Results (1 chunk):")
        report_lines.append(f"  - Processing Time: {ollama_time:.2f} seconds ({ollama_time/60:.2f} minutes)")
        report_lines.append(f"  - Entities Extracted: {ollama_entities}")
        report_lines.append(f"  - Relationships Extracted: {ollama_relationships}")
        
        # Monthly cost calculation (GPU server runs 24/7 at $2/hour)
        # GPU server cost = $2/hour × 24 hours/day × 30 days/month = $1,440/month
        gpu_monthly_server_cost = GPU_SERVER_COST_PER_HOUR * 24 * 30  # $1,440/month fixed
        
        # Calculate API costs (none for Ollama)
        total_chunks = documents_per_month * avg_chunks_per_document
        api_cost = 0.0
        
        ollama_monthly = {
            "documents_per_month": documents_per_month,
            "total_chunks": total_chunks,
            "total_processing_time_hours": (total_chunks * ollama_time) / 3600,
            "total_processing_time_days": (total_chunks * ollama_time) / 3600 / 24,
            "server_cost": gpu_monthly_server_cost,
            "api_cost": api_cost,
            "total_cost": gpu_monthly_server_cost + api_cost,
            "cost_per_document": (gpu_monthly_server_cost + api_cost) / documents_per_month if documents_per_month > 0 else 0,
        }
        
        report_lines.append(f"\nMonthly Cost Projection ({documents_per_month} documents):")
        report_lines.append(f"  - Total Processing Time: {ollama_monthly['total_processing_time_hours']:.2f} hours ({ollama_monthly['total_processing_time_days']:.2f} days)")
        report_lines.append(f"  - Server Cost: ${ollama_monthly['server_cost']:.2f}")
        report_lines.append(f"  - API Costs: ${ollama_monthly['api_cost']:.2f}")
        report_lines.append(f"  - TOTAL MONTHLY COST: ${ollama_monthly['total_cost']:.2f}")
        report_lines.append(f"  - Cost per Document: ${ollama_monthly['cost_per_document']:.4f}")
    else:
        report_lines.append(f"\nTest Results: ERROR - {ollama_results.get('error', 'Unknown error')}")
        ollama_monthly = None
    
    # Scenario 2: Non-GPU Server with OpenAI
    report_lines.append("\n## SCENARIO 2: NON-GPU SERVER WITH OPENAI")
    report_lines.append("-" * 100)
    report_lines.append(f"Server Cost: ${NON_GPU_SERVER_COST_PER_DAY:.2f}/day (${NON_GPU_SERVER_COST_PER_DAY * 30:.2f}/month)")
    report_lines.append(f"LLM: OpenAI API (cloud inference)")
    
    best_openai = None
    best_cost = float('inf')
    
    for result in openai_results:
        if result["status"] == "success":
            model_id = result.get("model_id", "unknown")
            openai_time = result["elapsed_time_seconds"]
            openai_cost_per_chunk = result["cost_usd"]
            openai_entities = result["extraction"]["entities_count"]
            openai_relationships = result["extraction"]["relationships_count"]
            
            report_lines.append(f"\n### Model: {model_id}")
            report_lines.append(f"  Test Results (1 chunk):")
            report_lines.append(f"    - Processing Time: {openai_time:.2f} seconds ({openai_time/60:.2f} minutes)")
            report_lines.append(f"    - Cost per Chunk: ${openai_cost_per_chunk:.6f}")
            report_lines.append(f"    - Token Usage: {result['token_usage']['total_tokens']:,} tokens")
            report_lines.append(f"    - Entities Extracted: {openai_entities}")
            report_lines.append(f"    - Relationships Extracted: {openai_relationships}")
            
            # Monthly cost calculation
            openai_monthly = calculate_monthly_costs(
                documents_per_month=documents_per_month,
                avg_chunks_per_document=avg_chunks_per_document,
                avg_processing_time_per_chunk_seconds=openai_time,
                server_cost_per_hour=0.0,  # Fixed daily cost, handled separately
                api_cost_per_chunk=openai_cost_per_chunk,
            )
            
            # Add fixed monthly server cost
            monthly_server_cost = NON_GPU_SERVER_COST_PER_DAY * 30
            openai_monthly["server_cost"] = monthly_server_cost
            openai_monthly["total_cost"] = openai_monthly["api_cost"] + monthly_server_cost
            openai_monthly["cost_per_document"] = openai_monthly["total_cost"] / documents_per_month
            
            report_lines.append(f"  Monthly Cost Projection ({documents_per_month} documents):")
            report_lines.append(f"    - Total Processing Time: {openai_monthly['total_processing_time_hours']:.2f} hours ({openai_monthly['total_processing_time_days']:.2f} days)")
            report_lines.append(f"    - Server Cost (fixed): ${monthly_server_cost:.2f}")
            report_lines.append(f"    - API Costs: ${openai_monthly['api_cost']:.2f}")
            report_lines.append(f"    - TOTAL MONTHLY COST: ${openai_monthly['total_cost']:.2f}")
            report_lines.append(f"    - Cost per Document: ${openai_monthly['cost_per_document']:.4f}")
            
            result["monthly_cost"] = openai_monthly
            if openai_monthly["total_cost"] < best_cost:
                best_cost = openai_monthly["total_cost"]
                best_openai = {"model": model_id, "result": result, "monthly": openai_monthly}
    
    # Comparison
    report_lines.append("\n" + "=" * 100)
    report_lines.append("## COMPARISON & RECOMMENDATIONS")
    report_lines.append("=" * 100)
    
    if ollama_monthly and best_openai:
        ollama_total = ollama_monthly["total_cost"]
        openai_total = best_openai["monthly"]["total_cost"]
        difference = abs(ollama_total - openai_total)
        
        report_lines.append(f"\n### Cost Comparison")
        report_lines.append(f"GPU Server (Ollama): ${ollama_total:.2f}/month")
        report_lines.append(f"Non-GPU Server ({best_openai['model']}): ${openai_total:.2f}/month")
        report_lines.append(f"Difference: ${difference:.2f}/month ({(openai_total - ollama_total):.2f})")
        
        if ollama_total < openai_total:
            report_lines.append(f"\n✓ GPU Server is ${difference:.2f}/month CHEAPER")
        else:
            report_lines.append(f"\n✓ Non-GPU Server is ${difference:.2f}/month CHEAPER")
    
    # Pros and Cons
    report_lines.append("\n### SCENARIO 1: GPU SERVER WITH OLLAMA")
    report_lines.append("\nPROS:")
    report_lines.append("  • No API costs - all inference happens locally")
    report_lines.append("  • Lower cost for high-volume processing (if utilized efficiently)")
    report_lines.append("  • Data privacy - no data sent to external APIs")
    report_lines.append("  • No rate limits or API quota restrictions")
    report_lines.append("  • Predictable server costs")
    report_lines.append("\nCONS:")
    report_lines.append("  • Slower processing time per chunk (GPU performance limitations)")
    report_lines.append("  • Lower quality extraction (Ollama models generally inferior to OpenAI)")
    report_lines.append("  • Higher cost if server sits idle")
    report_lines.append("  • Requires GPU infrastructure management")
    report_lines.append("  • Limited model selection compared to OpenAI")
    report_lines.append("  • Server must run 24/7 or management overhead for start/stop")
    
    report_lines.append("\n### SCENARIO 2: NON-GPU SERVER WITH OPENAI")
    report_lines.append("\nPROS:")
    report_lines.append("  • Faster processing time (OpenAI's optimized infrastructure)")
    report_lines.append("  • Higher quality extraction (state-of-the-art models)")
    report_lines.append("  • Lower fixed server cost ($10/day vs $2/hour)")
    report_lines.append("  • Access to latest models (GPT-4o, GPT-5 variants)")
    report_lines.append("  • Better reliability and uptime (OpenAI's infrastructure)")
    report_lines.append("  • No need to manage model updates or GPU drivers")
    report_lines.append("  • Can scale processing speed by choosing faster models")
    report_lines.append("\nCONS:")
    report_lines.append("  • API costs scale with volume")
    report_lines.append("  • Data sent to external API (privacy considerations)")
    report_lines.append("  • Subject to API rate limits and quotas")
    report_lines.append("  • Costs increase linearly with processing volume")
    report_lines.append("  • Fixed daily cost regardless of usage")
    
    # Recommendations
    report_lines.append("\n### RECOMMENDATIONS")
    report_lines.append("\nBased on the analysis:")
    
    if ollama_monthly and best_openai:
        if ollama_monthly["total_cost"] < best_openai["monthly"]["total_cost"]:
            savings_pct = ((best_openai["monthly"]["total_cost"] - ollama_monthly["total_cost"]) / best_openai["monthly"]["total_cost"]) * 100
            report_lines.append(f"  • GPU Server saves ${difference:.2f}/month ({savings_pct:.1f}%) BUT:")
            report_lines.append(f"    - Processing is {ollama_time / best_openai['result']['elapsed_time_seconds']:.1f}x SLOWER")
            report_lines.append(f"    - Quality may be lower (fewer entities/relationships extracted)")
            report_lines.append(f"    - Consider quality vs cost tradeoff")
        else:
            savings_pct = ((ollama_monthly["total_cost"] - best_openai["monthly"]["total_cost"]) / ollama_monthly["total_cost"]) * 100
            report_lines.append(f"  • Non-GPU Server saves ${difference:.2f}/month ({savings_pct:.1f}%) AND:")
            report_lines.append(f"    - Processing is {best_openai['result']['elapsed_time_seconds'] / ollama_time:.1f}x FASTER")
            report_lines.append(f"    - Higher quality extraction")
            report_lines.append(f"    - Better overall value proposition")
    
    report_lines.append(f"\n  • For {documents_per_month} documents/month:")
    if ollama_monthly:
        report_lines.append(f"    - GPU Server: ${ollama_monthly['total_cost']:.2f}/month (${ollama_monthly['cost_per_document']:.4f}/doc)")
    if best_openai:
        report_lines.append(f"    - Non-GPU Server: ${best_openai['monthly']['total_cost']:.2f}/month (${best_openai['monthly']['cost_per_document']:.4f}/doc)")
    
    report_lines.append("\n  • Consider break-even point:")
    # GPU server: Fixed $1,440/month (runs 24/7 at $2/hour)
    # Non-GPU server: Fixed $300/month + variable API costs
    break_even_docs = None
    if ollama_monthly and best_openai:
        gpu_fixed = GPU_SERVER_COST_PER_HOUR * 24 * 30  # $1,440/month
        openai_fixed = NON_GPU_SERVER_COST_PER_DAY * 30  # $300/month
        openai_cost_per_chunk = best_openai["result"]["cost_usd"]
        
        # Calculate where OpenAI total cost equals GPU fixed cost
        # GPU: $1,440 (fixed, runs 24/7)
        # OpenAI: $300 + (docs * chunks * cost_per_chunk)
        # $1,440 = $300 + (docs * chunks * cost_per_chunk)
        # docs * chunks * cost_per_chunk = $1,140
        # docs = $1,140 / (chunks * cost_per_chunk)
        
        if openai_cost_per_chunk > 0:
            break_even_docs = (gpu_fixed - openai_fixed) / (avg_chunks_per_document * openai_cost_per_chunk)
            
            if break_even_docs > 0:
                report_lines.append(f"    - Break-even: ~{break_even_docs:.0f} documents/month")
                report_lines.append(f"      (Above this: GPU server becomes cheaper)")
                report_lines.append(f"      (Below this: Non-GPU server is cheaper)")
                if documents_per_month < break_even_docs:
                    report_lines.append(f"    - At {documents_per_month} docs/month: Non-GPU Server is cheaper")
                elif documents_per_month > break_even_docs:
                    report_lines.append(f"    - At {documents_per_month} docs/month: GPU Server is cheaper")
                else:
                    report_lines.append(f"    - At {documents_per_month} docs/month: Costs are approximately equal")
    
    report_lines.append("\n  • Quality Considerations:")
    if ollama_results["status"] == "success" and best_openai:
        ollama_quality_score = ollama_results["extraction"]["entities_count"] + ollama_results["extraction"]["relationships_count"]
        openai_quality_score = best_openai["result"]["extraction"]["entities_count"] + best_openai["result"]["extraction"]["relationships_count"]
        if openai_quality_score > ollama_quality_score:
            quality_diff = ((openai_quality_score - ollama_quality_score) / ollama_quality_score) * 100
            report_lines.append(f"    - OpenAI extracts {quality_diff:.1f}% more entities/relationships")
            report_lines.append(f"    - Higher quality may justify additional cost")
    
    report_lines.append("\n" + "=" * 100)
    
    return "\n".join(report_lines)


def main():
    """Main execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Compare GPU Server (Ollama) vs Non-GPU Server (OpenAI) costs")
    parser.add_argument("--ollama-model", default=OLLAMA_MODEL, help="Ollama model to test")
    parser.add_argument("--openai-models", nargs="+", default=["gpt-4o-mini", "gpt-4o", "gpt-5.2", "gpt-5-mini", "gpt5-nano", "gpt-5.1", "gpt-4.1"], help="OpenAI models to test")
    parser.add_argument("--skip-ollama", action="store_true", help="Skip Ollama tests (use known GPU server costs)")
    parser.add_argument("--documents", type=int, default=100, help="Documents per month (default: 100)")
    parser.add_argument("--chunks", type=float, default=10.0, help="Average chunks per document (default: 10.0)")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent.parent / "data" / "cost_analysis_report.txt", help="Output report file")
    parser.add_argument("--profile", default="fraud", help="Profile to use")
    
    args = parser.parse_args()
    
    print("\n" + "=" * 100)
    print("SERVER COST ANALYSIS")
    print("=" * 100)
    print(f"Testing GPU Server (Ollama) vs Non-GPU Server (OpenAI)")
    print(f"Documents/month: {args.documents}")
    print(f"Average chunks/document: {args.chunks}")
    print("=" * 100 + "\n")
    
    # Test Ollama (or skip if requested)
    if args.skip_ollama:
        print("Skipping Ollama tests (using known GPU server costs)")
        # Create a mock result with known GPU server performance estimates
        # Typical Ollama on L4: ~30-60 seconds per chunk, lower quality
        ollama_result = {
            "status": "skipped",
            "elapsed_time_seconds": 45.0,  # Estimated: typical Ollama performance on L4
            "extraction": {
                "entities_count": 8,  # Estimated: lower than OpenAI
                "relationships_count": 6,  # Estimated: lower than OpenAI
                "entities": [],
                "relationships": [],
            },
            "error": None,
        }
    else:
        print("Testing Ollama on GPU Server...")
        ollama_result = test_ollama_extraction(FRAUD_CASE_TEXT, args.ollama_model, args.profile)
        if ollama_result["status"] == "success":
            print(f"✓ Ollama: {ollama_result['extraction']['entities_count']} entities, "
                  f"{ollama_result['extraction']['relationships_count']} relationships in {ollama_result['elapsed_time_seconds']:.2f}s")
        else:
            print(f"✗ Ollama: ERROR - {ollama_result.get('error', 'Unknown')}")
    
    # Test OpenAI models
    print(f"\nTesting OpenAI models on Non-GPU Server...")
    openai_results = []
    for model_id in args.openai_models:
        print(f"  Testing {model_id}...")
        result = test_openai_extraction(FRAUD_CASE_TEXT, model_id, args.profile)
        result["model_id"] = model_id
        openai_results.append(result)
        if result["status"] == "success":
            print(f"    ✓ {model_id}: {result['extraction']['entities_count']} entities, "
                  f"{result['extraction']['relationships_count']} relationships in {result['elapsed_time_seconds']:.2f}s "
                  f"(${result['cost_usd']:.6f})")
        else:
            print(f"    ✗ {model_id}: ERROR - {result.get('error', 'Unknown')}")
    
    # Generate text report
    print("\nGenerating text report...")
    report = generate_report(ollama_result, openai_results, args.documents, args.chunks)
    
    # Save text report
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"Text report saved to: {args.output}")
    
    # Generate PDF report
    print("\nGenerating PDF report...")
    try:
        import sys
        scripts_dir = Path(__file__).resolve().parent
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from generate_pdf_report import generate_pdf_report
        
        # Determine best OpenAI result
        best_openai_result = None
        best_cost = float('inf')
        for result in openai_results:
            if result["status"] == "success" and result.get("monthly_cost"):
                if result["monthly_cost"]["total_cost"] < best_cost:
                    best_cost = result["monthly_cost"]["total_cost"]
                    best_openai_result = {"model": result["model_id"], "result": result, "monthly": result["monthly_cost"]}
        
        # Generate PDF
        pdf_output = args.output.parent / (args.output.stem + ".pdf")
        
        # Calculate Ollama monthly if not done
        if ollama_result.get("status") in ["success", "skipped"] and not any(k.startswith("monthly") for k in ollama_result.keys()):
            ollama_time = ollama_result["elapsed_time_seconds"]
            gpu_monthly_server_cost = GPU_SERVER_COST_PER_HOUR * 24 * 30
            total_chunks = args.documents * args.chunks
            ollama_monthly = {
                "documents_per_month": args.documents,
                "total_chunks": total_chunks,
                "total_processing_time_hours": (total_chunks * ollama_time) / 3600,
                "total_processing_time_days": (total_chunks * ollama_time) / 3600 / 24,
                "server_cost": gpu_monthly_server_cost,
                "api_cost": 0.0,
                "total_cost": gpu_monthly_server_cost,
                "cost_per_document": gpu_monthly_server_cost / args.documents if args.documents > 0 else 0,
            }
        else:
            ollama_monthly = None
        
        success = generate_pdf_report(
            ollama_results=ollama_result,
            openai_results=openai_results,
            ollama_monthly=ollama_monthly,
            best_openai=best_openai_result,
            output_path=pdf_output,
            documents_per_month=args.documents,
            avg_chunks_per_document=args.chunks,
            avg_pages_per_document=3.0,  # Fixed: 3 pages per document
        )
        
        if success:
            print(f"✓ PDF report generated: {pdf_output}")
        else:
            print("✗ PDF generation failed (text report still available)")
    except ImportError as e:
        print(f"Warning: Could not generate PDF - {e}")
        print("Install xhtml2pdf: pip install xhtml2pdf")
    except Exception as e:
        print(f"Warning: PDF generation error - {e}")
        print("Text report is still available")
    
    print("\n" + "=" * 100)
    print("REPORT PREVIEW")
    print("=" * 100)
    print(report[:2000] + "\n... (see full report in file)")
    print("=" * 100)


if __name__ == "__main__":
    main()
