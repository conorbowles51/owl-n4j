import sys, os, hashlib, collections as C, xml.etree.ElementTree as ET
def ln(t): return t.rsplit('}',1)[-1]
root=sys.argv[1]; stack=[]; out=C.Counter()
try:
  for ev,el in ET.iterparse(open(sys.argv[2],'rb'),events=('start','end')):
    t=ln(el.tag)
    if ev=='start': stack.append(t); continue
    stack.pop()
    if t=='file' and stack and stack[-1]=='taggedFiles':
        d={}
        for m in el.iter():
            if ln(m.tag)=='item' and m.get('name') in('Local Path','MD5','Tags'): d[m.get('name')]=(m.text or '').strip()
        p=os.path.join(root,d.get('Local Path','').replace('\\','/'))
        if os.path.isfile(p) and os.path.getsize(p)==0 and hashlib.md5(open(p,'rb').read()).hexdigest()!=d.get('MD5','').lower():
            out[(os.path.splitext(p)[1].lower(), d.get('Tags'), 'sizeeq' if str(os.path.getsize(p))==el.get('size') else 'sizediff')]+=1
        el.clear()
except ET.ParseError: pass
print(out.most_common(10))
