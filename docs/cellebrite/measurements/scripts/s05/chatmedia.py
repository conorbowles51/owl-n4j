import hashlib, os, zipfile, itertools, collections
O='<REPO>'
S={}
def add(l,data,name):
    S.setdefault(l,{})[hashlib.md5(data).hexdigest()]=name.rsplit('.',1)[-1].lower() if '.' in name.rsplit('/',1)[-1] else '(none)'
for l,root in (('A-C3',O+'/Cellebrite Report Sample Phone/chats'),('A-C8',O+'/Cellebrite C8/chats')):
    for dp,dn,fn in os.walk(root):
        for f in fn:
            if f=='.DS_Store': continue
            add(l,open(os.path.join(dp,f),'rb').read(),f)
z=zipfile.ZipFile(O+'/C9.zip')
for n in z.namelist():
    if 'MACOSX' in n or n.endswith('/') or n.endswith('.DS_Store'): continue
    if n.split('/')[0]=='chats': add('A-C9',z.read(n),n)
print({l:len(v) for l,v in S.items()})
for a,b in itertools.combinations(S,2):
    s=set(S[a])&set(S[b]); print(a,b,len(s),collections.Counter(S[a][x] for x in s))
