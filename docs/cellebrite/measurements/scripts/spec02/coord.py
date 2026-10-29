import sys, collections, xml.etree.ElementTree as ET, zipfile
def s(t): return t.rsplit('}',1)[-1]
src=sys.argv[1]
if src.endswith('.zip'):
    z=zipfile.ZipFile(src); n=[i for i in z.namelist() if i.endswith('.xml') and '__MACOSX' not in i and z.getinfo(i).file_size>1e6][0]; f=z.open(n)
else: f=open(src,'rb')
KINDS=("field","multiField","modelField","multiModelField","nodeField","dataField")
C=collections.Counter(); mstack=[]; fstack=[]; cur=[]; parents=[]
tsv=collections.Counter(); emp=collections.Counter(); multi=collections.Counter(); fid=collections.Counter()
for ev,el in ET.iterparse(f, events=("start","end")):
    t=s(el.tag)
    if ev=='start':
        if t=='model':
            parents.append(mstack[-1] if mstack else None); mstack.append(el.get('type')); cur.append({'_n':collections.Counter()})
            if el.get('file_id'): fid[el.get('type')]+=1
        elif t in KINDS and mstack: fstack.append(el.get('name'))
        continue
    if t=='value' and mstack and fstack:
        cur[-1].setdefault(fstack[-1], (el.text or '').strip()); cur[-1]['_n'][fstack[-1]]+=1
        if el.get('type')=='TimeStamp': tsv[mstack[-1]]+=1
    elif t=='empty' and mstack and fstack: emp[(mstack[-1])]+=1
    elif t in KINDS and fstack and mstack:
        fn=fstack.pop()
        if t=='field' and cur[-1]['_n'][fn]>1: multi[(mstack[-1],fn)]+=1
    elif t=='model':
        mt=mstack.pop(); d=cur.pop(); p=parents.pop()
        if mt=='Coordinate':
            la,lo=d.get('Latitude'),d.get('Longitude')
            C[(p,'has_lat_lon' if la and lo else 'missing')]+=1
            try:
                if la and lo and float(la)==0 and float(lo)==0: C[(p,'zero_zero')]+=1
                if la and lo and not(-90<=float(la)<=90 and -180<=float(lo)<=180): C[(p,'out_of_range')]+=1
            except ValueError: C[(p,'unparseable')]+=1
            C[(p,'coord_acc')]+= 1 if d.get('GpsHorizontalAccuracy') else 0
            C[(p,'elev')]+= 1 if d.get('Elevation') else 0
        if mt=='Location':
            C[('Location','own_acc')]+= 1 if d.get('GpsHorizontalAccuracy') else 0
            C[('Location','n')]+=1
            C[('Location','DLA:'+str(d.get('DeviceLocationAffiliation')))]+=1
        if not mstack: el.clear()
print(sorted(C.items())); print('TS values by type', tsv.most_common(40)); print('empty by type', emp.most_common(10)); print('field with >1 value', multi.most_common(10)); print('file_id attr by type', fid.most_common(10))
