import sys, collections, xml.etree.ElementTree as ET
def ln(t): return t.rsplit('}',1)[-1]
C=collections.Counter(); S=collections.Counter(); n=0
try:
  for ev,el in ET.iterparse(sys.argv[1], events=('end',)):
    if ln(el.tag)=='file':
        n+=1
        for md in el.iter():
            if ln(md.tag)=='metadata':
                for it in md:
                    if ln(it.tag)=='item' and (it.text or '').strip(): C[(md.get('section'), it.get('name'))]+=1
        el.clear()
except ET.ParseError: pass
print(n); [print(k,v) for k,v in C.most_common(60)]
