"""Per top-level-record size distribution. Structure only."""
import sys, zipfile, collections as C, xml.etree.ElementTree as ET
def ln(t): return t.rsplit('}',1)[-1]
def src(s):
    if '::' in s:
        z,e=s.split('::',1); return zipfile.ZipFile(z).open(e)
    return open(s,'rb')
sizes=[]; tbytes=[]; per_type=C.defaultdict(list); fsize=[]; nested=[]
for s in sys.argv[1:]:
    stack=[]; cur=None; fcur=None
    try:
        for ev,el in ET.iterparse(src(s),events=('start','end')):
            n=ln(el.tag)
            if ev=='start':
                par=stack[-1] if stack else None
                stack.append(n)
                if n=='model' and par=='modelType':
                    cur=[0,0,0,el.get('type'),len(stack)]
                if cur is not None:
                    cur[0]+=1+len(el.attrib)
                    if n=='model': cur[2]+=1
                if n=='file' and par=='taggedFiles': fcur=[0,len(stack)]
                if fcur is not None: fcur[0]+=1+len(el.attrib)
            else:
                if cur is not None and el.text and el.text.strip(): cur[1]+=len(el.text.encode())
                if n=='model' and cur is not None and len(stack)==cur[4]:
                    sizes.append(cur[0]); tbytes.append(cur[1]); per_type[cur[3]].append(cur[0]); nested.append(cur[2]); cur=None
                if n=='file' and fcur is not None and len(stack)==fcur[1]: fsize.append(fcur[0]); fcur=None
                stack.pop(); el.clear()
    except ET.ParseError as e: print('parse error', str(e)[:60])
def q(a):
    a=sorted(a); return dict(n=len(a),median=a[len(a)//2],p99=a[int(len(a)*.99)],p999=a[int(len(a)*.999)],max=a[-1],sum=sum(a)) if a else {}
print('record units(elements+attrs)',q(sizes)); print('record text bytes',q(tbytes)); print('models per record',q(nested)); print('tagged file units',q(fsize))
big=sorted(((max(v),k,len(v)) for k,v in per_type.items()),reverse=True)[:5]; print('largest by type',big)
