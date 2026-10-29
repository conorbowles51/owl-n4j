import sys, re, collections, xml.etree.ElementTree as ET
def s(t): return t.rsplit('}',1)[-1]
f=open(sys.argv[1],'rb'); fmt=collections.Counter(); ftp=collections.Counter(); ts=collections.Counter(); dbl=collections.Counter(); boo=collections.Counter()
for ev,el in ET.iterparse(f, events=("end",)):
    if s(el.tag)=='value':
        t=el.get('type'); x=(el.text or '').strip()
        if t=='TimeStamp':
            fmt[el.get('format')]+=1; ftp[re.sub(r'[0-9]','9',re.sub(r'[A-Za-z]+','A',el.get('formattedTimestamp') or ''))]+=1
        elif t=='TimeSpan': ts[re.sub(r'\d','9',x)]+=1
        elif t=='Double': dbl[re.sub(r'\d+','9',x)]+=1
        elif t=='Boolean': boo[x]+=1
    if s(el.tag)=='model' : pass
print('format',fmt.most_common(5)); print('formatted',ftp.most_common(8)); print('timespan',ts.most_common(8)); print('double',dbl.most_common(6)); print('bool',boo)
