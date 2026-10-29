"""Structure-only file verification measurement. args: root_dir_or_zip::prefix xml..."""
import sys, os, time, hashlib, zipfile, collections as C, xml.etree.ElementTree as ET
def ln(t): return t.rsplit('}',1)[-1]
root=sys.argv[1]; xmls=sys.argv[2:]
Z=None
if '::' in root:
    zp,prefix=root.split('::',1); Z=zipfile.ZipFile(zp); names={i.filename:i for i in Z.infolist()}
def src(s):
    if Z and not os.path.exists(s): return Z.open(s)
    return open(s,'rb')
files=[]; stack=[]
for x in xmls:
  try:
    for ev,el in ET.iterparse(src(x),events=('start','end')):
        t=ln(el.tag)
        if ev=='start': stack.append(t); continue
        stack.pop()
        if t=='file' and stack and stack[-1]=='taggedFiles':
            d={'id':el.get('id'),'size':el.get('size')}
            for m in el.iter():
                if ln(m.tag)=='item' and m.get('name') in('Local Path','MD5','SHA256'): d[m.get('name')]=(m.text or '').strip()
            files.append(d); el.clear()
        elif t=='model': el.clear()
  except ET.ParseError: pass
t0=time.time(); out=C.Counter(); nbytes=0; md5_by_path=C.Counter(); content=C.defaultdict(set); paths=C.Counter(); size_mismatch=0
for d in files:
    lp=d.get('Local Path','').replace('\\','/')
    paths[lp]+=1
    if not lp: out['no local path']+=1; continue
    if Z:
        key=prefix+'/'+lp
        info=names.get(key)
        if info is None: out['missing']+=1; continue
        fh=Z.open(info)
    else:
        p=os.path.join(root,lp)
        if not os.path.isfile(p): out['missing']+=1; continue
        fh=open(p,'rb')
    h5=hashlib.md5(); h2=hashlib.sha256() if d.get('SHA256') else None; n=0
    with fh:
        for ch in iter(lambda: fh.read(1<<20), b''):
            h5.update(ch); n+=len(ch)
            if h2: h2.update(ch)
    nbytes+=n
    if d.get('size') and str(n)!=d['size']: size_mismatch+=1
    md5=d.get('MD5','').lower()
    if not md5: out['no md5']+=1
    elif md5==h5.hexdigest(): out['md5 match']+=1
    else: out['md5 mismatch']+=1
    if h2: out['sha256 '+('match' if d['SHA256'].lower()==h2.hexdigest() else 'mismatch')]+=1
    content[h5.hexdigest()].add(d['id'])
dt=time.time()-t0
print('tagged files',len(files),dict(out),'size_mismatch',size_mismatch)
print('hashed MB',round(nbytes/1e6,1),'seconds',round(dt,1),'MB/s',round(nbytes/1e6/max(dt,.01),1))
print('local paths shared by >1 file id',sum(1 for v in paths.values() if v>1),'contents shared by >1 file id',sum(1 for v in content.values() if len(v)>1),'file ids in shared contents',sum(len(v) for v in content.values() if len(v)>1))
ext=C.Counter(os.path.splitext(d.get('Local Path',''))[1].lower() or '(none)' for d in files); print('local path ext top',ext.most_common(8))
