# Structure-only: (parent type, container field name, child type) counts for nested models.
import sys, collections, zipfile, xml.etree.ElementTree as ET
def s(t): return t.rsplit('}',1)[-1]
src=sys.argv[1]; inner=sys.argv[2] if len(sys.argv)>2 else None
f = zipfile.ZipFile(src).open(inner) if inner else open(src,'rb')
st=[]; C=collections.Counter()
try:
  for ev,el in ET.iterparse(f, events=("start","end")):
    t=s(el.tag)
    if ev=="start":
        if t in ("modelField","multiModelField"): st.append(('F',el.get('name')))
        elif t=="model":
            ptype=next((x[1] for x in reversed(st) if x[0]=='M'),None); pf=st[-1][1] if st and st[-1][0]=='F' else None
            if ptype: C[(ptype,pf,el.get('type'))]+=1
            st.append(('M',el.get('type')))
        continue
    if t in ("modelField","multiModelField","model"):
        st.pop()
        if t=="model" and not any(x[0]=='M' for x in st): el.clear()
except ET.ParseError as e: print('parse_error',e)
for k,v in sorted(C.items()): print(k,v)
