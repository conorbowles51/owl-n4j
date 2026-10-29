import sys, zipfile, collections as C, xml.etree.ElementTree as ET
def ln(t): return t.rsplit('}',1)[-1]
def src(s):
    if '::' in s: z,e=s.split('::',1); return zipfile.ZipFile(z).open(e)
    return open(s,'rb')
ids=C.Counter(); noid=0; depthkind=C.Counter(); stack=[]; fids=C.Counter(); jt_model=0; jt_file=0; jt_other=C.Counter()
types_of=C.defaultdict(set)
for s in sys.argv[1:]:
  try:
    for ev,el in ET.iterparse(src(s),events=('start','end')):
        n=ln(el.tag)
        if ev=='start':
            par=stack[-1] if stack else None; stack.append(n)
            if n=='model':
                i=el.get('id')
                if i is None: noid+=1
                else: ids[i]+=1; types_of[i].add((el.get('type'), 'top' if par=='modelType' else 'nested'))
            if n=='file' and par=='taggedFiles': fids[el.get('id')]+=1
            if n=='targetid': jt_other[el.get('ismodel')]+=1
        else:
            stack.pop(); el.clear()
  except ET.ParseError: pass
d={k:v for k,v in ids.items() if v>1}
print('models no id',noid,'distinct ids',len(ids),'ids repeated',len(d),'extra occurrences',sum(v-1 for v in d.values()))
pat=C.Counter(tuple(sorted(types_of[k])) for k in d); print('repeat patterns',pat.most_common(5))
print('file ids repeated',sum(1 for v in fids.values() if v>1),'files',sum(fids.values()))
print('targetid ismodel',dict(jt_other))
