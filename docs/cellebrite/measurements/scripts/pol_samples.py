# Structure-only: distinct short values for selected (type,field), timestamp format patterns, deleted_state per type.
import sys, json, re, collections, zipfile, xml.etree.ElementTree as ET
def s(t): return t.rsplit('}',1)[-1]
src=sys.argv[1]; inner=sys.argv[2] if len(sys.argv)>2 else None
f = zipfile.ZipFile(src).open(inner) if inner else open(src,'rb')
TYPES={'DeviceEvent','Location','Coordinate','CellTower','WirelessNetwork','AppsUsageLog','NetworkUsage','PoweringEvent','SearchedItem','DeviceConnectivity','Notification','Journey','SocialMediaActivity','ApplicationUsage','Call','InstantMessage','Party','VisitedPage','Cookie','InstalledApplication','LogEntry','CalendarEntry','UserAccount','Chat','ActivitySensorData','ActivitySensorDataSample','Email','Contact','Autofill','User'}
VALFIELDS={'EventType','Value','UserMapping','Origin','Precision','DeviceLocationAffiliation','AccountLocationAffiliation','Type','Category','Source','SourceApplication','Direction','Status','Role','IsPhoneOwner','Folder','UsageMode','Event','Element','Action','ConnectivityMethod','ConnectivityNature','DeviceType','NetworkConnectionType','Platform','SocialActivityType','OperationMode','Confidence','IsRoaming','Label','DeletionReason','IsLocationSharing','VideoCall'}
SAFE=re.compile(r'^[A-Za-z][A-Za-z0-9 _./:()-]{0,40}$')
dv=collections.defaultdict(collections.Counter); tsfmt=collections.defaultdict(collections.Counter)
dele=collections.defaultdict(collections.Counter); conf=collections.defaultdict(collections.Counter)
pairs=collections.Counter(); stack=[]; fstack=[]; cur=[]; err=None
try:
  for ev,el in ET.iterparse(f, events=("start","end")):
    t=s(el.tag)
    if ev=="start":
        if t=="model":
            ty=el.get("type"); stack.append(ty); cur.append({})
            if ty in TYPES:
                dele[ty][el.get('deleted_state')]+=1
                conf[ty][el.get('decoding_confidence')]+=1
        elif t in ("field","multiField") and stack: fstack.append((stack[-1], el.get("name")))
        continue
    if t=="value" and fstack:
        ty,fn=fstack[-1]
        if ty in TYPES:
            vt=el.get('type'); txt=(el.text or '').strip()
            if vt=='TimeStamp':
                tsfmt[(ty,fn)][re.sub(r'\d','9',txt)]+=1
            elif fn in VALFIELDS or vt not in ('String',):
                if vt in ('Double','Int64') : continue
                key = txt if (SAFE.match(txt) and vt!='String') or (SAFE.match(txt) and fn in VALFIELDS) else '<other>'
                if fn in ('Value',) and ty!='DeviceEvent': key='<n/a>'
                dv[(ty,fn)][key]+=1
            if cur: cur[-1][fn]=txt if fn in ('EventType','Value','Status','Direction','Role','IsPhoneOwner') else None
    elif t in ("field","multiField") and fstack: fstack.pop()
    elif t=="model":
        ty=stack.pop(); d=cur.pop()
        if ty=='DeviceEvent': pairs[('DE',d.get('EventType'),d.get('Value') if d.get('Value') and SAFE.match(d.get('Value')) else ('<other>' if d.get('Value') else None))]+=1
        if ty=='Call': pairs[('Call',d.get('Direction'),d.get('Status'))]+=1
        if not stack: el.clear()
except ET.ParseError as e: err=str(e)
print('parse_error',err)
for k in sorted(dv): print('V',k, dict(dv[k].most_common(40)))
for k in sorted(tsfmt): print('T',k, dict(tsfmt[k].most_common(6)))
for k in sorted(dele): print('D',k, dict(dele[k]), dict(conf[k]))
for k,c in sorted(pairs.items(), key=str): print('P',k,c)
