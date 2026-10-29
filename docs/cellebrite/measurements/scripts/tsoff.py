import sys, re, zipfile, collections as C, xml.etree.ElementTree as ET
def ln(t): return t.rsplit('}',1)[-1]
def src(s):
    if '::' in s: z,e=s.split('::',1); return zipfile.ZipFile(z).open(e)
    return open(s,'rb')
def shape(t): return re.sub(r'[0-9]','d',re.sub(r'[A-Za-z]{3,}','W',t.strip()))[:40]
off=C.Counter(); fshape=C.Counter(); noff=C.Counter(); fileoff=C.Counter(); stack=[]; mt=[]
for s in sys.argv[1:]:
  try:
    for ev,el in ET.iterparse(src(s),events=('start','end')):
        n=ln(el.tag)
        if ev=='start':
            stack.append(n)
            if n=='model': mt.append(el.get('type'))
            if n in('field','multiField'): mt.append('.'+str(el.get('name')))
            continue
        stack.pop()
        if n=='value' and el.get('type')=='TimeStamp':
            t=(el.text or '').strip(); m=re.search(r'([+-]\d\d:\d\d|Z)$',t)
            off[m.group(1) if m else 'none']+=1
            if not m: noff[(mt[-2] if len(mt)>1 else '?')+(mt[-1])]+=1
            fshape[shape(el.get('formattedTimestamp') or '')]+=1
        if n=='timestamp':
            t=(el.text or '').strip(); m=re.search(r'([+-]\d\d:\d\d|Z)$',t); fileoff[m.group(1) if m else 'none']+=1
        if n=='model': mt.pop()
        if n in('field','multiField'): mt.pop()
        if n in ('model','file'): el.clear()
  except ET.ParseError: pass
print('value offsets',off.most_common(6)); print('formatted shapes',fshape.most_common(4)); print('offsetless by type.field',noff.most_common(6)); print('file ts offsets',fileoff.most_common(4))
