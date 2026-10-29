import json,collections,sys
d='<SCRATCH>/'
docs=[json.loads(l) for l in open(d+'server_catalog.jsonl')]
for f in ('cat_c3.json','cat_c9.json','cat_c8.json'): x=json.load(open(d+f)); x['src']=f; docs.append(x)
combos=collections.defaultdict(lambda:[collections.Counter(),0])
types=collections.Counter(); typerep=collections.Counter(); enums=collections.defaultdict(set)
kinds=collections.Counter()
for x in docs:
  for t,c in x['model_types'].items(): types[t]+=c; typerep[t]+=1
  for t,f,k,vt in x['catalog']:
    combos[(t,f,k)][0].update(vt); combos[(t,f,k)][1]+=1; kinds[k]+=1
  for e,v in x['enums'].items(): enums[e].update(v)
print('docs',len(docs),'types',len(types),'combos',len(combos),'enums',len(enums))
print('kinds in catalog', kinds)
drift=[(k,dict(v[0])) for k,v in combos.items() if len(v[0])>1]
print('multi-vt combos', drift)
json.dump({'types':{t:[types[t],typerep[t]] for t in types},'combos':[[*k,dict(v[0]),v[1]] for k,v in sorted(combos.items())],'enums':{k:sorted(v) for k,v in enums.items()}},open(d+'spec02/agg.json','w'),indent=0)
