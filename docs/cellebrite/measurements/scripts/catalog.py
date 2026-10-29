import sys, json, collections, xml.etree.ElementTree as ET
def s(t): return t.rsplit('}',1)[-1]
src, out = sys.argv[1], sys.argv[2]
f = sys.stdin.buffer if src == "-" else open(src, "rb")
KINDS=("field","multiField","modelField","multiModelField","nodeField","dataField")
cat=collections.defaultdict(lambda: collections.Counter())  # (type,field,kind) -> value types
enums=collections.defaultdict(set); stack=[]; fstack=[]; types=collections.Counter(); err=None
try:
    for ev,el in ET.iterparse(f, events=("start","end")):
        t=s(el.tag)
        if ev=="start":
            if t=="model": stack.append(el.get("type")); types[el.get("type")]+=1
            elif t in KINDS and stack: fstack.append((stack[-1], el.get("name"), t))
            continue
        if t=="value" and fstack:
            vt=el.get("type"); cat[fstack[-1]][vt]+=1
            if vt not in ("String","TimeStamp","Boolean","Int64","Int32","Double","TimeSpan","DecodingSourceOptions") and el.text:
                if len(enums[vt])<50: enums[vt].add(el.text.strip())
        elif t in KINDS and fstack: fstack.pop()
        elif t=="model":
            stack.pop()
            if not stack: el.clear()
except ET.ParseError as e:
    err=str(e)
json.dump({"parse_error":err,"model_types":types,
           "catalog":[[k[0],k[1],k[2],dict(v)] for k,v in cat.items()],
           "enums":{k:sorted(v) for k,v in enums.items()}}, open(out,"w"))
print(f"{src[-40:]}: types={len(types)} combos={len(cat)} enums={len(enums)} parse_error={err}")
