# Structure-level measurement. Prints counts only. Stores salted hashes for cross-phone comparison.
import sys, re, json, hashlib, zipfile, collections, unicodedata, pickle, os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
SALT=os.environ.get('SALT','x').encode()
def h(s): return hashlib.sha256(SALT+s.encode('utf-8')).hexdigest()[:20]
def ln(t): return t.rsplit('}',1)[-1]
label, src = sys.argv[1], sys.argv[2]; member = sys.argv[3] if len(sys.argv)>3 else None
f = zipfile.ZipFile(src).open(member) if member else open(src,'rb')
AMT=re.compile(r'(?:[$€£]\s?\d[\d,]*(?:\.\d{2})?|\b\d[\d,]*\.\d{2}\b|\b(?:usd|mxn|eur|dollars?|pesos?)\b)', re.I)
FIN=re.compile(r'bank|banco|pay|cash|wallet|venmo|zelle|paypal|coinbase|binance|crypto|credit|card|chase|wellsfargo|capitalone|citi|bbva|santander|western ?union|moneygram|remit|loan|finance|invest|trading|exchange|bitcoin|btc|usdt|sofi|chime|cashapp|square', re.I)
def norm_body(b):
    b=unicodedata.normalize('NFKC',b).casefold(); return re.sub(r'\s+',' ',b).strip()
def norm_id(s):
    s=(s or '').strip(); d=re.sub(r'\D','',s.split('@')[0])
    if d and len(d)>=7 and len(re.sub(r'[\d+\-\s().]','',s.split('@')[0]))==0: return 'n:'+d[-10:]
    return 's:'+s.casefold()
def ts(v):
    if not v: return None
    v=v.strip().replace('Z','+00:00')
    try: d=datetime.fromisoformat(v)
    except Exception: return None
    return d.timestamp() if d.tzinfo else ('naive', d.timestamp())
C=collections.Counter(); D=collections.defaultdict(collections.Counter)
msgs=[]; owner=set(); parties_seen=set(); md5s={}
stack=[]  # list of dicts per open model
def fieldvals(m, name): return m['f'].get(name, [])
cur_field=[]
def safe(it):
    try:
        yield from it
    except ET.ParseError as e:
        C['parse_stopped']+=1
