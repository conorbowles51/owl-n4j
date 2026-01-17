"""
Test script to compare different OpenAI models for entity extraction.

Tests multiple OpenAI models on a consistent fraud case text chunk and measures:
- Processing time
- Token usage (input/output/total)
- Estimated cost
- Extraction results (entities, relationships, verified facts, AI insights)
"""

import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

# Add parent directory to path for imports
_scripts_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_scripts_dir))

from openai import OpenAI
from config import OPENAI_API_KEY

# Import ingestion modules
import importlib.util
_profile_loader_path = _scripts_dir / "profile_loader.py"
_profile_loader_spec = importlib.util.spec_from_file_location("test_profile_loader", _profile_loader_path)
_profile_loader_module = importlib.util.module_from_spec(_profile_loader_spec)
_profile_loader_spec.loader.exec_module(_profile_loader_module)
get_ingestion_config = _profile_loader_module.get_ingestion_config

# OpenAI pricing per 1M tokens (as of late 2024, update as needed)
# https://openai.com/api/pricing/
# Note: GPT-5 models may use estimated pricing - verify actual pricing when available
PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00},  # $2.50/$10 per 1M tokens
    "gpt-4o-2024-08-06": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},  # $0.15/$0.60 per 1M tokens
    "gpt-4o-mini-2024-07-18": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},  # $10/$30 per 1M tokens
    "gpt-4-turbo-2024-04-09": {"input": 10.00, "output": 30.00},
    "gpt-4.1": {"input": 3.00, "output": 12.00},  # Estimated pricing
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},  # $0.50/$1.50 per 1M tokens
    "gpt-3.5-turbo-0125": {"input": 0.50, "output": 1.50},
    # GPT-5 models (estimated pricing - verify when available)
    "gpt-5": {"input": 3.00, "output": 12.00},  # Estimated
    "gpt-5.1": {"input": 3.00, "output": 12.00},  # Estimated
    "gpt-5.2": {"input": 3.00, "output": 12.00},  # Estimated
    "gpt-5-mini": {"input": 0.20, "output": 0.80},  # Estimated (cheaper variant)
    "gpt5-nano": {"input": 0.10, "output": 0.40},  # Estimated (cheapest variant)
    "o1-preview": {"input": 15.00, "output": 60.00},  # $15/$60 per 1M tokens
    "o1-mini": {"input": 3.00, "output": 12.00},  # $3/$12 per 1M tokens
}

# Recommended models to test (mix of capabilities and cost)
RECOMMENDED_MODELS = [
    "gpt-4o",              # Latest, most capable, good balance
    "gpt-4o-mini",         # Fast and cheap, good for most tasks
    "gpt-4-turbo",         # Previous generation, more expensive
    "gpt-3.5-turbo",       # Cheapest, baseline comparison
]

# Extended models including GPT-5 variants
ALL_MODELS = RECOMMENDED_MODELS + [
    "gpt-5.2",
    "gpt-5-mini",
    "gpt5-nano",
    "gpt-5.1",
    "gpt-4.1",
]

# Default models to test (includes GPT-5 variants)
DEFAULT_MODELS = RECOMMENDED_MODELS + [
    "gpt-5.2",
    "gpt-5-mini",
    "gpt5-nano",
    "gpt-5.1",
    "gpt-4.1",
]

# Default fraud case test text (consistent across all tests)
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


