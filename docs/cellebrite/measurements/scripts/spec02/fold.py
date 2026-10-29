import unicodedata as u, re
DECOR={}
# negative circled A-Z U+1F150..1F169, negative squared U+1F170..1F189
for i in range(26):
    DECOR[0x1F150+i]=chr(65+i); DECOR[0x1F170+i]=chr(65+i)
# small capitals (subset, single-letter targets)
SC={0x1D00:'A',0x0299:'B',0x1D04:'C',0x1D05:'D',0x1D07:'E',0xA730:'F',0x0262:'G',0x029C:'H',0x026A:'I',0x1D0A:'J',0x1D0B:'K',0x029F:'L',0x1D0D:'M',0x0274:'N',0x1D0F:'O',0x1D18:'P',0xA7AF:'Q',0x0280:'R',0xA731:'S',0x1D1B:'T',0x1D1C:'U',0x1D20:'V',0x1D21:'W',0x028F:'Y',0x1D22:'Z'}
DECOR.update(SC)
CYR={0x0410:'A',0x0430:'a',0x0412:'B',0x0415:'E',0x0435:'e',0x041A:'K',0x041C:'M',0x041D:'H',0x041E:'O',0x043E:'o',0x0420:'P',0x0440:'p',0x0421:'C',0x0441:'c',0x0422:'T',0x0425:'X',0x0445:'x',0x0443:'y',0x0456:'i',0x0406:'I',0x0458:'j',0x0405:'S',0x0455:'s'}
GRK={0x0391:'A',0x0392:'B',0x0395:'E',0x0396:'Z',0x0397:'H',0x0399:'I',0x039A:'K',0x039C:'M',0x039D:'N',0x039F:'O',0x03BF:'o',0x03A1:'P',0x03A4:'T',0x03A5:'Y',0x03A7:'X'}
def script(c):
    n=u.name(c,'')
    return 'LATIN' if n.startswith('LATIN') else 'CYRILLIC' if n.startswith('CYRILLIC') else 'GREEK' if n.startswith('GREEK') else 'OTHER'
def name_key(s):
    s=u.normalize('NFKC', s or '')
    s=''.join(DECOR.get(ord(c),c) for c in s)
    out=[]
    for tok in re.split(r'(\s+)', s):
        letters={script(c) for c in tok if c.isalpha()}
        if 'LATIN' in letters and letters & {'CYRILLIC','GREEK'}:
            tok=''.join(CYR.get(ord(c), GRK.get(ord(c), c)) for c in tok)
        out.append(tok)
    s=''.join(out).casefold()
    s=''.join(c if (c.isalnum() or u.category(c)=='Mn') else ' ' for c in s if u.category(c) not in ('Cf','Cc'))
    return ' '.join(s.split())
def loose_key(s):
    return u.normalize('NFC',''.join(c for c in u.normalize('NFD',name_key(s)) if u.category(c)!='Mn'))
V=['\U0001D4D0\U0001D4F7\U0001D4EA','ＡＮＡ','ᴀɴᴀ','\U0001F170\U0001F17D\U0001F170','Ⓐⓝⓐ','Аna','Анна','José','José','Ana \U0001F1FA\U0001F1F8','ANA ​ MARIA','Ana-María','\U0001D400\U0001D427\U0001D41A \U0001D40C\U0001D41A\U0001D42B\U0001D422\U0001D41A','ana.maria','Αna','ß','O’Neil','\U0001D7CF\U0001D7D0\U0001D7D1']
for v in V: print(repr(v), '->', repr(name_key(v)), repr(loose_key(v)))
