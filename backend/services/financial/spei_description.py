"""Directional fields in Kapital's explicitly delimited SPEI description.

Position is used only inside this recognised layout. Unlabelled middle tokens
remain payment references; they are never guessed to be account identifiers.
"""
import re
import unicodedata


def _norm(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', value.upper())
        if not unicodedata.combining(c)).split())


def kapital_spei(description):
    raw = description or ''
    fields = []
    for match in re.finditer(r'[^|]+', raw):
        text = match[0].strip()
        if text:
            start = match.start() + len(match[0]) - len(match[0].lstrip())
            fields.append(dict(text=text, start=start, end=start+len(text)))
    if len(fields) < 10 or len(fields) > 14:
        return None
    method = _norm(fields[0]['text'])
    if method not in ('RECEPCION SPEI', 'ENVIO SPEI') or _norm(fields[-3]['text']) not in ('KAPITAL', 'BANCO KAPITAL'):
        return None
    if not all(re.fullmatch(r'\d{18}', fields[i]['text']) for i in (3, -1)):
        return None
    qualifier = 'DATO NO VERIFICADO POR ESTA INSTITUCION'
    def party(index):
        value = fields[index]['text']
        normalized = _norm(value)
        # The qualification belongs to the source assertion, not the name.
        split = re.search(r'\bDATO\s+NO\s+VERIFICADO\s+POR\s+ESTA\s+INSTITUCI[OÓ]N\s*$', value, re.I)
        name = value[:split.start()].strip() if split else value
        if not name or not re.search(r'[A-Za-zÁÉÍÓÚÑáéíóúñ]', name):
            return None
        return dict(name=name, qualifier=qualifier if normalized.endswith(qualifier) else None, **fields[index])
    other, own = party(2), party(-2)
    if not other or not own:
        return None
    incoming = method == 'RECEPCION SPEI'
    remote = dict(party=other, bank=fields[1], account={**fields[3], 'kind':'clabe'})
    local = dict(party=own, bank=fields[-3], account={**fields[-1], 'kind':'clabe'})
    return dict(method='SPEI', layout='kapital-delimited-spei', direction='credit' if incoming else 'debit',
        sender=remote if incoming else local, recipient=local if incoming else remote,
        payment_references=fields[4:-3], ownership_established=False)
