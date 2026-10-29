import sys, time, zipfile, resource
from lxml import etree
def src(s):
    if '::' in s: z,e=s.split('::',1); return zipfile.ZipFile(z).open(e)
    return open(s,'rb')
E=A=T=0; err=[]; t0=time.time()
for s in sys.argv[1:]:
    try:
        for ev,el in etree.iterparse(src(s),events=('start','end'),huge_tree=True,remove_comments=False,resolve_entities=False,no_network=True):
            if ev=='start':
                E+=1; A+=len(el.attrib)
            else:
                if el.text is not None and el.text.strip(): T+=1
                el.clear(keep_tail=True)
                while el.getprevious() is not None: del el.getparent()[0]
    except etree.XMLSyntaxError as e:
        err.append(str(e)[:80])
print(dict(elements=E,attributes=A,texts=T,seconds=round(time.time()-t0,1),rss_mb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1048576,1),errors=err))
