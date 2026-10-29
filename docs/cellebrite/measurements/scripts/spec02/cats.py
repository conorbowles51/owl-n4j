import sys, re, collections, xml.etree.ElementTree as ET, zipfile
def s(t): return t.rsplit('}',1)[-1]
src=sys.argv[1]
if src.endswith('.zip'):
    z=zipfile.ZipFile(src); n=[i for i in z.namelist() if i.endswith('.xml') and '__MACOSX' not in i and z.getinfo(i).file_size>1e6][0]; f=z.open(n)
else: f=open(src,'rb')
KINDS=("field","multiField","modelField","multiModelField","nodeField","dataField")
C=collections.Counter(); mstack=[]; fstack=[]; partyrole=collections.Counter(); calldir=collections.Counter()
cur=[]
for ev,el in ET.iterparse(f, events=("start","end")):
    t=s(el.tag)
    if ev=='start':
        if t=='model': mstack.append(el.get('type')); cur.append({})
        elif t in KINDS and mstack: fstack.append(el.get('name'))
        continue
    if t=='value' and mstack and fstack:
        mt=mstack[-1]; fn=fstack[-1]; x=(el.text or '').strip()
        if mt in ('UserID','PhoneNumber','EmailAddress','WebAddress','ProfilePicture','SIMData','KeyValueModel') and fn in ('Category','Domain','Key','Name'):
            C[(mt,fn,x[:40] if mt!='KeyValueModel' else x[:40])]+=1
        cur[-1].setdefault(fn,x)
    elif t in KINDS and fstack and mstack: fstack.pop()
    elif t=='model':
        mt=mstack.pop(); d=cur.pop()
        if mt=='Party' and len(mstack)>0:
            partyrole[(mstack[-1], d.get('Role'), d.get('IsPhoneOwner'))]+=1
        if mt=='Call': calldir[(d.get('Direction'),d.get('Status'))]+=1
        if not mstack: el.clear()
for k,v in sorted(C.items(), key=lambda kv:-kv[1])[:60]: print(k,v)
print('PARTY parent/role/owner'); [print(' ',k,v) for k,v in sorted(partyrole.items(), key=lambda kv:-kv[1])]
print('CALL',calldir.most_common(20))
