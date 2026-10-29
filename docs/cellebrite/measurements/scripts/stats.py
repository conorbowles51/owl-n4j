import sys, re, json, collections as C, xml.etree.ElementTree as ET
args=sys.argv[1:]
listing=set()
lp=args[args.index('--list')+1]
for l in open(lp,encoding='utf-8',errors='replace'):
    listing.add(l.rstrip('\n').replace('\\','/').lower())
xmls=[args[i+1] for i,a in enumerate(args) if a=='--xml']
def ln(t): return t.split('}')[-1]
R=dict(roots=[],ns=set(),tagcount=C.Counter(),attrnames=C.defaultdict(set),
 meta_items=C.defaultdict(C.Counter),meta_nonempty=C.defaultdict(C.Counter),
 file_count=0,file_deleted=C.Counter(),file_fs=C.Counter(),file_embedded=C.Counter(),file_ext=C.Counter(),
 file_lp_present=0,file_lp_exists=0,file_lp_prefix=C.Counter(),file_hash=C.Counter(),file_tags=C.Counter(),
 mt_top=C.Counter(),mt_all=C.Counter(),mt_deleted=C.defaultdict(C.Counter),mt_source=C.defaultdict(C.Counter),
 fieldnames=C.defaultdict(C.Counter),jt=0,jt_resolved=0,valpaths=0,valpaths_exist=0,valpath_prefix=C.Counter(),
 maxtext=0,maxtext_tag='',maxdepth=0,extrainfo=0,extrainfo_child=C.Counter(),tz=None,rootattrs={},
 nonascii_ctrl=0,model_attr_vals=C.defaultdict(C.Counter),value_types=C.Counter(),confidence=C.Counter())
file_ids=set(); targets=[]
PATHRE=re.compile(r'^(chats|files|contacts|photos|thumbnails|fileuploads|socialmedia|useraccounts)[\\/]',re.I)
def chkpath(v):
    v=v.strip()
    if PATHRE.match(v):
        R['valpaths']+=1
        p=v.replace('\\','/').lower()
        R['valpath_prefix']['/'.join(p.split('/')[:2]) if not p.startswith('files') else '/'.join(p.split('/')[:2])]+=0
        R['valpath_prefix'][p.split('/')[0]]+=1
        if p in listing: R['valpaths_exist']+=1
def walk_model(m,top):
    t=m.get('type'); R['mt_all'][t]+=1
    R['mt_deleted'][t][m.get('deleted_state')]+=1
    R['confidence'][m.get('decoding_confidence')]+=1
    for c in m:
        tag=ln(c.tag)
        if tag=='field':
            R['fieldnames'][t][c.get('name')]+=1
            for v in c:
                R['value_types'][v.get('type')]+=1
                if v.text: chkpath(v.text)
                if top and c.get('name')=='Source' and v.text: R['mt_source'][t][v.text.strip()]+=1
        elif tag in('modelField','multiModelField'):
            R['fieldnames'][t]['<'+tag+'>'+str(c.get('name'))]+=1
            for mm in c.iter():
                if ln(mm.tag)=='model' and mm is not c: pass
            for mm in c:
                if ln(mm.tag)=='model': walk_model(mm,False)
        elif tag=='jumptargets':
            for tg in c:
                R['jt']+=1; targets.append((tg.text or '').strip())
        else:
            R['fieldnames'][t]['<'+tag+'>']+=1
            if tag in('nodeField','multiNodeField'):
                for x in c.iter():
                    if ln(x.tag)=='file': pass
for x in xmls:
    src=sys.stdin.buffer if x=='-' else open(x,'rb')
    depth=0; stack=[]
    R.setdefault('errors',[])
    ITP=ET.iterparse(src,events=('start','end','start-ns'))
    while True:
      try:
        ev,el=next(ITP)
      except StopIteration: break
      except ET.ParseError as e:
        R['errors'].append(x[-14:]+': '+str(e)+' openstack='+'/'.join(stack)); break
      if True:
          if ev=='start-ns': R['ns'].add(el[1]); continue
          tag=ln(el.tag)
          if ev=='start':
              if depth==0:
                  R['roots'].append(tag); R['rootattrs'][tag]={k:v for k,v in el.attrib.items() if k in('reportVersion','extractionType','NodeCount','ModelCount','containsGarbage','MediaResults')}
                  R['rootattrnames']=list(el.attrib.keys())
              stack.append(tag); depth+=1; R['maxdepth']=max(R['maxdepth'],depth)
              R['tagcount'][tag]+=1
              for k in el.attrib: R['attrnames'][tag].add(k)
              continue
          depth-=1; stack.pop()
          if el.text and len(el.text)>R['maxtext']: R['maxtext']=len(el.text); R['maxtext_tag']='/'.join(stack[-3:]+[tag])
          parent=stack[-1] if stack else None
          if tag=='item' and parent=='metadata' and 'file' not in stack:
              sec=None
              R['meta_items'][str(len(stack))][el.get('name')]+=1
              if (el.text or '').strip(): R['meta_nonempty'][str(len(stack))][el.get('name')]+=1
          if tag=='file' and parent=='taggedFiles':
              R['file_count']+=1; file_ids.add(el.get('id'))
              R['file_deleted'][el.get('deleted')]+=1; R['file_fs'][el.get('fs')]+=1; R['file_embedded'][el.get('embedded')]+=1
              n=el.get('name') or ''; R['file_ext'][n.rsplit('.',1)[-1].lower() if '.' in n else '(none)']+=1
              for it in el.iter():
                  if ln(it.tag)=='item':
                      nm=it.get('name'); v=(it.text or '').strip()
                      if nm=='Local Path' and v:
                          R['file_lp_present']+=1; p=v.replace('\\','/').lower()
                          R['file_lp_prefix']['/'.join(p.split('/')[:2])]+=1
                          if p in listing: R['file_lp_exists']+=1
                      if nm in('MD5','SHA256') and v: R['file_hash'][nm]+=1
                      if nm=='Tags' and v: R['file_tags'][v]+=1
              el.clear()
          if tag=='model' and parent=='modelType':
              R['mt_top'][el.get('type')]+=1; walk_model(el,True); el.clear()
          if parent=='extraInfos':
              R['extrainfo']+=1
              for c in el.iter(): R['extrainfo_child'][ln(c.tag)]+=1
              el.clear()
          if tag=='timeZoneConfigurations': R['tz']=dict(el.attrib)
          if parent in('taggedFiles','extraInfos','modelType'): pass
res={k:(v if not isinstance(v,set) else sorted(v)) for k,v in R.items()}
res['attrnames']={k:sorted(v) for k,v in R['attrnames'].items()}
res['jt_resolved']=sum(1 for t in targets if t in file_ids); res['jt_unique']=len(set(targets)); res['file_ids']=len(file_ids)
res['mt_source']={k:dict(v.most_common(15)) for k,v in R['mt_source'].items()}
print(json.dumps(res,indent=1,default=str))
