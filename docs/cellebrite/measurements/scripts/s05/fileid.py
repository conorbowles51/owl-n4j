import sys, collections, xml.etree.ElementTree as ET
def s(t): return t.rsplit('}',1)[-1]
tagged, model = sys.argv[1], sys.argv[2]
ftag={}; ext=collections.Counter()
try:
    for ev,el in ET.iterparse(tagged, events=("end",)):
        if s(el.tag)=="file":
            fid=el.get("id"); tg=None
            for it in el.iter():
                if s(it.tag)=="item" and it.get("name")=="Tags": tg=(it.text or '').strip()
            ftag[fid]=tg or 'NONE'
            if tg=='Database':
                n=el.get('name') or ''; ext[n.rsplit('.',1)[-1].lower() if '.' in n else '(none)']+=1
            el.clear()
except ET.ParseError as e: print("tagged parse stop:", str(e)[:60])
print("files indexed", len(ftag), collections.Counter(ftag.values()))
print("Database ext", ext.most_common(8))
depth=0; total=0; jt=collections.Counter(); per=collections.Counter(); inmodel=None
for ev,el in ET.iterparse(model, events=("start","end")):
    t=s(el.tag)
    if t=="model":
        if ev=="start":
            depth+=1
            if depth==1: total+=1; inmodel=el.get('type'); seen=set()
        else:
            depth-=1
            if depth==0:
                per[(inmodel, 'has_db_src' if 'Database' in seen else ('has_other_src' if seen-{'UNRESOLVED'} else ('unresolved' if seen else 'no_jt')))]+=1
                el.clear()
    elif t=="targetid" and ev=="end" and depth>=1 and el.get('ismodel')=='false':
        tg=ftag.get((el.text or '').strip(),'UNRESOLVED'); jt[tg]+=1; seen.add(tg)
print("top models", total, "file jumptargets by tag", dict(jt))
agg=collections.Counter()
for (ty,k),n in per.items(): agg[k]+=n
print(dict(agg))
for k,v in sorted(per.items(), key=lambda x:-x[1])[:30]: print(k,v)
