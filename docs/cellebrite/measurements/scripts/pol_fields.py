import json,sys,collections
L=[json.loads(l) for l in open(sys.argv[1])]
want=sys.argv[2].split(',')
F=collections.defaultdict(lambda: collections.Counter()); P=collections.defaultdict(set)
for i,d in enumerate(L,1):
    for t,f,k,vt in d['catalog']:
        if t in want:
            for v,c in vt.items(): F[t][(f,k,v)]+=c; P[(t,f,k,v)].add(i)
for t in want:
    print('==',t)
    for (f,k,v),c in sorted(F[t].items()): print(f"   {f} [{k}] {v} {c} ph={len(P[(t,f,k,v)])}")
