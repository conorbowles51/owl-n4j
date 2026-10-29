import sys, os, hashlib, collections as C, xml.etree.ElementTree as ET
def ln(t): return t.rsplit('}',1)[-1]
root=sys.argv[1]; files=[]; stack=[]
for x in sys.argv[2:]:
  try:
    for ev,el in ET.iterparse(open(x,'rb'),events=('start','end')):
        t=ln(el.tag)
        if ev=='start': stack.append(t); continue
        stack.pop()
        if t=='file' and stack and stack[-1]=='taggedFiles':
            d={'size':el.get('size'),'embedded':el.get('embedded'),'deleted':el.get('deleted'),'chunks':None}
            for m in el.iter():
                if ln(m.tag)=='item' and m.get('name') in('Local Path','MD5','SHA256','CoreFileSystemFileSystemNodeFileChunks','ReportTemplateFileSize'): d[m.get('name')]=(m.text or '').strip()
            files.append(d); el.clear()
        elif t=='model': el.clear()
  except ET.ParseError: pass
EMPTY=hashlib.md5(b'').hexdigest()
res=C.Counter(); sizes=C.Counter(); emb=C.Counter(); sha_missing=C.Counter()
for d in files:
    lp=d.get('Local Path','').replace('\\','/'); p=os.path.join(root,lp)
    has_sha=bool(d.get('SHA256'))
    if not os.path.isfile(p): sha_missing['missing, sha256 present' if has_sha else 'missing, no sha256']+=1; res[('missing','emb='+str(d['embedded']),'del='+str(d['deleted']))]+=1; continue
    data_size=os.path.getsize(p)
    h=hashlib.md5(open(p,'rb').read()).hexdigest()
    ok=h==d.get('MD5','').lower()
    if not ok:
        sizes['disk0' if data_size==0 else 'disk>0']+=1
        res[('mismatch','emb='+str(d['embedded']),'xmlmd5=empty' if d.get('MD5','').lower()==EMPTY else 'xmlmd5=other', 'ondisk=empty' if h==EMPTY else 'ondisk=nonempty', 'declared0' if d['size']=='0' else 'declared>0', 'sizeeq' if str(data_size)==d['size'] else 'sizediff')]+=1
    else:
        res[('match','emb='+str(d['embedded']))]+=1
for k,v in res.most_common(12): print(v,k)
print(dict(sizes), dict(sha_missing))
