import sys, zipfile, collections as C, xml.etree.ElementTree as ET
def ln(t): return t.rsplit('}',1)[-1]
def src(s):
    if '::' in s: z,e=s.split('::',1); return zipfile.ZipFile(z).open(e)
    return open(s,'rb')
shape=C.Counter(); stack=[]; n=0
for ev,el in ET.iterparse(src(sys.argv[1]),events=('start','end')):
    t=ln(el.tag)
    if ev=='start':
        stack.append(t); continue
    if t=='file' and stack[-2:-1]==['taggedFiles']:
        def walk(e,p):
            for c in e:
                k=ln(c.tag); key=p+'/'+k+('['+(c.get('name') or c.get('section') or '')+']' if k in('item','metadata','timestamp') else '')
                shape[(key, tuple(sorted(ln(a) for a in c.attrib)))]+=1; walk(c,key)
        shape[('file',tuple(sorted(ln(a) for a in el.attrib)))]+=1
        walk(el,'file'); n+=1
        el.clear()
    elif t=='model': el.clear()
    stack.pop()
for (k,a),c in sorted(shape.items(), key=lambda x:-x[1])[:45]: print(c,k,a)
