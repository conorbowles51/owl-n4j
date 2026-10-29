# Structure-only: for Party models carrying DateRead/DateDelivered/DatePlayed, count (parent type, Role, IsPhoneOwner, which date fields).
import sys, collections, zipfile, xml.etree.ElementTree as ET
def s(t): return t.rsplit('}',1)[-1]
src=sys.argv[1]; inner=sys.argv[2] if len(sys.argv)>2 else None
f = zipfile.ZipFile(src).open(inner) if inner else open(src,'rb')
stack=[]; cur=[]; fst=[]; C=collections.Counter()
try:
  for ev,el in ET.iterparse(f, events=("start","end")):
    t=s(el.tag)
    if ev=="start":
        if t=="model": stack.append(el.get('type')); cur.append({})
        elif t=="field" and stack: fst.append(el.get('name'))
        continue
    if t=="value" and fst and cur: cur[-1][fst[-1]]=(el.text or '').strip()
    elif t=="field" and fst: fst.pop()
    elif t=="model":
        ty=stack.pop(); d=cur.pop()
        if ty=='Party':
            ds=tuple(k for k in ('DateRead','DateDelivered','DatePlayed') if d.get(k))
            if ds: C[(stack[-1] if stack else None, d.get('Role'), d.get('IsPhoneOwner'), ds)]+=1
        if not stack: el.clear()
except ET.ParseError as e: print('parse_error', e)
for k,v in C.most_common(): print(k,v)