def extract_with_token_tracking(
    text: str,
    model_id: str,
    profile_name: str = "fraud",
    system_context: Optional[str] = None,
    temperature: float = 1.0,
) -> Dict:
    """
    Extract entities and relationships while tracking token usage.
    
    Returns dict with:
    - extraction_result: The normal extraction result
    - token_usage: Dict with prompt_tokens, completion_tokens, total_tokens
    - cost_usd: Estimated cost in USD
    """
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set")
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    # Get profile configuration
    profile = get_ingestion_config(profile_name)
    ingestion_config = profile.get("ingestion", {})
    if system_context is None:
        system_context = ingestion_config.get("system_context", "")
    if temperature is None:
        temperature = ingestion_config.get("temperature", 1.0)
    
    # Build the extraction prompt (mimicking llm_client.py logic)
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
      "date": "string or null (YYYY-MM-DD format)",
      "time": "string or null (HH:MM format)",
      "amount": "string or null (e.g., '$50,000')",
      "location": "string or null",
      "verified_facts": [
        {{
          "text": "Factual statement directly from the document",
          "quote": "Exact quote from the text proving this fact",
          "page": 1,
          "importance": 4
        }}
      ],
      "ai_insights": [
        {{
          "text": "Inference or analysis not directly stated",
          "confidence": "high|medium|low",
          "reasoning": "Why this inference makes sense"
        }}
      ]
    }}
  ],
  "relationships": [
    {{
      "from_key": "string",
      "to_key": "string",
      "type": "string",
      "notes": "string"
    }}
  ]
}}
"""
    
    messages = []
    if system_context:
        messages.append({"role": "system", "content": system_context})
    messages.append({"role": "user", "content": prompt})
    
    # Make API call with token tracking
    response = client.chat.completions.create(
        model=model_id,
        messages=messages,
        temperature=temperature,
        response_format={"type": "json_object"},
        timeout=600,
    )
    
    # Extract response and token usage
    content = response.choices[0].message.content or ""
    usage = response.usage
    
    token_usage = {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }
    
    # Calculate cost
    cost_usd = calculate_cost(model_id, token_usage["prompt_tokens"], token_usage["completion_tokens"])
    
    # Parse JSON response
    try:
        extraction_result = json.loads(content)
    except json.JSONDecodeError as e:
        extraction_result = {"error": str(e), "raw_response": content[:500]}
    
    return {
        "extraction_result": extraction_result,
        "token_usage": token_usage,
        "cost_usd": cost_usd,
    }


def calculate_cost(model_id: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate estimated cost in USD based on token usage."""
    # Find pricing (try exact match, then try prefix match)
    pricing = PRICING.get(model_id)
    if not pricing:
        # Try prefix match (e.g., "gpt-4o-2024-08-06" -> "gpt-4o")
        for key in PRICING.keys():
            if model_id.startswith(key.split("-")[0] + "-" + key.split("-")[1]):
                pricing = PRICING[key]
                break
    
    if not pricing:
        # Default to gpt-4o pricing if unknown
        pricing = PRICING["gpt-4o"]
        print(f"Warning: Unknown model {model_id}, using gpt-4o pricing")
    
    input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output"]
    
    return input_cost + output_cost


def test_model(
    model_id: str,
    test_text: str,
    profile_name: str = "fraud",
) -> Dict:
    """
    Test a single model and return results with metrics.
    
    Returns:
        Dict with model_id, timing, token_usage, cost, and extraction results
    """
    print(f"\n{'='*80}")
    print(f"Testing model: {model_id}")
    print(f"{'='*80}")
    
    start_time = time.time()
    
    try:
        result = extract_with_token_tracking(
            text=test_text,
            model_id=model_id,
            profile_name=profile_name,
        )
        
        elapsed_time = time.time() - start_time
        
        extraction = result["extraction_result"]
        
        # Count extracted items
        entities = extraction.get("entities", []) if "error" not in extraction else []
        relationships = extraction.get("relationships", []) if "error" not in extraction else []
        
        total_verified_facts = sum(
            len(e.get("verified_facts", [])) for e in entities
        )
        total_ai_insights = sum(
            len(e.get("ai_insights", [])) for e in entities
        )
        
        return {
            "model_id": model_id,
            "status": "success",
            "elapsed_time_seconds": elapsed_time,
            "token_usage": result["token_usage"],
            "cost_usd": result["cost_usd"],
            "extraction": {
                "entities_count": len(entities),
                "relationships_count": len(relationships),
                "total_verified_facts": total_verified_facts,
                "total_ai_insights": total_ai_insights,
                "entities": entities,
                "relationships": relationships,
            },
            "error": None,
        }
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        return {
            "model_id": model_id,
            "status": "error",
            "elapsed_time_seconds": elapsed_time,
            "token_usage": None,
            "cost_usd": None,
            "extraction": None,
            "error": str(e),
        }


