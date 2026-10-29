import sys, xml.etree.ElementTree as ET
# Print skeleton (tags+attr names, redacted values) of first N elements of given local tag
src = sys.stdin.buffer if sys.argv[1]=='-' else open(sys.argv[1],'rb')
want = sys.argv[2]; n=int(sys.argv[3])
def ln(t): return t.split('}')[-1]
SAFE={'name','type','systemtype','group','section','format','deleted_state','decoding_confidence','fieldType','isSystem','isRequired','multipleLines','sourceExtraction','embedded','isrelated','extractionId','fs','fsid'}
def dump(e,d=0):
    a=' '.join(f'{k.split("}")[-1]}="{v if k in SAFE else "[R]"}"' for k,v in e.attrib.items())
    t=(e.text or '').strip()
    print('  '*d+f'<{ln(e.tag)} {a}>'+(' [TEXT]' if t else ''))
    for c in e: dump(c,d+1)
c=0
stack=0
for ev,el in ET.iterparse(src,events=('end',)):
    if ln(el.tag)==want:
        dump(el); c+=1; print('----')
        if c>=n: break
