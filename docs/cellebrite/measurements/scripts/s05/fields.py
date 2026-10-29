import json,sys
a=json.load(open('s05/agg.json'))
want=sys.argv[1].split(',')
for k,v in a['fields'].items():
    t,f,kind=k.split('|')
    if t in want:
        tot={}
        for lab,vt in v.items():
            for x,c in vt.items(): tot[x]=tot.get(x,0)+c
        print(f'{t}.{f} [{kind}] phones={len(v)} {tot} on={",".join(v)}')
