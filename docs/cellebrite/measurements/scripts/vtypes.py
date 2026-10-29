import sys, collections, xml.etree.ElementTree as ET
def s(t): return t.rsplit('}',1)[-1]
vt=collections.Counter(); pairs=set(); kinds=collections.Counter(); stack=[]
for ev,el in ET.iterparse(sys.argv[1], events=("start","end")):
    t=s(el.tag)
    if ev=="start":
        if t=="model": stack.append(el.get("type"))
        elif t in ("field","multiField","modelField","multiModelField","nodeField","dataField") and stack:
            pairs.add((stack[-1], el.get("name"), t))
        continue
    if t=="value": vt[el.get("type")]+=1
    if t=="model":
        stack.pop()
        if not stack: el.clear()
print("value data types:", dict(vt.most_common()))
print("distinct (record type, field name, field kind):", len(pairs))
print("distinct record types with fields:", len({p[0] for p in pairs}))
