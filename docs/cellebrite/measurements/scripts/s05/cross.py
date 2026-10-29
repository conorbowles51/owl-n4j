import pickle, collections, statistics, itertools, sys
P={l:pickle.load(open(f's05/out/{l}.pkl','rb')) for l in ['A-C3','A-C9','A-C8']}
P['A-C8']['md5s']=pickle.load(open('s05/out/A-C8T.pkl','rb'))['md5s']
def t(m):
    x=m['t']; return x[1] if isinstance(x,tuple) else x
for l,p in P.items():
    ms=p['msgs']; print(l,'msgs',len(ms),'with body',sum(1 for m in ms if m['body']),'naive ts',sum(1 for m in ms if isinstance(m['t'],tuple)),'no ts',sum(1 for m in ms if m['t'] is None),'from owner',sum(m['fown'] for m in ms), 'multi-To', sum(1 for m in ms if m['ntop']>1))
print('owner ids appearing as parties on other phone:')
for a,b in itertools.permutations(P,2):
    print(' ',a,'owner ->',b,':',len(P[a]['owner'] & P[b]['parties']),'of',len(P[a]['owner']))
print('shared party identifiers (any):')
for a,b in itertools.combinations(P,2): print(' ',a,b,len(P[a]['parties']&P[b]['parties']))
for a,b in itertools.combinations(P,2):
    idx=collections.defaultdict(list)
    for m in P[b]['msgs']:
        if m['body'] and t(m) is not None: idx[m['body']].append(m)
    freqa=collections.Counter(m['body'] for m in P[a]['msgs'] if m['body'])
    res=collections.Counter(); dts=[]; srcpairs=collections.Counter()
    for m in P[a]['msgs']:
        if not m['body'] or t(m) is None or m['body'] not in idx: continue
        cands=idx[m['body']]; best=min(cands,key=lambda c:abs(t(c)-t(m))); dt=t(best)-t(m)
        common = freqa[m['body']]>3 or len(cands)>3
        short = m['blen']<10
        key='common' if common else ('short' if short else 'distinct')
        res['body_equal_'+key]+=1
        if abs(dt)<=300: res['within300s_'+key]+=1
        if abs(dt)<=3600 and key=='distinct': dts.append(dt)
        if abs(dt)<=300 and key=='distinct':
            if m['ds']!=best['ds']: res['deleted_state_differs']+=1
            if m['fown']!=best['fown']: res['complementary_direction']+=1
            srcpairs[(m['typ'],best['typ'])]+=1
    print(a,b,dict(res),'types',dict(srcpairs))
    if dts:
        med=statistics.median(dts); mad=statistics.median([abs(x-med) for x in dts]); print('   offset median s',round(med,1),'MAD',round(mad,1),'n',len(dts), 'exact0', sum(1 for x in dts if abs(x)<1))
print('media md5 overlap')
for a,b in itertools.combinations(P,2):
    s=set(P[a]['md5s'])&set(P[b]['md5s']); tags=collections.Counter(P[a]['md5s'][x] for x in s)
    print(' ',a,b,len(s),dict(tags))
print('md5 counts', {l:len(p['md5s']) for l,p in P.items()})
