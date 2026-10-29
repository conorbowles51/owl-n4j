import sys, zipfile, collections, hashlib, itertools, os, xml.etree.ElementTree as ET
SALT=open('s05/salt').read().strip().encode()
def h(s): return hashlib.sha256(SALT+s.encode()).hexdigest()[:20]
def ln(t): return t.rsplit('}',1)[-1]
O='<REPO>'
specs={'A-C3':O+'/Cellebrite Report Sample Phone/<C3_REPORT_PATH>',
'A-C9':O+'/C9.zip::<C9_REPORT_PATH>',
'A-C8':O+'/Cellebrite C8/<C8_REPORT_PATH>'}
R={}
for l,s in specs.items():
    f=zipfile.ZipFile(s.split('::')[0]).open(s.split('::')[1]) if '::' in s else open(s,'rb')
    ids=collections.defaultdict(set); stack=[]; fld=[]; C=collections.Counter()
    for ev,el in ET.iterparse(f,events=('start','end')):
        t=ln(el.tag)
        if ev=='start':
            if t=='model': stack.append([el.get('type'),{}])
            elif t=='field': fld.append(el.get('name'))
            continue
        if t=='field' and fld: fld.pop()
        elif t=='value' and stack and fld: stack[-1][1].setdefault(fld[-1], el.text or '')
        elif t=='model':
            ty,F=stack.pop()
            if ty=='InstantMessage':
                C['im']+=1
                if F.get('Identifier'): C['im_id']+=1; ids[('im',F.get('SourceApplication') or F.get('Source',''))].add(h(F['Identifier']))
            if ty=='Chat' and F.get('Id'): ids[('chat',F.get('Source',''))].add(h(F['Id']))
            if not stack: el.clear()
    R[l]=ids; print(l,dict(C), {k:len(v) for k,v in ids.items() if k[0]=='chat'})
for a,b in itertools.combinations(R,2):
    out={}
    for k in set(R[a])&set(R[b]):
        n=len(R[a][k]&R[b][k])
        if n: out[k]=n
    print(a,b,out)
