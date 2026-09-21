"""Boolean transaction search; same grammar as the investigator's table."""
import re
from services.financial.money import get_currency

FIELDS = dict(from_='from_name', to='to_name', category='category', description='description', reference='bank_reference', date='ordering_date', currency='currency', account='account_label')
FIELDS['from'] = FIELDS.pop('from_')


def transaction_search(query, mode='text'):
    tokens = re.findall(r'(?:[a-zA-Z]+:)?"(?:\\.|[^"\\])*"|\(|\)|[^\s()"]+', query)
    index = 0
    def primary():
        nonlocal index
        token = tokens[index] if index < len(tokens) else None
        index += 1
        if token is None or token in ('AND', 'OR', ')'):
            raise ValueError('Enter a term after each operator.')
        if token == 'NOT':
            return ('NOT', primary())
        if token == '(':
            value = either()
            if index >= len(tokens) or tokens[index] != ')':
                raise ValueError('Close each opening parenthesis.')
            index += 1
            return value
        match = re.fullmatch(r'([a-zA-Z]+):(.*)', token)
        field, term = (match[1].lower(), match[2]) if match else (None, token)
        if field and field not in FIELDS and field != 'amount':
            raise ValueError('Unknown search field.')
        if not term:
            raise ValueError('Enter a value after the field name.')
        if term.startswith('"'):
            term = re.sub(r'\\(.)', r'\1', term[1:-1])
        if not term.strip():
            raise ValueError('Enter text inside quoted phrases.')
        return ('term', term.lower(), field)
    def both():
        nonlocal index
        value = primary()
        while index < len(tokens) and tokens[index] not in ('OR', ')'):
            if tokens[index] == 'AND':
                index += 1
            value = ('AND', value, primary())
        return value
    def either():
        nonlocal index
        value = both()
        while index < len(tokens) and tokens[index] == 'OR':
            index += 1
            value = ('OR', value, both())
        return value
    if not query.strip():
        tree = None
    elif mode == 'boolean':
        if re.sub(r'\s', '', ''.join(tokens)) != re.sub(r'\s', '', query):
            raise ValueError('Close each quoted phrase before searching.')
        tree = either()
        if index != len(tokens):
            raise ValueError('Remove the unmatched closing parenthesis.')
    else:
        tree = ('term', query.strip().lower(), None)
    def matches(row):
        values = {name: str(row.get(field) or '') for name, field in FIELDS.items()}
        values['category'] = values['category'] or 'Uncategorized'
        scale = get_currency(row['currency']).exponent
        minor = str(row['amount_minor']).zfill(scale + 1)
        values['amount'] = minor if not scale else minor[:-scale] + '.' + minor[-scale:]
        text = ' '.join([*values.values(), *[str(row.get(key) or '') for key in ('ref_id', 'key', 'counterparty_raw', 'account_holder', 'account_id')]]).lower()
        def evaluate(node):
            if node[0] == 'term':
                return node[1] in (values[node[2]].lower() if node[2] else text)
            if node[0] == 'NOT':
                return not evaluate(node[1])
            return (evaluate(node[1]) and evaluate(node[2])) if node[0] == 'AND' else (evaluate(node[1]) or evaluate(node[2]))
        return tree is None or evaluate(tree)
    return matches
