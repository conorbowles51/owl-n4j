"""One explicit, bounded external provider check using synthetic text only.

Reads the configured OpenAI key/model without printing them. Never loads case
records, original PDFs or real database settings. No automatic retry.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[1]
values=dotenv_values(root/'.env')
key=values.get('OPENAI_API_KEY');model=values.get('OPENAI_MODEL')
if not key or not model:raise SystemExit('Existing OpenAI key and model configuration required.')
# Prevent engine settings from automatically loading the installation .env.
os.chdir('/tmp')
os.environ['OPENAI_API_KEY']=key
os.environ['PYTHON_DOTENV_DISABLED']='1'
sys.path.insert(0,str(root/'evidence-engine'))
from app.services import openai_client
from openai import AsyncOpenAI
client=AsyncOpenAI(api_key=key,base_url='https://api.openai.com/v1',max_retries=0,timeout=45)
openai_client._client=client
openai_client._client_key=key
schema={'type':'object','properties':{'date_text':{'type':'string'},'amount_text':{'type':'string'},'direction_text':{'type':'string'}},'required':['date_text','amount_text','direction_text'],'additionalProperties':False}
async def main():
 report={'checked_at':datetime.now(timezone.utc).isoformat(),'provider':'openai','model':model,'synthetic_only':True,'max_output_tokens':512,'automatic_retries':0,'financial_writes':0,'scope':'Provider adapter structured extraction only; not the full document pipeline.'}
 try:
  content,usage=await openai_client._openai_chat_completion(
   [{'role':'system','content':'Copy the exact date, amount and direction strings from this synthetic statement row into the required JSON. Do not calculate or normalise them.'},{'role':'user','content':'SYNTHETIC TEST ONLY. Date: 2026-01-02; Amount: GBP 12.34; Direction: money out.'}],
   model=model,response_format={'type':'json_schema','json_schema':{'name':'synthetic_financial_reading','strict':True,'schema':schema}},temperature=None,max_output_tokens=512)
  actual=json.loads(content)
  if actual!={'date_text':'2026-01-02','amount_text':'GBP 12.34','direction_text':'money out'}:raise ValueError('Synthetic reading differs from exact supplied text')
  report.update(passed=True,exact_synthetic_reading=True,usage={name:getattr(usage,name,None) for name in ('prompt_tokens','completion_tokens','total_tokens')})
 except Exception as exc:
  report.update(passed=False,error_type=type(exc).__name__,http_status=getattr(exc,'status_code',None))
 finally:
  await client.close()
 (root/'data/local-runtime/synthetic-financial-provider-check.json').write_text(json.dumps(report,indent=2))
 print(json.dumps(report))
 if not report['passed']:raise SystemExit(1)
asyncio.run(main())
