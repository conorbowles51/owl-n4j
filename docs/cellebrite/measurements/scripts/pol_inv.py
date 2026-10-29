import json,sys,collections
L=[json.loads(l) for l in open(sys.argv[1])]
tot=collections.Counter(); ph=collections.defaultdict(set)
tsf=collections.defaultdict(lambda: collections.Counter()); tsph=collections.defaultdict(set)
for i,d in enumerate(L,1):
    for t,c in d['model_types'].items(): tot[t]+=c; ph[t].add(i)
    for t,f,k,vt in d['catalog']:
        if 'TimeStamp' in vt or 'TimeSpan' in vt:
            for v in ('TimeStamp','TimeSpan'):
                if v in vt: tsf[t][(f,k,v)]+=vt[v]; tsph[(t,f,v)].add(i)
for t in sorted(tsf, key=lambda t:-tot[t]):
    print(f"{t}\t{tot[t]}\t{len(ph[t])}\t{sorted(ph[t])}")
    for (f,k,v),c in tsf[t].most_common(): print(f"    {f} [{k}] {v} values={c} phones={len(tsph[(t,f,v)])}")