for ev, el in safe(ET.iterparse(f, events=('start','end'))):
    t=ln(el.tag)
    if ev=='start':
        if t=='model': stack.append(dict(type=el.get('type'), id=el.get('id'), ds=el.get('deleted_state'), f=collections.defaultdict(list), sub=collections.defaultdict(list), parent_field=cur_field[-1] if cur_field else None))
        elif t in ('field','multiField','modelField','multiModelField'): cur_field.append(el.get('name'))
        continue
    if t=='value' and stack and cur_field:
        stack[-1]['f'][cur_field[-1]].append(el.text or '')
    elif t in ('field','multiField','modelField','multiModelField'):
        if cur_field: cur_field.pop()
    elif t=='file' :
        md5=None; tag=None
        for it in el.iter():
            if ln(it.tag)=='item':
                n=it.get('name')
                if n=='MD5': md5=(it.text or '').strip().lower()
                if n=='Tags': tag=(it.text or '').strip()
        if md5: md5s[md5]=tag
        el.clear()
    elif t=='model':
        m=stack.pop(); ty=m['type']; F=m['f']
        if stack: stack[-1]['sub'][m['parent_field']].append(m)
        if ty=='Party':
            ident=(F.get('Identifier') or [''])[0]
            if ident:
                parties_seen.add(h(norm_id(ident)))
                if (F.get('IsPhoneOwner') or [''])[0].lower()=='true': owner.add(h(norm_id(ident)))
        elif ty=='InstantMessage':
            C['im']+=1; body=(F.get('Body') or [''])[0]; src_=(F.get('Source') or [''])[0]; typ=(F.get('Type') or [''])[0]
            D['im_type'][typ]+=1; D['im_deleted'][m['ds']]+=1
            frm=m['sub'].get('From',[]); to=m['sub'].get('To',[])
            fid=(frm[0]['f'].get('Identifier') or [''])[0] if frm else ''
            fown=(frm[0]['f'].get('IsPhoneOwner') or [''])[0].lower()=='true' if frm else False
            smsc=(F.get('SMSC') or [''])[0]
            if smsc: C['smsc_present']+=1; D['smsc_distinct'][h(smsc)]+=1;
            if smsc and fid and norm_id(smsc)==norm_id(fid): C['smsc_equals_from']+=1
            sc = bool(re.fullmatch(r'\d{3,6}', fid.strip())) if fid else False
            if sc: C['from_shortcode']+=1; D['shortcode_src'][typ]+=1
            if body and AMT.search(body):
                C['im_amount']+=1
                if sc: C['shortcode_amount']+=1
            sd=(F.get('SelfDestructDuration') or [''])[0]
            if sd: D['selfdestruct'][('zero' if re.fullmatch(r'[0:.\s]*|P?T?0+S?',sd) else 'nonzero')]+=1
            for lab in F.get('Label',[]): D['im_label'][lab]+=1
            for r in F.get('DeletionReason',[]): D['delreason'][r]+=1
            att=sum(len(x) for k,x in m['sub'].items() if k in ('Attachment','Attachments'))
            to_ids=[(x['f'].get('Identifier') or [''])[0] for x in to]
            msgs.append(dict(body=h(norm_body(body)) if body and len(norm_body(body))>=1 else None, blen=len(norm_body(body)) if body else 0,
                t=ts((F.get('TimeStamp') or [''])[0]), frm=h(norm_id(fid)) if fid else None, fown=fown, to=[h(norm_id(x)) for x in to_ids if x],
                ds=m['ds'], src=src_, typ=typ, att=att, ntop=len(to)))
            if (F.get('TimeStamp') or [''])[0] and isinstance(msgs[-1]['t'],tuple): C['im_naive_ts']+=1
        elif ty=='Email':
            C['email']+=1; b=' '.join(F.get('Body',[])+F.get('Subject',[]))
            if AMT.search(b): C['email_amount']+=1
        elif ty=='InstalledApplication':
            for c in F.get('Categories',[]): D['app_cat'][c]+=1
            C['apps']+=1
        elif ty=='Cookie':
            C['cookie']+=1
            if FIN.search((F.get('Domain') or [''])[0]): C['cookie_fin']+=1; D['cookie_fin_dom'][h((F.get('Domain') or [''])[0].lstrip('.').casefold())]+=1
        elif ty=='VisitedPage':
            C['visited']+=1
            u=(F.get('Url') or [''])[0]; host=re.sub(r'^[a-z]+://','',u.casefold()).split('/')[0]
            if FIN.search(host): C['visited_fin']+=1; D['visited_fin_host'][h(host)]+=1
        elif ty=='Password':
            C['password']+=1; s=' '.join(F.get('Service',[])+F.get('Account',[])[:0])
            if FIN.search(s): C['password_fin']+=1
        elif ty=='UserAccount':
            C['useraccount']+=1
            if FIN.search(' '.join(F.get('ServiceType',[])+F.get('Source',[]))): C['useraccount_fin']+=1
        elif ty=='DictionaryWord':
            C['dictword']+=1; w=(F.get('Word') or [''])[0]
            if re.search(r'\d',w): C['dictword_digit']+=1
        elif ty=='Autofill':
            C['autofill']+=1
        if not stack: el.clear()
# shortcodes distinct
out=dict(label=label, counts=C, dists={k:dict(v) if k not in ('smsc_distinct','cookie_fin_dom','visited_fin_host') else len(v) for k,v in D.items()}, owners=len(owner), md5=len(md5s))
print(json.dumps(out, default=str))
pickle.dump(dict(msgs=msgs, owner=owner, parties=parties_seen, md5s=md5s), open(f'{os.path.dirname(__file__)}/out/{label}.pkl','wb'))
