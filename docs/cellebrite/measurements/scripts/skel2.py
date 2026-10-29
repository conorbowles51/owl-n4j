import sys, zipfile, collections as C, xml.etree.ElementTree as ET
def ln(t): return t.rsplit('}',1)[-1]
def src(s):
    if '::' in s: z,e=s.split('::',1); return zipfile.ZipFile(z).open(e)
    return open(s,'rb')
seen=C.OrderedDict(); stack=[]
for s in sys.argv[1:]:
  try:
    for ev,el in ET.iterparse(src(s),events=('start','end')):
        n=ln(el.tag)
        if ev=='start':
            stack.append(n)
            if 'decodedData' in stack[:-1] or ('taggedFiles' in stack[:-1]): continue
            p='/'.join(stack); a=tuple(sorted(ln(k) for k in el.attrib))
            if n=='item' or n=='metadata': a=a+((el.get('name') or el.get('section') or '') if n!='item' or 'metadata' in stack else '',)
            seen.setdefault((p,a),0); seen[(p,a)]+=1
        else:
            stack.pop(); el.clear()
  except ET.ParseError as e: print('ERR',e)
for (p,a),c in seen.items(): print(c,p,a)
