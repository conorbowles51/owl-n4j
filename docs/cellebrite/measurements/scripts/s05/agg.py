import json,sys,collections
def label(src):
    if '<CASE_1P_ID>' in src: return '1P'
    case='A' if '<CASE_A_ID>' in src else 'B'
    import re
    m=re.findall(r'_(C\d)_|/(C\d)[_ -]|C1-0',src)
    if '<A_C1B_REPORT_PATH>' in src: return 'A-C1b'
    if '<A_C1A_MARK>' in src: return 'A-C1a'
    for a,b in m:
        x=a or b
        if x: return case+'-'+x
    return case+'-?'
phones=[]
for l in open(sys.argv[1]):
    d=json.loads(l); phones.append((label(d['src']),d))
types=collections.defaultdict(dict); fields=collections.defaultdict(dict); enums=collections.defaultdict(set)
for lab,d in phones:
    for t,c in d['model_types'].items(): types[t][lab]=c
    for t,f,k,vt in d['catalog']: fields[(t,f,k)][lab]=vt
    for e,vals in d['enums'].items(): enums[e].update(vals)
json.dump({'labels':[p[0] for p in phones],'types':types,'fields':{'|'.join(k):v for k,v in fields.items()},'enums':{k:sorted(v) for k,v in enums.items()}},open(sys.argv[2],'w'),indent=0)
print([p[0] for p in phones])
