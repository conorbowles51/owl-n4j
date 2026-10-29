import sys, collections as C, xml.etree.ElementTree as ET
def ln(t): return t.split('}')[-1]
fids=set(); mids=set(); tg=[]; mfile=[]; srcfile=C.Counter(); ds=C.Counter(); emb=C.Counter()
for x in sys.argv[1:]:
    src=sys.stdin.buffer if x=='-' else open(x,'rb')
    try:
        for ev,el in ET.iterparse(src,events=('end',)):
            t=ln(el.tag)
            if t=='file': fids.add(el.get('id')); el.clear()
            elif t=='model':
                mids.add(el.get('id'))
                if el.get('file_id'): mfile.append(el.get('file_id'))
            elif t=='targetid': tg.append((el.get('ismodel'),(el.text or '').strip()))
            elif t=='dataField':
                for c in el: emb[ln(c.tag)]+=1
            elif t=='modelType': el.clear()
    except ET.ParseError as e: print('ERR',e)
r=C.Counter()
for im,v in tg: r[(im, 'file' if v in fids else 'model' if v in mids else 'unresolved')]+=1
print('targets',dict(r)); print('model.file_id',len(mfile),'resolved',sum(1 for f in mfile if f in fids)); print('dataField children',dict(emb))