def print_results_summary(results: List[Dict]):
    """Print a formatted summary of all test results."""
    print(f"\n{'='*80}")
    print("TEST RESULTS SUMMARY")
    print(f"{'='*80}\n")
    
    # Header
    print(f"{'Model':<25} {'Time (s)':<12} {'Input Tokens':<15} {'Output Tokens':<15} {'Total Tokens':<15} {'Cost (USD)':<12} {'Status':<10}")
    print("-" * 110)
    
    for result in results:
        model = result["model_id"]
        time_sec = f"{result['elapsed_time_seconds']:.2f}" if result["status"] == "success" else "N/A"
        
        if result["status"] == "success":
            tokens = result["token_usage"]
            input_tok = f"{tokens['prompt_tokens']:,}"
            output_tok = f"{tokens['completion_tokens']:,}" if 'completion_tokens' in tokens else "0"
            total_tok = f"{tokens['total_tokens']:,}"
            cost = f"${result['cost_usd']:.6f}"
            status = "✓ Success"
            
            extraction = result.get("extraction", {})
            if extraction:
                print(f"{model:<25} {time_sec:<12} {input_tok:<15} {output_tok:<15} {total_tok:<15} {cost:<12} {status:<10}")
                print(f"  → Entities: {extraction.get('entities_count', 0)}, "
                      f"Relationships: {extraction.get('relationships_count', 0)}, "
                      f"Verified Facts: {extraction.get('total_verified_facts', 0)}, "
                      f"AI Insights: {extraction.get('total_ai_insights', 0)}")
        else:
            print(f"{model:<25} {time_sec:<12} {'N/A':<15} {'N/A':<15} {'N/A':<15} {'N/A':<12} {'✗ Error':<10}")
            print(f"  → Error: {result.get('error', 'Unknown error')}")


def save_detailed_results(results: List[Dict], output_file: Path):
    """Save detailed results to JSON file."""
    output_data = {
        "test_date": datetime.now().isoformat(),
        "test_text_length": len(FRAUD_CASE_TEXT),
        "test_text_preview": FRAUD_CASE_TEXT[:500] + "...",
        "results": results,
    }
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\nDetailed results saved to: {output_file}")


def main():
    """Main test execution."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Test different OpenAI models for entity extraction"
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_MODELS,
        help=f"List of models to test (default: {DEFAULT_MODELS})",
    )
    parser.add_argument(
        "--text-file",
        type=Path,
        help="Path to custom test text file (default: uses built-in fraud case text)",
    )
    parser.add_argument(
        "--profile",
        default="fraud",
        help="Profile name to use (default: fraud)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent.parent / "data" / "model_test_results.json",
        help="Output file for detailed results (default: data/model_test_results.json)",
    )
    
    args = parser.parse_args()
    
    # Load test text
    if args.text_file:
        if not args.text_file.exists():
            print(f"Error: Text file not found: {args.text_file}")
            sys.exit(1)
        with open(args.text_file, "r", encoding="utf-8") as f:
            test_text = f.read()
    else:
        test_text = FRAUD_CASE_TEXT
    
    print(f"\n{'='*80}")
    print("OpenAI Model Comparison Test")
    print(f"{'='*80}")
    print(f"Test text length: {len(test_text)} characters")
    print(f"Models to test: {', '.join(args.models)}")
    print(f"Profile: {args.profile}")
    print(f"{'='*80}\n")
    
    # Run tests
    results = []
    for model_id in args.models:
        result = test_model(model_id, test_text, args.profile)
        results.append(result)
        
        # Brief status
        if result["status"] == "success":
            ext = result["extraction"]
            print(f"✓ {model_id}: {ext['entities_count']} entities, "
                  f"{ext['relationships_count']} relationships in {result['elapsed_time_seconds']:.2f}s "
                  f"(${result['cost_usd']:.6f})")
        else:
            print(f"✗ {model_id}: ERROR - {result.get('error', 'Unknown')}")
    
    # Print summary
    print_results_summary(results)
    
    # Save detailed results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_detailed_results(results, args.output)
    
    # Print recommendations
    print(f"\n{'='*80}")
    print("RECOMMENDATIONS")
    print(f"{'='*80}")
    
    successful_results = [r for r in results if r["status"] == "success"]
    
    if successful_results:
        fastest = min(successful_results, key=lambda x: x["elapsed_time_seconds"])
        cheapest = min(successful_results, key=lambda x: x["cost_usd"])
        most_entities = max(successful_results, key=lambda x: x["extraction"]["entities_count"])
        
        print(f"\nFastest: {fastest['model_id']} ({fastest['elapsed_time_seconds']:.2f}s)")
        print(f"Cheapest: {cheapest['model_id']} (${cheapest['cost_usd']:.6f})")
        print(f"Most entities extracted: {most_entities['model_id']} ({most_entities['extraction']['entities_count']} entities)")
        print(f"\nNote: Compare the actual extraction quality in the detailed results file.")
    
    print()


if __name__ == "__main__":
    main()
