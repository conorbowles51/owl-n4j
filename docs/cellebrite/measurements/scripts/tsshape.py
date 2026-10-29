import sys, re, zipfile, collections as C, xml.etree.ElementTree as ET
def ln(t): return t.rsplit('}',1)[-1]
def src(s):
    if '::' in s: z,e=s.split('::',1); return zipfile.ZipFile(z).open(e)
    return open(s,'rb')
def shape(t): return re.sub(r'[0-9]','d',re.sub(r'[A-Za-z]{3,}','W',t.strip()))[:40]
vs=C.Counter(); fa=C.Counter(); acc=C.Counter(); accattr=C.Counter(); eq=C.Counter(); meta=C.Counter(); stack=[]
for s in sys.argv[1:]:
  try:
    for ev,el in ET.iterparse(src(s),events=('start','end')):
        n=ln(el.tag)
        if ev=='start': stack.append(n); continue
        stack.pop()
        if n=='value' and el.get('type')=='TimeStamp':
            t=el.text or ''; vs[shape(t)]+=1
            f=el.get('formattedTimestamp'); fa['has formattedTimestamp' if f is not None else 'no attr']+=1
            if f is not None: eq['text==formatted' if f.strip()==t.strip() else 'differs']+=1
        if n=='timestamp':
            acc[shape(el.text or '')]+=1; accattr[tuple(sorted(ln(k) for k in el.attrib))]+=1
        if n=='item' and 'metadata' in stack and re.search(r'Date|Time',el.get('name') or ''):
            meta[(el.get('name'), shape(el.text or ''))]+=1
        if n in ('model','file','metadata'): el.clear()
  except ET.ParseError: pass
print('TimeStamp value shapes',vs.most_common(8)); print(dict(fa), dict(eq))
print('file timestamp shapes',acc.most_common(6)); print('file timestamp attrs',accattr.most_common(4))
print('metadata dates',meta.most_common(12))
