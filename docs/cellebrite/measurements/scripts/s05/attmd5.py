import sys, zipfile, pickle, collections, xml.etree.ElementTree as ET, itertools
def ln(t): return t.rsplit('}',1)[-1]
O='<REPO>'
def src(spec):
    if '::' in spec: z,m=spec.split('::'); return zipfile.ZipFile(z).open(m)
    return open(spec,'rb')
def it(f):
    try: yield from ET.iterparse(f, events=('start','end'))
    except ET.ParseError: pass
def run(tagged, model):
    byid={}; bypath={}
    for ev,el in it(src(tagged)):
        if ev=='end' and ln(el.tag)=='file':
            md5=None; lp=None
            for x in el.iter():
                if ln(x.tag)=='item':
                    if x.get('name')=='MD5': md5=(x.text or '').strip().lower()
                    if x.get('name')=='Local Path': lp=(x.text or '').strip().replace('\\','/').lower()
            if md5: byid[el.get('id')]=md5; 
            if md5 and lp: bypath[lp]=md5
            el.clear()
    out=set(); C=collections.Counter(); stack=[]; fld=[]
    for ev,el in it(src(model)):
        t=ln(el.tag)
        if ev=='start':
            if t=='model': stack.append([el.get('type'), el.get('file_id'), set(), None])
            elif t=='field': fld.append(el.get('name'))
            continue
        if t=='field' and fld: fld.pop()
        elif t=='value' and stack and fld and fld[-1]=='attachment_extracted_path' and el.text: stack[-1][3]=el.text.strip().replace('\\','/').lower()
        elif t=='targetid' and stack and el.get('ismodel')=='false': stack[-1][2].add((el.text or '').strip())
        elif t=='model':
            ty,fid,jts,p=stack.pop()
            if ty=='Attachment':
                C['att']+=1; got=None
                if fid and fid in byid: got=byid[fid]; C['via_file_id']+=1
                elif p and p in bypath: got=bypath[p]; C['via_path']+=1
                else:
                    for j in jts:
                        if j in byid: got=byid[j]; C['via_jt']+=1; break
                if got: out.add(got)
                else: C['unresolved']+=1
            if not stack: el.clear()
    return out, C
specs={'A-C3':(O+'/Cellebrite Report Sample Phone/<C3_REPORT_PATH>',)*2,
 'A-C9':((O+'/C9.zip::<C9_REPORT_PATH>',)*2),
 'A-C8':(O+'/Cellebrite C8/<C8_REPORT_PATH>',O+'/Cellebrite C8/<C8_REPORT_PATH>')}
R={}
for l,(a,b) in specs.items():
    R[l],C=run(a,b); print(l,dict(C),'distinct md5',len(R[l]))
for a,b in itertools.combinations(R,2): print(a,b,'shared attachment md5',len(R[a]&R[b]))
