import sys, zipfile, collections, re, xml.etree.ElementTree as ET
def ln(t): return t.rsplit('}',1)[-1]
spec=sys.argv[1]
f=zipfile.ZipFile(spec.split('::')[0]).open(spec.split('::')[1]) if '::' in spec else open(spec,'rb')
KNOWN={'msgstore.db','wa.db','mmssms.db','contacts2.db','calllog.db','history','cookies','web data','login data','sms.db','addressbook.sqlitedb','callhistory.storedata','knowledgec.db','cache.db','chatstorage.sqlite','accounts.db','accounts_ce.db','accounts_de.db','telephony.db','bugle_db','downloads.db','cache4.db','fbmessenger.db','threads_db2','gmail.db','photos.db','external.db','localappstate.db','usagestats'}
C=collections.Counter(); ext=collections.Counter()
try:
  for ev,el in ET.iterparse(f, events=('end',)):
    if ln(el.tag)=='file':
        p=(el.get('path') or '').replace('\\','/'); b=p.rsplit('/',1)[-1].lower()
        tag=None
        for it in el.iter():
            if ln(it.tag)=='item' and it.get('name')=='Tags': tag=(it.text or '').strip()
        C['files']+=1
        if p: C['has_original_path']+=1
        if b in KNOWN: C['known_artifact_db']+=1
        if re.search(r'\.(db|sqlite|sqlitedb|storedata)$',b): C['sqlite_named']+=1
        if b.endswith('-wal') or b.endswith('-journal'): C['wal_or_journal']+=1
        el.clear()
except ET.ParseError: C['parse_stopped']+=1
print(dict(C))
