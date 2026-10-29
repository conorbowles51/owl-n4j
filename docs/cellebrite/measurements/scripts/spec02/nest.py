import sys, json, collections, xml.etree.ElementTree as ET, zipfile
def s(t): return t.rsplit('}',1)[-1]
src=sys.argv[1]
if src.endswith('.zip'):
    z=zipfile.ZipFile(src); n=[i for i in z.namelist() if i.endswith('.xml') and '__MACOSX' not in i and z.getinfo(i).file_size>1e6][0]; f=z.open(n)
else: f=open(src,'rb')
KINDS=("field","multiField","modelField","multiModelField","nodeField","dataField")
nest=collections.Counter(); usermap=collections.Counter(); role=collections.Counter(); owner=collections.Counter()
tsattrs=collections.Counter(); tsfmt=collections.Counter(); identshape=collections.Counter(); confs=collections.Counter()
mstack=[]; fstack=[]; partyctx=[]
import re
def shape(v):
    if v is None: return 'none'
    v=v.strip()
    if re.fullmatch(r'\+?[\d\s\-\(\)\.]{5,}',v): return 'phone-like'
    if '@s.whatsapp.net' in v: return 'wa-jid'
    if '@g.us' in v: return 'wa-group'
    if re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',v): return 'email-like'
    if re.fullmatch(r'\d+',v): return 'digits'
    return 'other'
try:
  for ev,el in ET.iterparse(f, events=("start","end")):
    t=s(el.tag)
    if ev=="start":
        if t=="model":
            ty=el.get("type"); confs[el.get('decoding_confidence')]+=1
            if fstack and mstack: nest[(mstack[-1], fstack[-1][1], fstack[-1][0], ty)]+=1
            mstack.append(ty)
        elif t in KINDS and mstack: fstack.append((t, el.get("name")))
        continue
    if t=="value" and fstack and mstack:
        vt=el.get('type'); fn=fstack[-1][1]
        if vt=='DecodingSourceOptions': usermap[(el.text or '').strip()]+=1
        if vt=='TimeStamp':
            tsattrs[tuple(sorted(el.attrib))]+=1
            tx=(el.text or '').strip(); tsfmt[re.sub(r'\d','9',tx)]+=1
        if mstack[-1]=='Party' and fn=='Role': role[(el.text or '').strip()]+=1
        if mstack[-1]=='Party' and fn=='IsPhoneOwner': owner[(el.text or '').strip()]+=1
        if mstack[-1]=='Party' and fn=='Identifier': identshape[shape(el.text)]+=1
        if mstack[-1] in ('PhoneNumber','UserID','EmailAddress') and fn=='Value': identshape[mstack[-1]+':'+shape(el.text)]+=1
    elif t in KINDS and fstack and mstack: fstack.pop()
    elif t=="model":
        mstack.pop()
        if not mstack: el.clear()
except ET.ParseError as e: print('parse error',e)
print('NEST'); [print(' ',k,v) for k,v in sorted(nest.items())]
print('USERMAP',usermap); print('ROLE',role); print('OWNER',owner); print('TSATTRS',tsattrs)
print('TSFMT',tsfmt.most_common(10)); print('IDSHAPE',identshape); print('CONF',confs)
