"""The other side of a payment, as the statement prints it in the description.

Each rule recognises one printed layout and takes the name from the field that
layout reserves for the beneficiary, the ordering party, the payee or the
merchant. A bank that only carries the money (the receiving or sending bank of
a transfer) is never taken as the party when a name is printed. Nothing is
guessed: a layout whose name field cannot be told apart from its references or
concept text gives no name. These are read-time suggestions; the stored
description is never changed and a person's label always wins
(services.financial.payment_labels).
"""
import re
import unicodedata

from services.financial.payment_inference import normalized

# Mexican banks as they are printed before the beneficiary in SPEI lines that
# print no field separator. Longest names first so 'BBVA MEXICO' wins over 'BBVA'.
_MX_BANKS = sorted([
    'BBVA MEXICO', 'BBVA BANCOMER', 'BBVA', 'BANAMEX', 'CITI MEXICO', 'CITIBANAMEX', 'BANORTE', 'SANTANDER', 'HSBC',
    'SCOTIABANK', 'INBURSA', 'AZTECA', 'BANCOPPEL', 'BAJIO', 'BANBAJIO', 'AFIRME', 'MIFEL', 'BANREGIO', 'MONEX',
    'INTERCAM BANCO', 'INTERCAM', 'KAPITAL', 'AUTOFIN', 'NU MEXICO', 'STP', 'KUSPIT', 'BANCOMEXT', 'VE POR MAS',
    'MULTIVA', 'BANJERCITO', 'ACTINVER', 'BANSI', 'INVEX', 'BARCLAYS', 'MERCADO PAGO W', 'SABADELL', 'HEY BANCO',
    'BANCO BASE', 'CIBANCO', 'HSBC MEXICO', 'SANTANDER MEXICO', 'BANORTE IXE', 'SCOTIABANK INVERLAT', 'BANKAOOL', 'ALBO', 'FONDEADORA', 'SPIN BY OXXO', 'TRANSFER', 'ASP INTEGRA OPC',
], key=len, reverse=True)

_UNVERIFIED = r'\s*(?:\bDAT[O0]\s*N[O0]\b|DAT[O0]\s*N[O0]\s*\W?[VM]ERIF).*$'
_STATES = ('AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH '
           'OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY').split()
# Places printed after the merchant on US debit card lines, removed only when
# they are the last words before the state. Other place names stay, so the
# printed descriptor is never cut where its end is unclear.
_PLACES = ['WASHINGTON', 'HYATTSVILLE', 'SUITLAND', 'SILVER SPRING', 'OXON HILL', 'ALEXANDRIA', 'ANNAPOLIS',
           'FALLS CHURCH', 'WHEATON', 'ODENTON', 'MILLERSVILLE', 'CAMP SPRINGS', 'CLINTON', 'TEMPLE HILLS',
           'DISTRICT HEIG', 'FORT WASHINGT', 'UPPER MARLBOR', 'UPPR MARLBORO', 'CAPITOL HEIGH', 'LANHAM',
           'BOWIE', 'LAUREL', 'ARLINGTON', 'BALTIMORE', 'BETHESDA', 'ROCKVILLE', 'COLLEGE PARK', 'LARGO',
           'GREENBELT', 'WOODBRIDGE', 'FORESTVILLE', 'DISTRICT HEIGHTS', 'NEW YORK', 'NEW YORK CITY']
_PLACES.sort(key=len, reverse=True)

# Mexican state abbreviations and the places most printed as a branch, borough or merchant location. A name
# ending in a state code, or that is one of these places, is where, not who.
_MX_STATES = ('AGS BC BCN BCS CAMP CHIS CHIH CDMX COAH COL DGO DF EDOMEX GTO GRO HGO JAL MEX MICH MOR NAY NL OAX PUE '
              'QRO QROO SLP SIN SON TAB TAMPS TAMS TLAX VER YUC ZAC').split()
_MX_PLACES = frozenset(' '.join(p.split()) for p in """
    MEXICO|CIUDAD DE MEXICO|CD DE MEXICO|CD MEXICO|MEXICO DF|MONTERREY|GUADALAJARA|ZAPOPAN|PUEBLA|TIJUANA|LEON|JUAREZ|CIUDAD JUAREZ|
    CD JUAREZ|TOLUCA|QUERETARO|SANTIAGO DE QUERETARO|MERIDA|CANCUN|CHIHUAHUA|AGUASCALIENTES|SAN LUIS POTOSI|HERMOSILLO|CULIACAN|
    MEXICALI|SALTILLO|TORREON|MORELIA|VERACRUZ|ACAPULCO|OAXACA|TAMPICO|REYNOSA|MATAMOROS|DURANGO|VICTORIA DE DURANGO|CIUDAD VICTORIA|
    MAZATLAN|CUERNAVACA|PACHUCA|XALAPA|VILLAHERMOSA|TUXTLA GUTIERREZ|TLAXCALA|ZACATECAS|COLIMA|TEPIC|CAMPECHE|CHETUMAL|LA PAZ|
    ENSENADA|NOGALES|CELAYA|IRAPUATO|SAN PEDRO GARZA GARCIA|SAN NICOLAS DE LOS GARZA|APODACA|ESCOBEDO|GUADALUPE|SANTA CATARINA|
    NAUCALPAN|TLALNEPANTLA|ECATEPEC|NEZAHUALCOYOTL|HUIXQUILUCAN|METEPEC|TLAQUEPAQUE|TONALA|TLAJOMULCO|MIGUEL HIDALGO|BENITO JUAREZ|
    CUAUHTEMOC|COYOACAN|TLALPAN|IZTAPALAPA|IZTACALCO|AZCAPOTZALCO|GUSTAVO A MADERO|ALVARO OBREGON|VENUSTIANO CARRANZA|XOCHIMILCO|
    CUAJIMALPA|MAGDALENA CONTRERAS|MILPA ALTA|TLAHUAC|DOLORES HIDALGO|JESUS MARIA|SALVADOR ALVARADO|SAN MIGUEL DE ALLENDE|
    LOS MOCHIS|GUASAVE|NAVOJOA|CIUDAD OBREGON|CD OBREGON|SAN JOSE DEL CABO|CABO SAN LUCAS|PLAYA DEL CARMEN|SANTA FE|POLANCO|
    SAN FRANCISCO|LOS ANGELES|SAN DIEGO|SAN ANTONIO|SAN JOSE|HOUSTON|DALLAS|AUSTIN|EL PASO|CHICAGO|PHOENIX|PHILADELPHIA|
    MIAMI|ORLANDO|TAMPA|ATLANTA|BOSTON|SEATTLE|DENVER|DETROIT|LAS VEGAS|PORTLAND|CHARLOTTE|NASHVILLE|COLUMBUS|INDIANAPOLIS|
    JACKSONVILLE|FORT WORTH|MEMPHIS|LOUISVILLE|MILWAUKEE|ALBUQUERQUE|TUCSON|FRESNO|SACRAMENTO|KANSAS CITY|OMAHA|RALEIGH|
    RICHMOND|NORFOLK|PITTSBURGH|CLEVELAND|CINCINNATI|BROOKLYN|BRONX|QUEENS|MANHATTAN|NEWARK|JERSEY CITY|BUFFALO|LONDON|TORONTO
""".split('|') if p.strip())
# Openings of a street address.
_ADDRESS_FIRST = frozenset('AV AVE AVENIDA CALLE CALZ CALZADA BLVD BOULEVARD CARR CARRETERA PRIV PRIVADA COL COLONIA KM '
                           'PROL PROLONGACION ANDADOR CIRCUITO RETORNO CERRADA MANZANA MZ LOTE LT PASEO PERIFERICO ANILLO EJE'.split())
# Last words of a street name (INSURGENTES SUR, MAIN ST).
_ADDRESS_LAST = frozenset('SUR NORTE OTE PTE ORIENTE PONIENTE ST STREET AVE AVENUE RD ROAD BLVD DR DRIVE LN LANE WAY HWY PKWY'.split())
# Concept, period and linking words: a name made only of these (even with a legal form) is not a party.
_NOT_NAME_WORDS = frozenset(
    'VIDA BONO BONOS QUINCENA QNA HORAS HORA EXTRA EXTRAS SUELDO SUELDOS SALARIO SALARIOS VIATICOS AGUINALDO VACACIONES '
    'PRIMA PRIMAS FINIQUITO NOMINA PAGO PAGOS RENTA SEGURO SEGUROS GASTOS COMISION COMISIONES TRABAJO SANGUINEO SERVICIO '
    'SERVICIOS PRESTAMO ANTICIPO APOYO AYUDA DESPENSA FONDO AHORRO UTILIDADES PTU INCAPACIDAD DE DEL LA LAS LOS EL Y E'.split()) \
    | frozenset(_MX_STATES)
# Banks a descriptor may print; a bank alone is never the merchant or payee of a line that should name one.
_BANK_NAMES = frozenset(_MX_BANKS) | frozenset(' '.join(b.split()) for b in """BANK OF AMERICA|CHASE|JPMORGAN CHASE|WELLS FARGO|
    CITIBANK|CITI|CAPITAL ONE|TRUIST|PNC|US BANK|TD BANK|NAVY FEDERAL|NAVY FEDERAL CREDIT UNION|M&T|M&T BANK|SANTANDER BANK|
    BANCO SANTANDER|BBVA USA|BANCO AZTECA|BANCO DEL BAJIO|BANCOMER|BANCO BBVA|BANCO MONEX|BANCO INTERCAM|HSBC BANK""".split('|'))


def bank_name(text):
    """True when the text is a bank's name, alone or followed by other words (WELLS FARGO BANK, BANCOMER SA)."""
    text = ' '.join(re.sub(r'[^A-Z0-9& ]', ' ', normalized(text)).split())
    return any(text == bank or text.startswith(bank + ' ') for bank in _BANK_NAMES) or bool(re.match(r'BANCO\b|BANK\b', text))


def place_name(text):
    """True when the text is a place: it ends in a Mexican state code (at most three words before it), or without
    its final state code it is a known place."""
    words = re.sub(r'[^A-Z0-9 ]', ' ', normalized(text)).split()
    if not words:
        return False
    if words[-1] in _MX_STATES and len(words) <= 4:
        return True
    while words and (words[-1] in _MX_STATES or words[-1] in _STATES):
        words = words[:-1]
    return ' '.join(words) in _MX_PLACES or ' '.join(words) in _PLACES


def _without_place(label):
    """The label without a known place printed (or glued, 'MARKETWASHINGTON') at its end."""
    for place in _PLACES:
        if label.endswith(place) and len(label) > len(place) + 2 and (label[-len(place) - 1] == ' ' or len(place) >= 8):
            return label[:-len(place)].strip()
    return label


def clean_name(value):
    """A printed name without the bank's qualification, footnote marks and stray references."""
    text = re.sub(_UNVERIFIED, '', value or '', flags=re.I)
    text = re.sub(r'(?:[({]\s*[1lI7]\s*(?:[)}]|(?=\s|$))\s*)+', ' ', text)
    # Long digit runs inside a name are a reference that landed in the field.
    text = ' '.join(t for t in text.split() if not re.fullmatch(r'\d{6,}', t))
    return text.strip(' |],;:.-—').strip()


def plausible_name(value):
    text = normalized(value)
    letters = sum(c.isalpha() for c in text)
    return (letters >= 2 and len(text) <= 180 and not re.search(r'\d{7,}', text)
            and not re.fullmatch(r'(?:REF|REFERENCIA|CONCEPTO|CUENTA|CLABE|ACCOUNT|CLIENTE|BANCO|BANK|N/?A|SIN NOMBRE|'
                                 r'TERCEROS?|ORDENANTE|BENEFICIARIO|NOMBRE|NONE|UNKNOWN)', text))


# Words that describe what a payment is for rather than who it is with. A name opening with one of
# these, or holding a payment word anywhere, is the concept or the line's own wording, not a party.
_CONCEPT_FIRST = frozenset('PAGO PAGOS ONLINE AUTOPAY AUTOMATIC RECURRING TRANSFER TRANSFERENCIA TRASPASO LOAN MONTHLY ANNUAL '
                           'MENSUALIDAD RENT RENTA REFUND REEMBOLSO ANTICIPO COLEGIATURA FEE FEES SERVICE SERVICIO CUOTA ABONO '
                           'CARGO TRANSACTION DEPOSIT DEPOSITO WITHDRAWAL RETIRO SALE PURCHASE CHARGE NOMINA '
                           'REFERENCIA CONCEPTO FACTURA ADJUSTMENT PRESTAMO FINIQUITO AGUINALDO BONO QUINCENA SUELDO SALARIO VIATICOS '
                           'ZELLE VENMO'.split())
_CONCEPT_ANY = frozenset('PAYMENT PAYMENTS PMT PYMT FEE MENSUALIDAD COLEGIATURA ANTICIPO REFUND CANCELLED CANCELED'.split())


# Common given names (Spanish and English). Where a layout runs a free-text concept and a name together,
# a person is recognised only by opening with one of these; a company only by its legal form or a word
# that only names companies. Anything else is left unnamed rather than guessed.
_GIVEN_NAMES = frozenset("""
    AARON ABEL ABRAHAM ADA ADAN ADOLFO ADRIAN ADRIANA AGUSTIN ALAN ALBA ALBERTO ALEJANDRA ALEJANDRO ALFONSO ALFREDO ALICIA
    ALMA ALONSO ALVARO AMADO AMALIA AMPARO ANA ANABEL ANDREA ANDRES ANGEL ANGELA ANGELICA ANTONIA ANTONIO ARACELI ARIEL
    ARMANDO ARTURO AURORA AXEL BEATRIZ BENITO BENJAMIN BERENICE BERNARDO BLANCA BRANDON BRENDA BRUNO CAMILA CANDELARIO
    CARLA CARLOS CARMEN CAROLINA CATALINA CECILIA CELIA CESAR CHRISTIAN CINTHIA CLARA CLAUDIA CRISTIAN CRISTINA CRISTOBAL
    CYNTHIA DAMIAN DANIEL DANIELA DARIO DAVID DIANA DIEGO DOLORES DOMINGO DULCE EDGAR EDITH EDUARDO EFRAIN ELENA ELIAS
    ELISA ELIZABETH ELSA ELVIRA EMILIA EMILIO EMMANUEL ENRIQUE ERIC ERICK ERIKA ERNESTO ESPERANZA ESTEBAN ESTELA EUGENIO
    EVA EVER FABIAN FABIOLA FATIMA FELIPE FELIX FERNANDA FERNANDO FIDEL FLOR FRANCISCA FRANCISCO GABRIEL GABRIELA GENARO
    GEORGINA GERARDO GERMAN GILBERTO GLORIA GONZALO GRACIELA GREGORIO GUADALUPE GUILLERMO GUSTAVO HECTOR HERIBERTO HILDA
    HORACIO HUGO HUMBERTO IGNACIO IRENE IRMA ISAAC ISABEL ISAIAS ISMAEL ISRAEL IVAN JACINTO JAIME JAVIER JESICA JESSICA
    JESUS JOAQUIN JOEL JORGE JOSE JOSEFINA JOSUE JUAN JUANA JULIA JULIAN JULIO KARINA KARLA LAURA LAZARO LEONARDO LEONEL
    LETICIA LILIA LILIANA LORENA LORENZO LOURDES LUCIA LUIS LUISA LUZ MANUEL MANUELA MARCO MARCOS MARGARITA MARIA MARIANA
    MARIANO MARIO MARISOL MARTA MARTHA MARTIN MATEO MAURICIO MAXIMILIANO MAYRA MELISSA MERCEDES MIGUEL MIRIAM MOISES
    MONICA NANCY NATALIA NELSON NESTOR NICOLAS NOE NOEMI NORA NORMA OCTAVIO OFELIA OLGA OMAR ORLANDO OSCAR OSWALDO
    PABLO PAOLA PATRICIA PAULA PAULINA PEDRO PILAR RAFAEL RAMIRO RAMON RAQUEL RAUL REBECA REYNA RICARDO RIGOBERTO ROBERTO
    ROCIO RODOLFO RODRIGO ROGELIO ROLANDO ROMAN ROSA ROSARIO RUBEN RUTH SALVADOR SAMUEL SANDRA SANTIAGO SARA SAUL
    SEBASTIAN SERGIO SILVIA SOFIA SONIA SUSANA TERESA TOMAS ULISES URIEL VALENTIN VALERIA VERONICA VICENTE VICTOR
    VICTORIA VIRGINIA VLADIMIR WALTER XOCHITL YESENIA YOLANDA ZOILA
    ADAM AMY ANDREW ANN ANTHONY BRIAN CHARLES CHRISTOPHER DONALD EMILY GEORGE JAMES JANE JASON JENNIFER JOHN JOSEPH
    KAREN KEVIN LINDA LISA MARK MARY MATTHEW MICHAEL NANCY PAUL RICHARD ROBERT SARAH STEVEN SUSAN THOMAS WILLIAM
""".split())
_LEGAL_FORM = re.compile(r'\b(?:S\.?\s?A\.?(?:\s?(?:P\.?\s?I|B)\.?)?|S\s?DE\s?R\.?\s?L|S\.?\s?C|A\.?\s?C|S\.?\s?P\.?\s?R|INC|LLC|LTD|CORP)\.?'
                         r'(?:\s*(?:DE|D\s?E)\s*(?:C\.?\s?V?\.?|R\.?\s?L\.?))?\s*$|\bDE\s+C\.?\s?V\.?$|\bS\s?DE\s?R\.?\s?L\b')
_COMPANY_WORDS = re.compile(r'\b(?:GRUPO|CORPORAT\w*|COMERCIALIZADORA|CONSTRUCTORA|DISTRIBUIDORA|ARRENDADORA|INMOBILIARIA|'
                            r'FINANCIAL|FINANCIERA|LEASIN\w*|CONSULTORES|LABORATORIOS)\b')


_PAYMENT_CONCEPT = re.compile(r'\b(?:PAGO|PAGOS|ABONO|ANTICIPO|SALDO|RENTA|MENSUALIDAD|PRIMER|PRIMERO|SEGUNDO|TERCER|TERCERO|'
                              r'FACTURA|CUOTA|PARCIAL|FINIQUITO|NOMINA|LIQUIDACION|ENGANCHE|COLEGIATURA|INSCRIPCION|REEMBOLSO)\b')


def party_shaped(name):
    """True when a name taken from free text has the shape of a party: a company by its legal form or a
    word that only names companies, or a person opening with a common given name (after an optional initial)."""
    text = normalized(name)
    # Payment wording inside the text (SEGUNDO PAGO, ANTICIPO) makes it a concept, whatever its other words.
    if _PAYMENT_CONCEPT.search(text):
        return False
    words = text.split()
    if not words or words[0] in _ADDRESS_FIRST or words[-1] in _MX_STATES or place_name(text) or bank_name(text):
        return False
    legal = _LEGAL_FORM.search(text)
    if legal:
        # The words before the legal form must hold a name, not only a concept, period or place (BONO SC, CDMX AC).
        before = re.sub(r'[^A-Z0-9& ]', ' ', text[:legal.start()]).split()
        return bool(before) and not all(w in _NOT_NAME_WORDS for w in before) and not place_name(' '.join(before))
    company = _COMPANY_WORDS.search(text)
    if company:
        # A company word names a company after a name (TOYOTA FINANCIAL) or before one (GRUPO BIMBO), not as the
        # opening of a phrase (GRUPO DE TRABAJO).
        before = text[:company.start()].split()
        after = text[company.end():].split()
        if before:
            return not all(w in _NOT_NAME_WORDS for w in before) and not place_name(' '.join(before))
        return bool(after) and after[0] not in _NOT_NAME_WORDS and not all(w in _NOT_NAME_WORDS for w in after)
    if words and len(words[0]) == 1:
        words = words[1:]
    return 2 <= len(words) <= 6 and words[0] in _GIVEN_NAMES and all(re.fullmatch(r"[A-Z][A-Z'\-]*", w) for w in words)


# Generic payment, concept and place words: a merchant or payee name made only of these is a description of
# the payment (CREDIT CARD, CAR LOAN, ELECTRIC BILL), not who it is with.
_GENERIC_WORDS = frozenset("""
    PAYMENT PAYMENTS PMT PYMT PAY BILL BILLS CARD CREDIT DEBIT LOAN CAR AUTO HOME MORTGAGE RENT TAX TAXES PAYROLL
    INSURANCE PREMIUM ELECTRIC WATER GAS UTILITY UTILITIES PHONE MOBILE INTERNET CABLE WEB ONLINE TRANSFER DIRECT
    MONTHLY QUARTERLY ANNUAL WEEKLY FEE FEES SERVICE SERVICES CHARGE PURCHASE SALE REFUND RETURN DEPOSIT WITHDRAWAL
    PENDING AUTHORIZATION AUTH CC ACH CASH CHECK STORE SHOP MARKET NEW SAN SANTA ST SAINT NORTH SOUTH EAST WEST CITY
    TOWN COUNTY YORK THE AND OF FOR TO
""".split())


def generic_words_only(name):
    words = [w for w in re.sub(r'[^A-Z0-9 ]', ' ', normalized(name)).split() if not w.isdigit()]
    return not words or all(w in _GENERIC_WORDS or w in _STATES for w in words)


def concept_or_place(name, place=True, anywhere=True):
    """True when a captured name is the payment's concept, a street address or (with ``place``) a place, not a party.

    Used by the layout rules whose name field can also hold a concept or a place."""
    words = re.sub(r'[^A-Z0-9&\- ]', ' ', normalized(name)).split()
    if not words:
        return True
    if words[0] in _CONCEPT_FIRST or (anywhere and any(w in _CONCEPT_ANY for w in words)):
        return True
    # A street number opening the name (123 MAIN), or a street word (AV REFORMA, CALLE 5 DE MAYO), is an address.
    if re.fullmatch(r'\d+', words[0]) or words[0] in _ADDRESS_FIRST:
        return True
    # A town and its state (ANYTOWN TX, SAN FRANCISCO CA) with nothing else is where, not who.
    if not place:
        return False
    if words[-1] in _STATES and len(words) <= 3:
        return True
    return ' '.join(words) in _PLACES or place_name(' '.join(words))


# A transfer's own layout opening: wording found later in it (a concept saying COMISION) is not the bank's charge.
TRANSFER_OPENING = re.compile(r'^(?:\S{1,3}\s+\d{2}/[A-Z]{3}\s+)?(?:\d+\s+)?(?:[A-Z0-9]{2,3}\s+)?(?:(?:ABONO|CARGO|PAGO)\s+(?:POR\s+)?TRANSFERENCIA\b|'
                              r'SP(?:ID|E\S?)\s+(?:ENVIADO|RECIBIDO)|TRASPASO A TERCEROS\b|(?:ENVIO|RECEPCION)\s+SP(?:EI|ID)\b)')


# Rules that read a transfer's own name field. Only these may replace a charge
# or interest suggestion made from wording found elsewhere in the description
# (a transfer whose concept text says COMISION is still a transfer).
TRANSFER_RULES = frozenset({'own-account-transfer', 'returned-transfer-party', 'cashier-cheque-payee', 'bbva-sit-payer',
                            'tax-authority-payee', 'social-security-payee', 'brokerage-party', 'spei-cliente-party', 'spei-delimited-party', 'monex-named-party', 'bbva-transfer-party',
                            'third-party-account', 'zelle-party', 'credit-union-transfer-party', 'ach-company',
                            'named-payment-party', 'bill-payee', 'service-payee'})


def printed_party(raw, *, direction, account_type=None):
    """(name, rule, explanation) of the other side printed in the description, or None."""
    if account_type == 'credit_card' or not raw or not raw.strip():
        return None
    # Descriptions are at most a few thousand characters; a longer one is read from its start.
    raw = raw[:3000]
    value = normalized(raw)
    # BBVA reprints its posting date ahead of some lines (=: 04/DIC P31 .., 15/SEP_ BT3 ..).
    value = strip_date_prefix(value)
    # A name printed in a transfer's own field comes first; own-account wording applies only when none is printed.
    for rule in (_mx_named_lines, _santander_spei, _santander_returned, _delimited_spei, _monex_transfer, _bbva_spei,
                 _bbva_third_party_account, _mx_payee, _us_ach_company, _us_named_transfer,
                 _us_card_merchant, _us_bar_line, _own_account):
        found = rule(raw, value, direction)
        if found:
            name, rule_id, explanation = found
            if rule_id in ('third-party-account', 'own-account-transfer', 'tax-authority-payee', 'social-security-payee'):
                return found
            name = clean_name(name)
            if plausible_name(name):
                return (name if rule_id == 'debit-card-merchant' else _as_printed(name, raw)), rule_id, explanation
            return None
    return None


def strip_date_prefix(value):
    """The normalised description without a reprinted posting date and stray marks before the bank's code."""
    value = re.sub(r'^[\W_]*\d{2}\s*[/I]\s*I?[A-Z]{3}[\W_]*(?=[A-Z0-9]{2,4}\s)', '', value)
    # A code read with a stray mark (_WO01, $40 for S40).
    return re.sub(r'^[_=\-—:.\s]+(?=[A-Z]{1,2}[O0]?\d{1,2}\s)|^\$(?=\d{2}\s)', '', value)


def _as_printed(name, raw):
    """The name with the accents and capitals the statement prints (rules read an unaccented upper-case copy)."""
    folded, at = [], []
    for i, c in enumerate(raw):
        for b in (' ' if c.isspace() else ''.join(x for x in unicodedata.normalize('NFKD', c) if not unicodedata.combining(x)).upper()):
            folded.append(b)
            at.append(i)
    # The name field follows the layout's other wording, so its last printing is the field itself.
    found = [*re.finditer(r'(?<![A-Z0-9])' + r'\s+'.join(re.escape(w) for w in name.upper().split()) + r'(?![A-Z0-9])', ''.join(folded))]
    found = found[-1] if found else None
    return ' '.join(raw[at[found.start()]:at[found.end() - 1] + 1].split()) if found else name


_UNVERIFIED_NOTE = ' The bank marks this name as not verified by it; check ownership separately.'


def _santander_spei(raw, value, direction):
    # PAGO TRANSFERENCIA SPEI HORA .. ENVIADO A <bank> A LA CUENTA <clabe> AL CLIENTE <name> (1) (1) DATO NO ...
    # ABONO TRANSFERENCIA SPEI HORA .. RECIBIDO DE <bank> DE LA CUENTA <clabe> DEL CLIENTE <name> CLAVE DE RASTREO ..
    if re.match(r'^(?:\d+\s+)?ABONO TRANSFERENCIA TEF RECIBIDO DE\b', value):
        value = value.replace(' TEF RECIBIDO DE', ' TEF HORA RECIBIDO DE', 1)
    sent = re.search(r'\bENVIADO A\s+.+?\s+A\s?LA CUENTA\s+[\d ]+?\s+(?:[^A-Z0-9\s]+\s+)?AL CLIENTE\s+(.+)$', value)
    got = re.search(r'\bRECIBIDO DE\s+.+?\s+DE LA CUENTA\s+[\d ]+?\s+DEL CLIENTE\s+(.+)$', value)
    match = sent if direction == 'debit' else got
    if not match or not re.search(r'\b(?:SPE\S?|SPID|TEF)\s+HORA\b', value):
        return None
    name = re.split(r'\s*[({]\s*[1lI7]\s*[)}]|\s+DATO\s+NO\b|\s+(?:CLAVE\s+)?DE\s+RASTREO\b|\s+RASTREO\b|\s+REF\s+\d|\s+CONCEPTO\b|\s+RFC\b', match[1])[0]
    role = 'beneficiary' if direction == 'debit' else 'sender'
    return name, 'spei-cliente-party', (f'The {role} printed after “{"AL" if direction == "debit" else "DEL"} CLIENTE” in the '
                                        'transfer description; the bank and account are separate fields.'
                                        + (_UNVERIFIED_NOTE if 'NO VERIFICADO' in value else ''))


def _delimited_spei(raw, value, direction):
    # ENVIO SPEI <bank> | <name> DATO NO VERIFICADO .. | <clabe> | ..   (Intercam, Kapital)
    # RECEPCION SPEI | <bank> | <name> DATO NO VERIFICADO .. | <clabe> | ..
    # ENVIO SPEI <bank> <name> <clabe> <concept> ..   (the same layout printed without separators)
    match = re.match(r'^(?:\d+\s+)?(ENVIO|RECEPCION)\s+SP(?:EI|ID)\b\s*(.*)$', value)
    if not match or (match[1] == 'ENVIO') != (direction == 'debit'):
        return None
    rest = match[2]
    note = _UNVERIFIED_NOTE if re.search(r'NO\s+I?\s*VERIFICADO', rest) else ''
    role = 'beneficiary' if direction == 'debit' else 'sender'
    explanation = f'The {role} printed in the name field of the transfer description; the bank and account are separate fields.' + note
    if '|' in rest:
        # ENVIO prints its bank before the first bar, RECEPCION after it: either
        # way the second non-empty field is the other side's name.
        fields = [f.strip() for f in rest.split('|') if f.strip()]
        if len(fields) > 1 and not re.search(r'\d{10,}', fields[1]):
            return fields[1], 'spei-delimited-party', explanation
        return None
    for bank in _MX_BANKS:
        if rest.startswith(bank + ' '):
            tail = re.match(r'(.+?)\s+(?:CLABE\s+)?\d{17,19}\b', rest[len(bank) + 1:])
            if tail:
                return tail[1], 'spei-delimited-party', explanation
            return None
    return None


def _monex_transfer(raw, value, direction):
    if direction == 'debit':
        match = (re.search(r'\bNOMBRE BENEFICIARIO\s*:\s*(.+?)\s+(?:CLAVE DE RASTREO|REFERENCIA|CONCEPTO|RFC)\b', value)
                 or re.search(r'\bBENEFICIARIO\s+(.+?),\s*(?:CONCEPTO|REF)\b', value)
                 or re.match(r'^RETIRO BENEFICIARIO\s+(.+?)\s+(?:RFC\s*:|BANCO\s)', value))
        role = 'beneficiary'
    else:
        match = re.search(r'\bNOMBRE DEL ORDENANTE\s*:\s*(.+?)\s+(?:CLAVE DE RASTREO|REFERENCIA|CONCEPTO)\b', value)
        role = 'ordering party'
    if not match:
        return None
    return match[1], 'monex-named-party', f'The {role} printed in its own labelled field of the transfer description; the receiving or sending bank is a separate field.'


_BBVA_SPEI = re.compile(r'^(?:\S{1,3}\s+\d{2}/[A-Z]{3}\s+)?[A-Z0-9]{2,3}\s+SP(?:ID|E\S?)\s+(ENVIADO|RECIBIDO)\s*(.*)$')


def _bbva_spei(raw, value, direction):
    # T17 SPEI ENVIADO <bank> <7 digits><concept> Ref. <10 digits> <bank code> <clabe> <tracking> <name>
    match = _BBVA_SPEI.match(value)
    if not match or (match[1] == 'ENVIADO') != (direction == 'debit'):
        return None
    role = 'beneficiary' if direction == 'debit' else 'ordering party'
    after_ref = re.search(r'\bREF\.\s*\d{6,}\s+\d{3}\b\s*(.*)$', match[2])
    if after_ref:
        tokens = after_ref[1].replace('|', ' ').split()
        # Account, tracking key and other references come first; the name follows them.
        while tokens and (re.search(r'\d', tokens[0]) and len(tokens[0]) >= 5 or re.fullmatch(r'\d+', tokens[0])):
            tokens.pop(0)
        # A further long reference inside what is left ends the reference block.
        for index in range(len(tokens) - 1, -1, -1):
            if re.search(r'\d{8,}', tokens[index]) or re.fullmatch(r'(?=(?:\D*\d){3})[A-Z0-9]{10,}', tokens[index]):
                tokens = tokens[index + 1:]
                break
        if tokens:
            return ' '.join(tokens), 'bbva-transfer-party', f'The {role} printed after the account and tracking references; the bank named first carries the transfer and is not taken as the party.'
        return None
    # Without the Ref. block, an account or tracking number of 15 or more digits still ends the references.
    tail = re.search(r'\b\d{15,}\s+([^\d]+)$', match[2])
    if tail:
        return tail[1], 'bbva-transfer-party', f'The {role} printed after the account and tracking references; the bank named first carries the transfer and is not taken as the party.'
    # Without any reference the concept and name run together. A payroll concept with its date or
    # fortnight (NOMINA 150125, NOMINA 1A QNA ENE25) ends at a fixed place, so what follows is the name slot.
    fixed = (re.match(r'^.+?\s\d{7}NOMINA\s+\d{6}\s+(.+)$', match[2])
             or re.match(r'^\S+(?:\s\S+)?\s\d{7}NOMINA\s+\d?\S{1,3}\s+QNA\s+[A-Z]{3,5}\s?\d{2}\s+([A-Z][A-Z.]+(?:\s+[A-Z][A-Z.]+){1,5})$', match[2]))
    if fixed and not re.search(r'\d', fixed[1]) and not generic_words_only(fixed[1]):
        return fixed[1], 'bbva-transfer-party', f'The {role} printed after the payroll concept and its date; the bank named first carries the transfer and is not taken as the party.'
    # Other concepts are free text of any length; the name is taken only when it has the shape of a party.
    short = (re.match(r'^\S+(?:\s\S+)?\s\d{7}(?:FINIQUITO|PENSION|GTOS A COMPROBAR|AGUINALDO|VACACIONES|'
                      r'PRESTAMO(?: PERSONAL)?|LIQUIDACION)\s+([A-Z][A-Z.]+(?:\s+[A-Z][A-Z.]+){1,5})$', match[2])
             or re.match(r'^\S+(?:\s\S+)?\s\d{7}PAGO\s+(?:F|FACT|FACTURA|COT)\.?\s+\S*\d\S*\s+([A-Z][A-Z ]+?\s(?:SA|S\.A\.|S DE RL|SAPI|SC|AC)(?:\s+DE\s+CV)?)$', match[2])
             # A payroll or invoice concept, its reference (holding a digit), then the name to the end of the line.
             or re.match(r'^\S+(?:\s\S+)?\s\d{7}(?:NOMINA|AGUINALDO|PTU|FINIQUITO|(?:PAGO|SALDO|ABONO|AB)(?:\s+A\s+CTA)?\s+(?:F|FA|FACT|FACTURA)|COT)\.?\s+'
                         r'\S*\d\S*\s+((?!(?:EQ|DISP|CAMION|SELLOS|CONCRETO)\s)[A-Z][A-Z]+(?:\s+[A-Z][A-Z]*){1,5})$', match[2]))
    if short and not re.search(r'\d', short[1]) and party_shaped(short[1]):
        return short[1], 'bbva-transfer-party', f'The {role} printed after the payroll concept and its date; the bank named first carries the transfer and is not taken as the party.'
    return None


def _bbva_third_party_account(raw, value, direction):
    # N06 PAGO CUENTA DE TERCERO BNET <10-digit account> <concept> Ref. ..: only the account is printed.
    # Also: N06 PAGO CUENTA DE TERCERO CUENTA: <account> BNET; (BE)TRASPASO A CUENTA: <account> (Intercam, Kapital);
    # N05 PAGO TARJETA DE TERCEROS CUENTA: <card>; E17 ORDEN DE PAGO EXTRANJERO ORDENANTE: /<account>.
    match = (re.match(r'^[A-Z][\dO]\d\s+PAGO CUENTA DE TERCERO\s+(?:BNET\s+|CUENTA\s*:\s*)(\d{10})\b', value)
             or (re.search(r'\bTRASPASO DE FONDOS DEL CONTRATO\s+(\d{6,})\b', value) if direction == 'credit' and value.startswith('DEPOSITO EN CTA') else None)
             or (re.match(r'^(?:\d+\s+)?\(BE\)\s*TRASPASO A CUENTA\s*:\s*(\d{10,18})$', value) if direction == 'debit' else None)
             or (re.match(r'^[A-Z]\d{2}\s+PAGO TARJETA DE TERCEROS\s+CUENTA\s*:\s*(\d{15,16})\b', value) if direction == 'debit' else None)
             or (re.match(r'^[A-Z]\d{2}\s+ORDEN DE PAGO EXTRANJERO\s+ORDENANTE\s*:\s*/?(\d{6,})\b', value) if direction == 'credit' else None))
    if match:
        return (f'Account {match[1]} (no name printed)', 'third-party-account',
                'The statement prints only the other account’s number for this transfer, not a name. It is shown so payments to and from the same account can be followed; it does not identify the holder.')
    return None


_OWN_NOTE = (' The statement describes this as a transfer between the holder’s own accounts; it is shown so the money can be '
             'followed between them.')


def _clabe(digits):
    """True when 18 digits pass the CLABE control digit (weights 3, 7, 1), so a certificate or tracking number is not taken for an account."""
    # Its first three digits are the bank's code (002 Banamex, 012 BBVA, 014 Santander ..); none starts 000.
    if not re.fullmatch(r'\d{18}', digits) or not 2 <= int(digits[:3]) <= 699:
        return False
    total = sum(int(d) * w % 10 for d, w in zip(digits[:17], [3, 7, 1] * 6))
    return (10 - total % 10) % 10 == int(digits[17])


def _own_number(value):
    """The own account's number printed in the line: after CUENTA, or a valid CLABE (BBVA prints it with two leading zeros)."""
    found = re.search(r'\bCUENTA\s*:?\s*(\d{10,18})\b', value)
    if found:
        return found[1]
    # Fiscal receipt text (certificate numbers, UUIDs) that a statement prints after a line is not an account.
    value = re.split(r'\bINFORMACION FISCAL\b|\bUUID\b|\bCERTIFICADO\b', value)[0]
    for found in re.finditer(r'\b0{0,2}(\d{18})\b', value):
        if _clabe(found[1]):
            return found[1]
    return None


def _own_account(raw, value, direction):
    """Transfers the statement itself describes as between the holder's own accounts."""
    cue = 'TO' if direction == 'debit' else 'FROM'
    # A line whose own wording says it was sent (or received) is not read in the other direction.
    sent = re.match(r'^(?:\d+\s+)?(?:ENVIO\b|\S{1,4}\s+SP\S{1,3}\s+ENVIADO\b|(?:\d+\s+)?(?:CARGO|PAGO)\s)', value)
    received = re.match(r'^(?:\d+\s+)?(?:RECEPCION\b|\S{1,4}\s+SP\S{1,3}\s+RECIBIDO|(?:\d+\s+)?ABONO\s)', value)
    if (sent and direction != 'debit') or (received and direction != 'credit'):
        return None
    # Santander / BBVA: TRASPASO (ENTRE) CUENTAS PROPIAS | CTAS PROPIAS [CUENTA: <acct>] [<clabe>]
    if re.search(r'TRASPASO\s+(?:ENTRE\s+)?(?:CUENTAS|CTAS)\s+PROPIAS\b', value) and not re.search(r'\bAL CLIENTE\b|\bDEL CLIENTE\b', value):
        number = _own_number(value)
        label = f'Own account …{number[-4:]}' if number else 'Own account (number not printed)'
        return label, 'own-account-transfer', 'The description says “cuentas propias”.' + _OWN_NOTE
    # Andrews: Withdrawal|Deposit [Online|Mobile Banking] Transfer To|From Share 0010 | Loan ####0001
    match = re.match(rf'^(?:WITHDRAWAL|DEPOSIT)\s+(?:(?:ONLINE|MOBILE) BANKING\s+)?TRANSFER\s+{cue}\s+(SHARE|LOAN)\s+[#X]*(\d{{2,}})\b', value)
    if match and value.startswith('WITHDRAWAL' if direction == 'debit' else 'DEPOSIT'):
        label = f'Own share account {match[2]}' if match[1] == 'SHARE' else f'Own loan account …{match[2][-4:]}'
        return label, 'own-account-transfer', 'The credit union prints this as a transfer between the member’s own share or loan accounts.' + _OWN_NOTE
    # Truist: TRUIST ONLINE TRANSFER ONLINE TO|FROM ****0001- ; TRUIST DEPOSIT TRANSFER MOBILE TO ****0002-
    match = re.match(rf'^TRUIST (?:ONLINE|DEPOSIT) TRANSFER (?:ONLINE|MOBILE) {cue} \*+(\d{{4}})\b', value)
    if match:
        return f'Own account ****{match[1]}', 'own-account-transfer', 'Truist prints this as an online transfer between the customer’s own accounts.' + _OWN_NOTE
    # Truist: AUTO OVERDRAFT TRANSFER ACCOUNT NUMBER <linked account>
    match = re.match(r'^AUTO OVERDRAFT TRANSFER ACCOUNT NUMBER (\d{6,})\b', value)
    if match:
        return f'Own account …{match[1][-4:]}', 'own-account-transfer', 'An automatic overdraft transfer moves money between accounts the customer linked for overdraft cover.' + _OWN_NOTE
    # BBVA: E57 TRASPASO ENTRE CUENTAS FOLIO .. ; C09 TRASPASO ENTRE CUENTAS DE LA CUENTA <account>
    if re.match(r'^[A-Z]\d{2}\s+TRASPASO ENTRE CUENTAS\b', value):
        number = _own_number(value)
        return (f'Own account …{number[-4:]}' if number else 'Own account (number not printed)'), 'own-account-transfer', \
            'The description says “traspaso entre cuentas”.' + _OWN_NOTE
    return None


def _santander_returned(raw, value, direction):
    # ABONO POR DEVOLUCIONES SPEI HORA .. DEVUELTO POR <bank> CUENTA <clabe> CLIENTE <name> CLAVE DE RASTREO .. CAUSA DEVOLUCION ..
    match = re.search(r'\bDEVUELTO POR\s+.+?\s+CUENTA\s+\d+\s+CLIENTE\s+(.+?)(?:\s+CLAVE DE RASTREO\b|\s+CAUSA\b|$)', value)
    if direction == 'credit' and match and re.match(r'^(?:\d+\s+)?ABONO POR DEVOLUCIONES\b', value):
        return match[1], 'returned-transfer-party', ('The account holder printed as “CLIENTE” on this returned transfer: the earlier '
                                                    'payment to them came back. The returning bank is a separate field.')
    return None


def _mx_named_lines(raw, value, direction):
    """Mexican lines that print the other side in a fixed place."""
    # Federal tax paid by electronic transfer: the payee is the tax authority (SAT).
    if direction == 'debit' and re.match(r'^(?:\d+\s+)?CGO IMPTO FED\b', value):
        return ('SAT (Servicio de Administración Tributaria)', 'tax-authority-payee',
                'The description says “cargo impuesto federal”: a federal tax payment, which is paid to the tax authority (SAT).')
    # Employer social-security contributions are collected by IMSS (with the INFONAVIT and retirement shares).
    if direction == 'debit' and re.match(r'^(?:\d+\s+)?PAGO CUOTAS PATRONALES\b', value):
        return ('IMSS (employer social-security contributions)', 'social-security-payee',
                'The description says “pago cuotas patronales”: employer social-security contributions, collected by IMSS '
                '(including the INFONAVIT and retirement shares).')
    # BBVA cashier's cheque bought for a named payee: C61 COMPRA CHEQUE DE CAJA <payee> Ref. ..
    match = re.match(r'^[A-Z]\d{2}\s+COMPRA CHEQUE DE CAJA\s+(.+?)(?:\s+REF(?:\.|\b).*)?$', value)
    if match and direction == 'debit' and party_shaped(match[1]):
        return match[1], 'cashier-cheque-payee', 'The payee printed on this cashier’s cheque purchase.'
    # BBVA SIT receipts: TJ3 SITH<ref> <payer, fixed width><agreement> Ref. ..
    match = re.match(r'^T[A-Z0-9]\d\s+SIT[A-Z]\d{6,}\s+(.+?)\s*\d{5,}\s+REF\.', value)
    if match and direction == 'credit' and party_shaped(match[1]):
        return match[1], 'bbva-sit-payer', 'The payer printed after the SIT reference on this collection; its agreement number and reference follow it.'
    # BBVA collections for a leasing company: Z3 CARGO COBRANZA <company> Ref. ..
    match = re.match(r'^Z\d{1,2}\s+CARGO COBRANZA\s+([A-Z][A-Z .&]+?)\s+REF\.', value)
    if match and direction == 'debit' and party_shaped(match[1]):
        return match[1], 'bbva-direct-debit-payee', 'The company collecting this charge, printed after “cargo cobranza”.'
    # BBVA Leasing invoices: Z32 BBVA LEASING PAGO FACTURA ..
    if direction == 'debit' and re.match(r'^[A-Z]\d{2}\s+BBVA LEASING\b', value):
        return 'BBVA Leasing', 'bbva-cie-payee', 'The leasing company printed at the start of this invoice payment.'
    # Intercam: RECEPCION SPEI | CB INTERCAM | DATO NO VERIFICADO ..: the sender is Intercam's brokerage (casa de bolsa).
    if direction == 'credit' and re.match(r'^RECEPCION SPEI\s*\|\s*CB INTERCAM\s*\|', value):
        return 'CB Intercam (Intercam Casa de Bolsa)', 'brokerage-party', 'The sender field prints “CB INTERCAM”, Intercam’s brokerage (casa de bolsa).'
    return None


def _mx_payee(raw, value, direction):
    if direction != 'debit':
        return None
    # DOMICILIACION PAGO SERVICIO <contract> RFC <rfc> COBRO <amount> <payee>
    match = (re.search(r'\bDOMICILIACION PAGO SERVICIO\b.*\bCOBRO\d?\s+[\d,.]+\s+(.+)$', value)
             or re.search(r'\bDOMICILIACION PAGO SERVICIO\b.*\d\s*COBRO\s+([A-Z][A-Z .&]+)$', value)
             or re.search(r'\bDOMICILIACION PAGO SERVICIO\s+\d+\s+RFC\s+\S+\s+\d+\s+[\d,]+\.\d{2}\s+([A-Z][A-Z .&]+)$', value))
    if match and party_shaped(match[1]):
        return match[1], 'direct-debit-payee', 'The company collecting this direct debit, printed after the amount collected.'
    match = re.search(r'\bDOMICILIACION PAGO SERVICIO\s+\d+\s+RFC\s+([A-Z&]{3,4}[0-9O]{6}[A-Z0-9]{3})$', value)
    if match:
        return (f'RFC {match[1]} (no name printed)', 'third-party-account',
                'The statement prints only the collecting company’s tax ID (RFC) for this direct debit, not its name. It is shown so payments to the same collector can be followed.')
    # CIE payments: P14 <payee> REF:<ref> CIE:<agreement>, or the payee alone.
    match = re.match(r'^P14\s+(.+?)(?:\s+REF\s*:.*\bCIE\s*:.*|\s+\d{7}\s+REF\.\s*GUIA\s*:.*)?$', value)
    if match and not re.search(r'\b(?:REF|CIE)\s*:', match[1]):
        return match[1], 'bbva-cie-payee', 'Payee printed before the REF and CIE references of this bill payment. It does not establish the ultimate beneficiary.'
    # P31/K08 direct debits print the collecting company first, then its references.
    match = re.match(r'^(?:P31|K08)\s+(.+)$', value)
    if match:
        words = []
        for token in match[1].split():
            if re.search(r'\d', token) or token in ('REF.', 'REF'):
                # The name field is fixed width; its last word can run into the reference (NAME12345).
                head = re.match(r'[A-Z]{3,}(?=\d)', token)
                if head and words:
                    words.append(head[0])
                break
            words.append(token)
        if len(words) >= 2:
            return ' '.join(words), 'bbva-direct-debit-payee', 'The company collecting this direct debit, printed before its references.'
    match = re.match(r'^(?:\d+\s+)?PAGO SERVICIO\s+([A-Z][A-Z .&]+)$', value)
    if match:
        return match[1], 'service-payee', 'The payee printed after “PAGO SERVICIO”.'
    if re.search(r'\bPAGO REFERENCIADO SAT\b', value):
        return 'SAT', 'tax-authority-payee', 'The description names the tax authority (SAT) as the payee of this referenced payment.'
    match = re.match(r'^[A-Z]\d{2}\s+(IMSS/INF/AFORE)\b', value)
    if match:
        return match[1], 'social-security-payee', 'The description names the social security institutes (IMSS, INFONAVIT, AFORE) paid through SIPARE.'
    return None


def _us_ach_company(raw, value, direction):
    # OCR splits the opening word (Wi thdrawal ACH ..).
    value = re.sub(r'^W\s?I\s?T\s?H\s?D\s?R\s?A\s?W\s?A\s?L\b', 'WITHDRAWAL', value)
    # Truist: ACH CORP DEBIT <company> PYMT|PAYMENT ..
    # Only the card processors named on these lines are taken; the slot otherwise holds the entry's own wording.
    match = re.match(r'^ACH CORP DEBIT\s+(?:(?:DISCOUNT|FEE|FEES)\s+)?(TRUIST MERCH SVC|FDMS)\b', value)
    if match and direction == 'debit':
        return match[1], 'ach-company', 'The company printed first on this ACH debit, before its entry wording.'
    # Andrews: Withdrawal ACH <name> TYPE: <type> ID: <id> CO: <company> [NAME: <person>] ACH Trace Number: ..
    match = re.match(r'^(?:WITHDRAWAL|DEPOSIT)\s+ACH\b.*?\bCO\s*:\s*(.+?)\s+(?:NAME\s*:|ACH TRACE|ENTRY CLASS|\.\s)', value)
    wanted = 'WITHDRAWAL' if direction == 'debit' else 'DEPOSIT'
    if match and value.startswith(wanted):
        return match[1], 'ach-company', 'The company name printed in the ACH “CO:” field of this payment.'
    return None


def _us_named_transfer(raw, value, direction):
    text = ' '.join(raw.split())
    cue = 'FROM' if direction == 'credit' else 'TO'
    for pattern, rule, explanation in [
        # Andrews: Withdrawal Online Banking Transfer To <SURNAME,GIVEN> XXXXXXXXXX Share 0040 ..
        (rf'^(?:WITHDRAWAL|DEPOSIT)\s+(?:ONLINE BANKING\s+)?TRANSFE\s?R\s+(?:\S+\s+){{0,5}}?{cue}\s+(?!LOAN\b|SHARE\b)(.+?)\s+X{{4,}}\b',
         'credit-union-transfer-party', 'The member printed as the other side of this credit union transfer; the masked account number is separate.'),
        (r'^WITHDRAWAL BILL PAYMENT BILL PR?AID-\s*(.+?)(?:\s+(?:CONF\b|CON\S?\s*#|#\s*\d).*)?$|'
         r'^(?:RECURRING )?WITHDRAWAL BILL PAYMENT #\d+\s+(.+?)(?:\s+(?:\d|\(\d).*)?$' if direction == 'debit' else r'(?!)',
         'bill-payee', 'The payee printed after “Bill Paid-”.'),
        # Navy Federal: Paid To - <payee> <type>; Payment To - <payee> <reference>; Deposit - ACH Paid From <payer> <ref>
        (r'^(?:PAID TO|PAYMENT TO|ACH PAID TO)\s*-?\s*(.+)$' if direction == 'debit' else r'^DEPOSIT\s*-\s*ACH PAID FROM\s+(.+)$',
         'named-payment-party', 'The party printed after “paid to” or “paid from” in the description.'),
        # Andrews: Deposit|Withdrawal Faster Payments ZEL* <name> <reference>
        (rf'^{"DEPOSIT" if direction == "credit" else "WITHDRAWAL"} FASTER PAYMENTS ZEL\*\s*(.+?)\s+\S*\d\S*$',
         'zelle-party', 'The person or business printed as the other side of this Zelle payment.'),
        # Andrews: Deposit Debit Card CASH APP*CASH OUT Visa Direct ..: money pushed from a payment app.
        (r'^DEPOSIT DEBIT CARD\s+(.+?)\s+VISA DIRECT\b|^DEPOSIT DEBIT CARD\s+(CASH APP\*[A-Z][A-Z ]*?)\*|^DEPOSIT DEBIT CARD\s+(PAYPAL\*[A-Z][A-Z ]*?)\s+SAN JOSE\b' if direction == 'credit' else r'(?!)',
         'card-push-payment-source', 'The payment app or sender printed on this Visa Direct card deposit; the person behind it is not printed.'),
        # Truist merchant card settlement: MC VI DEP TRUIST MERCH SVC <merchant name> ..
        (r'^MC VI DEP\s+(.+?\bMERCH SVC)\b' if direction == 'credit' else r'(?!)',
         'card-settlement-payer', 'The card processor printed as the payer of this card sales settlement.'),
        # Truist: VISA MONEY TRANSFER CREDIT|DEBIT <date> <place> <card> <sender or recipient>
        (r'^VISA MONEY TRANSFER (?:CREDIT|DEBIT)\s+\d{2}-\d{2}-\d{2}\s+.+?\s\d{4}\s+([A-Z][A-Z0-9 .&]+)$',
         'card-push-payment-source', 'The sender or recipient printed at the end of this Visa money transfer.'),
        # Truist: CD PREMIUM <insurer> <policy> ; RECURRING INTERNET PAYMENT CRCARDPMT <card issuer> <ref>
        (r'^CD PREMIUM\s+(.+?)\s+\S*\d' if direction == 'debit' else r'(?!)', 'ach-company', 'The insurer printed after “premium” on this debit.'),
        (r'^RECURRING INTERNET PAYMENT CRCARDPMT\s+(.+?)\s+\S*\d\S*$' if direction == 'debit' else r'(?!)', 'ach-company',
         'The card issuer printed as the payee of this card payment; the card account itself is not printed.'),
        (r'^CLOVER APP\s+(CLOVER APP MRKT)\b' if direction == 'debit' else r'(?!)', 'ach-company', 'The company printed first on this debit.'),
        # Navy Federal: POS Credit Adjustment <card> Transaction <date> <merchant> ..
        (r'^POS CREDIT ADJUSTMENT\s+\d{4}\s+TRANSACTION\s+\d{2}-\d{2}-\d{2}\s+(.+)$' if direction == 'credit' else r'(?!)',
         'debit-card-descriptor', 'Merchant as printed on this card refund or adjustment. It is not a verified legal identity; the original description remains available.'),
        # Zelle: ZELLE PAYMENT TO|FROM <name> PAYMENT ID ..
        (rf'^ZELLE PAYMENT\s+{cue}\s+(.+?)(?:\s+PAYMENT ID\b.*)?$', 'zelle-party', 'The person or business printed as the other side of this Zelle payment.'),
    ]:
        match = re.match(pattern, value)
        if match:
            name = next(group for group in match.groups() if group)
            if rule == 'card-push-payment-source' and re.search(r'\*\s*ID\b', name):
                return None
            if rule == 'card-push-payment-source' and name.startswith(('CASH APP*', 'PAYPAL*')) and 'VISA DIRECT' not in value:
                app, _, sender = name.partition('*')
                printed = re.search(re.escape(sender.strip()), text, re.I)
                return ('Cash App' if app == 'CASH APP' else 'PayPal') + ' (' + (printed[0] if printed else sender.strip()) + ')', rule, \
                    'The payment app and the sender name it prints on this card deposit.'
            if rule == 'debit-card-descriptor':
                name = re.split(r'\s+(?:\d{3,}|[A-Z]{2}\s+[A-Z]{2}$)', name)[0].rstrip(' *')
            if rule == 'bill-payee':
                # The payee ends before its phone (also a vanity number read badly, BOO-NAME), web address or state.
                name = re.split(r'\s+\d{3}-\d{3}-\d{4}\b|,|\s+(?:HTTPS?|WWW)\S*|\s+[B8][O0]{2}-\S+|\s+\S*\.COM/\S*', name)[0]
                # A processor's order or loan code after an asterisk, or digits glued to the last word, are references.
                head = re.split(r'[*•·]', name)[0].strip()
                name = head if re.search(r'[*•·]', name) and len(re.sub(r'[^A-Z]', '', head)) >= 3 else name
                name = re.sub(r'(?<=[A-Z])\d{4,}$', '', name)
                words = name.split()
                while len(words) > 1 and words[-1] in _STATES:
                    words.pop()
                name = ' '.join(words)
            if rule == 'named-payment-party':
                # The payee comes before the payment type, check or reference.
                name = re.split(r'\s+(?:MOBILE PMT|ONLINE PMT|CHECK PYMT|(?:ONLINE\s+)?PAYMENTS?\b|CHK\b|CK#|PYMT\b|PMT\b|ARC\b|\d)', name)[0]
            # The name fields of these layouts can also hold the payment's purpose or, on a Visa transfer, a place.
            if rule in ('bill-payee', 'card-push-payment-source', 'ach-company', 'debit-card-descriptor') \
                    and (concept_or_place(name, place=rule == 'card-push-payment-source', anywhere=rule != 'debit-card-descriptor')
                         or generic_words_only(name)):
                return None
            span = re.search(re.escape(name), text, re.I)
            return (text[span.start():span.end()] if span else name), rule, explanation
    return None


def _us_card_merchant(raw, value, direction):
    from services.financial.payment_inference import _card_tail, MERCHANTS
    # Truist: DEBIT CARD PURCHASE <merchant> #<store> <terminal> <date> ..: the merchant comes before the store number.
    store = re.match(r'^DEBIT CARD PURCHASE\s+(\S+(?:\s+\S+)?)\s+#\d{6}\b', value)
    if store and re.search(r'[A-Z]{2}', store[1]) and not concept_or_place(store[1]) and not generic_words_only(store[1]):
        return store[1], 'debit-card-descriptor', 'Merchant as printed on this debit card line, before its store number. It is not a verified legal identity; the original description remains available.'
    tail = _card_tail(value, direction) if not value.startswith(('|', '}', '~')) else None
    if tail is None:
        # Truist debit card lines that the category reader does not treat as purchases.
        other = re.match(r'^DEBIT CARD (?:RECURRING PYMT|MISC DEBIT|RETURN|CREDIT)\s+(.+)$', value)
        if not other:
            return None
        tail = other[1]
    # Truist PIN purchases print the place and card digits before the merchant.
    pin = re.match(r'^PURCHASE-PIN\s+\d{2}-\d{2}-\d{2}\s+.+?\s+\d{4}\s+(.+)$', tail)
    if pin:
        tail = pin[1]
    tail = re.sub(r'^(?:CREDIT VOUCHER\s+)?\d{2}/\d{2}\s+[0O]\s+\d{5,}\s+[0O]\s*', '', tail)
    # Authorisation digits read badly (B1234 0, ~1234 0, 000001OAA1 0) still end at the lone 0 before the merchant.
    tail = re.sub(r'^\S*\d\S*\s+[0O]\s+(?=[A-Z])', '', tail)
    # A terminal printed as its street address names no merchant (12345 - 100 MAIN ST ANYTOWN MD).
    if re.match(r'^(?:\d+\s+-\s+)?\d+\s+(?:[A-Z0-9]+\s+){1,2}(?:AV|AVE|ST|RD|BLVD|DR|PKWY|HWY|PL|WAY|LN|CT)\b', tail) or \
            re.search(r'(?:^|\s)\d+\s+-\s+\d+\s+(?:[A-Z0-9]+\s+){1,2}(?:AV|AVE|ST|RD|BLVD|DR|PKWY|HWY|PL|WAY|LN|CT)\b', tail):
        return None
    # Leading card, type and date words left by the bank's prefix (PURCHASE-PIN 01-01-24, RECURRING PYMT ..).
    while True:
        stripped = re.sub(r'^(?:PURCHASE(?:-PIN)?|REV AUTH|RECURRING|PYMT|MISC|DEBIT|RETURN|CARD|TRANSACTION|POS|ON|'
                          r'\d{2}[-/]\d{2}(?:[-/]\d{2,4})?|\d{3,}(?:\s+-)?|\.?[0O]{1,2}|\.\d+|\S*\d\S*(?=\s+[0O]\s+[A-Z])|\S?\d{1,2}(?=\s+[0O]\s)|[0O]+\d{3,}|(?=[\dIl]*\d{4})[\dIl]{6,})\s+', '', tail)
        if stripped == tail:
            break
        tail = stripped
    for pattern, merchant, _ in MERCHANTS:
        found = pattern.match(re.sub(r'^DD\s+(?=DOORDASH)', '', tail))
        if found:
            return merchant, 'debit-card-merchant', f'Merchant recognised from “{found[0]}” on this debit card line. This does not establish legal identity or ownership.'
    words = tail.split()
    kept = []
    for token in words:
        # Truist and Navy print the purchase date, then the place, after the merchant.
        if (re.fullmatch(r'\d{2}-\d{2}(?:-\d{2,4})?', token) or re.fullmatch(r'(?:\d{3}-?){2}\d{4}', token)
                or kept and re.fullmatch(r'\d{2}/\d{2}', token)):
            break
        # A store number or a reference code ends the merchant; the street or place follows it.
        if kept and (re.fullmatch(r'#?\d{3,}', token) or re.fullmatch(r'(?=(?:\D*\d){3})[A-Z0-9]{6,}', token)):
            break
        kept.append(token)
    while len(kept) > 1 and (kept[-1] in _STATES or re.fullmatch(r'\d{1,6}|#\d+|[\d\-]+', kept[-1])
                             or re.fullmatch(r'(?:HTTPS?|WWW)\S*|\S*\.(?:COM|NET|ORG)(?:/\S*)?\.?', kept[-1])):
        kept.pop()
    label = _without_place(' '.join(kept))
    label = re.sub(r'\s*#\s*\d+\b.*$', '', label)
    # A processor's order or reference code after the merchant (MERCHANT*1A2B3C4D5, SHOP* I01234-5678).
    label = re.sub(r'\s*\*\s*(?=\S*\d)\S{5,}$', '', label)
    label = re.sub(r'(?<=[A-Z])\s+(?=(?:\S*?\d){3})[A-Z0-9.\-]{4,}$', '', label).strip(' *-')
    # A payment processor's prefix is not the merchant (TST* EXAMPLE CAFE, SQ *COFFEE).
    label = re.sub(r'^(?:TST|SQ|IC|SP|PY|SPO)\s*\*\s*', '', label)
    if not re.search(r'[A-Z]{3}|^[A-Z]{2}/[A-Z]{2}$', label) or re.fullmatch(r'(?:DATE|CARD|DEBIT|PURCHASE|POS|TRANSACTION)(?:\s.*)?', label):
        return None
    # The card line's own prefix, read too badly to strip (W·ITHDRAWAL DEBIT CARD), is not a merchant.
    if re.search(r'THDRAWAL|DEBITCARD', re.sub(r'[^A-Z]', '', label)):
        return None
    span = re.search(re.escape(label).replace(r'\ ', r'\s+'), ' '.join(raw.split()), re.I)
    label = span[0] if span else label
    return label, 'debit-card-descriptor', 'Merchant as printed on this debit card line, with the card, date and place details removed. It is not a verified legal identity; the original description remains available.'


def _us_bar_line(raw, value, direction):
    # M&T prints each line after a bar: the merchant or ACH company, then its entry
    # wording and references (| EXAMPLEINSCO INSUR PREM, | SSA TREAS 310 XXSOC SEC).
    from services.financial.payment_inference import MERCHANTS
    match = re.match(r'^(?:[|}\]~]\s*)+(?:PIN\s*)?(?:RETURN-\s*)?(?:PURCHASE (?:WITH CASH BACK )?ON\s+\d{2}/\d{2}\s+)?(.+)$', value)
    if match:
        # OCR splits the debit card prefix after the bar (~Wi thdrawal Debit Card ..): read it as that card line.
        card = re.match(r'^\S{0,2}\s?I\s?T?\s?H\s?D\s?R\s?A\s?W\s?A\s?L\s+DEBIT CARD\s+(.+)$', match[1])
        if card:
            return _us_card_merchant(raw, 'WITHDRAWAL DEBIT CARD ' + card[1], direction) if direction == 'debit' else None
        if re.search(r'THDRAWAL|DEPOSIT', match[1].replace(' ', '')[:14]):
            return None
    if not match or re.match(r'(?:CHECK|ATM|INTEREST|LINE OF CREDIT|CREDIT LINE|MOBILE DEPOSIT|DEPOSIT|TRANSFER|ONLINE TRANSFER|'
                             r'OVERDRAFT|EFT PAYMENT|ADVANCE|WITHDRAWAL|NON-|M&T|WAIVE|REVERSE|COBRO|COMISION|IVA|SPEI|SEL|TRANSF\S*)\b', match[1]):
        return None
    tail = re.sub(r'^DD\s*\*?\s*(?=DOORDASH)', '', match[1])
    for pattern, merchant, _ in MERCHANTS:
        found = pattern.match(tail)
        if found:
            return merchant, 'debit-card-merchant', f'Merchant recognised from “{found[0]}” on this line. This does not establish legal identity or ownership.'
    words = []
    for token in tail.split():
        if (re.search(r'\d', token) or re.match(r'(?:HTTPS?|WWW)|\S*\.(?:COM|NET|ORG)\b', token)
                or token in ('PAYMENT', 'PAYMENTS', 'PYMT', 'PMT', 'PREM', 'COLL', 'EFT', 'WEB', 'BILL', 'BILLPAY', 'PURCHASE',
                             'AUTOMATIC', 'ACH', 'CHECK', 'INSUR', 'PMTS', 'ARC', 'PHONE', 'ONLINE', 'DEBIT', 'XXSOC')):
            # A word that runs into the store number keeps its letters (EXAMPLE HEIGH1234).
            head = re.match(r'[A-Z]{3,}(?=\d)', token)
            if head and words:
                words.append(head[0])
            break
        words.append(token)
    label = _without_place(' '.join(words))
    if not re.search(r'[A-Z]{2}', label):
        return None
    span = re.search(re.escape(label).replace(r'\ ', r'\s+'), ' '.join(raw.split()), re.I)
    return (span[0] if span else label), 'statement-line-payee', 'The merchant or company printed at the start of this line, before its payment wording and references. It is not a verified legal identity; the original description remains available.'


# Charges, interest, tax the bank withholds, its currency desk, its investment
# and repo products and its own credit lines: the statement bank is the other
# side. 'Leading' wording opens the description, so a fee for a transfer stays
# the bank's even when the transfer's beneficiary is printed after it.
_BANK_LEADING = re.compile(
    r'^(?:\d+\s+|[A-Z]{1,2}\d{1,2}\s*(?=[1I]\.S\.R)|[A-Z]{1,2}\d{1,2}\s+|(?:\|\s*)+)?(?:COM(?:ISION(?:ES)?)?\b(?!\.)(?!\s+FEDERAL DE ELECTRICIDAD)|ICOMISION\b|IVA\b|I\s?V\s?A\b|IVA-|'
    r'RETENCION\b|RET\.?\s*ISR\b|I\.?S\.?R\.?\s+RETENIDO\b|ABO(?:NO)? POR INTERESES\b|AB INTERESES\b|INTERESES\b|'
    r'PAGO INTERESES DE INV|INTEREST\s+(?:PAYMENT\b(?!\s+TO\b)|(?:CHARGED?|EARNED|PAID)\b)|DIVIDEND\s*$|SERV BANCA INTERNET\b|'
    r'COBRO DE COMISION|WITHDRAWAL DEBIT CARD FEE\b|DESCUENTO POR TIMBRADO|COBRO POR TIMBRADO|COMPENSACION POR RETRASO|REEMBOLSO OTRAS COMISIONES|'
    r'(?:[A-Z&-]+\s+)?ADD-ON FEE\b|WAIVE ADD-ON FEE\b|OVERDRAFT\b(?!.*\bTRANSFER\s+FROM\b)|NON-[A-Z&]+ ATM FEE\b|ATM FEE\b|SERVICE CHARGES?\b|'
    r'MAINTENANCE FEE\b|MONTHLY (?:SERVICE )?FEE\b|AUTHORIZED USER FEE\b|LATE FEE\b|ANNUAL FEE\b|FOREIGN TRANSACTION FEE\b|'
    r'COMPRA DE DIVISAS|VENTA DE DIVISAS|RETIRO POR COMPRA DE DIVISAS|DEPOSITO POR VENTA DE DIVISAS|'
    r'COMPRA\s*DE\s*REPORTO|COMPRADE\s*REPORTO|VENTA\s*DE\s*REPORTO|I?APERTURA DE INVERSION|DEPOSITO DE INVERSION|'
    r'PAGO CAP\.? DE INVERSION|VENCIMIENTO DE INVERSION|RETIRO PAGO CREDITO|'
    r'(?:VENTA|COMPRA|REASIGNACION) FONDOS\b|CAMBIOS/DERIVADOS\b|COMPENSACI.?N\b|COMPENSA SPEI\b|MORA SPE\S\b|PENALIZ SDO\b|REEMB OTRS COM\b|'
    r'ADMINISTRACION RENTA MEMBRESIA\b|DEPOSIT DIVIDEND\b|WITHDRAWAL PRIV(?:ILEGE)? PAY\b|WITHDRAWAL ATM W/D FEE\b|NO CHARGE POSITIVE AVAIL\b|'
    r'DAILY CAP OF \d+ FEES\b|TRANSACTION LESS THAN \$|WITHDRAWAL LIMIT FEE\b|[1I]\.S\.R\.\s+RETENIDO\b|'
    r'BONIFICACI\S*\s+COBRO\b|(?:CARGO|I?ABONO) A CUENTA\|[^|]*(?:COMPRA|VENDE|PAGA|RECIBE)\|DEAL\b|TIPO DE CAMBIO DE\b|LINE OF CREDIT PAYMENT\b|'
    r'RETIRO RETIRO DE FONDOS PARA TRANSFERENCIA :?TRASPASO A CR.DITO|DEPOSITO RECEPCION DE FONDOS POR TRANSFERENCIA :?TRASPASO DESDE CR.DITO)')
_BANK_PREFIX = r'^(?:\d+\s+|[A-Z]{1,2}\d{1,2}\s*(?=[1I]\.S\.R)|[A-Z]{1,2}\d{1,2}\s+|(?:\|\s*)+)?'
# Matched at the start of the description, after the bank's code or sequence number.
_BANK_KINDS = [
    (r'(?:COM(?:ISION(?:ES)?)?|ICOMISION|COBRO DE COMISION)\b', 'bank-charge', 'The description identifies a fee or commission charged by the statement bank; the bank name comes from the statement account.'),
    (r'(?:IVA|I\s?V\s?A\b|RETENCION|RET\.?\s*ISR|[1I]\.?S\.?R)', 'bank-tax-withheld', 'The description identifies tax the statement bank withholds or charges on its own service; the bank pays it on to the tax authority. The bank name comes from the statement account.'),
    (r'(?:ABO(?:NO)? POR INTERESES|AB INTERESES|INTERESES|PAGO INTERESES|INTEREST|DIVIDEND|DEPOSIT DIVIDEND)', 'bank-interest', 'The description identifies interest or dividends between the account and the statement bank; the bank name comes from the statement account.'),
    (r'.*(?:DIVISAS|CAMBIOS/DERIVADOS|\|DEAL\b|TIPO DE CAMBIO)', 'bank-currency-exchange', 'The description identifies a currency purchase or sale with the statement bank; the bank name comes from the statement account.'),
    (r'.*(?:REPORTO|INVERSION|(?:VENTA|COMPRA|REASIGNACION) FONDOS)', 'bank-investment', 'The description identifies an investment or repo bought from or repaid by the statement bank; the bank name comes from the statement account.'),
    (r'.*(?:CR.DITO|LINE OF CREDIT)', 'bank-credit-line', 'The description identifies a movement to or from a credit line held with the statement bank; the bank name comes from the statement account.'),
    (r'', 'bank-charge', 'The description identifies a bank fee, charge, refund of a charge or compensation from the statement bank; the bank name comes from the statement account.'),
]


def bank_service(value):
    """(rule, explanation) when the description is a service of the statement bank itself, or None."""
    if not _BANK_LEADING.match(value):
        return None
    text = re.sub(_BANK_PREFIX, '', value)
    for pattern, rule, explanation in _BANK_KINDS:
        if re.match(pattern, text):
            return rule, explanation
    return None


def card_line_merchant(raw, *, institution=None):
    """(name, rule, explanation) for a card statement purchase line, as printed, or None.

    The issuer's reference that some statements print first, the store number, the
    phone number, the place and the state are removed; what is left before them is
    the merchant descriptor. Lines whose opening is not a word (an address, a
    terminal number) name no merchant."""
    value = normalized(raw)
    # Interest the issuer charges, read badly (INTEREST CHARGE ON PURCHASES).
    if re.search(r'\bCHARGE ON (?:PURCHASES|CASH ADVANCES|BALANCE TRANSFERS)\b', value):
        return (institution, 'bank-charge', 'The description identifies interest the card issuer charges; the issuer name comes from the statement account.') if institution else None
    # A leading issuer reference (letters and digits, 10 or more) precedes the merchant on some statements;
    # a word glued to a ticket number (AMERICAN0012345678901) is the merchant, not a reference.
    # The card line's own format (issuer reference, store number, phone, state, ticket fields) must be
    # present: a bare name could be a person or anything else and is not read as a merchant.
    referenced = re.match(r'^(?:[A-Z]\s){0,3}(?=\S{0,3}\d)\S{10,}\s+', value)
    value = value[referenced.end():] if referenced else value
    if re.match(r'^[A-Z]\d{2}\s|.*\b(?:REF\s*:|CIE\s*:|REF\.)', value):
        return None
    # The issuer's own entries: payments, credits, fees, rewards, advances, disputes, promotions, tax lines.
    if re.match(r'^(?:(?:CAPITAL ONE|CARD|BANK|CAP \d|CITIBANK|CHKG)\s+)?(?:PAYMENTS?|PYMT|PMT|MOBILE|ONLINE|AUTOPAY|AUTOMATIC|ELECTRONIC|ELEC\w*|CREDIT|DEBIT|REFUND|'
                r'REVERSAL|ADJUSTMENT|CASH|BALANCE|INTEREST|FINANCE CHARGE|TRANSFER|WIRE|ATM|UNKNOWN|REFERENCE|REF\b|NOT RECORDED|FEE|LATE|PAST DUE|'
                r'WEB|OFFER|PROMO|ADVANCE|LINE OF CREDIT|CONDITIONAL|CONGRATS|MEMBERSHIP FEE|MISC FEE|PER ITEM|TDC|I\.?V\.?A\b)', value) \
            or re.search(r'\(FROM THE\b|\bPMT\s*(?:VRU)?AUTHDATE\b|\bPMTAUTHDATE\b', value):
        return None
    # The processor prefix (also read badly, TSTº) and a stray mark read before an opening quote are not the merchant.
    value = re.sub(r'^(?:(?:TST|SQ|SP|PY|IC)\s*\W|TST[O0])\s*', '', value)
    value = re.sub(r'^[A-Z]{1,2}\s+["“]', '', value)
    tokens = value.split()
    if not tokens or not re.match(r'[A-Z]', tokens[0]):
        return None
    kept = []
    evidence = bool(referenced)
    for index, token in enumerate(tokens):
        if token in ('NAME:', 'PHONE', 'DEPART:', 'ARRIVE:', 'FOLIO', 'DEFERRED') or re.match(r'(?:WWW\.|HTTPS?)|\S*\.(?:COM|NET|US)/', token):
            evidence = True
            break
        # A processor with only an order code (PAYPAL *1234567890, UPS*1a2b3c..) names no merchant.
        if not kept and re.match(r'^[A-Z]+\*(?=\S*\d)', token) and index == len(tokens) - 1:
            return None
        # A processor's order code after the merchant (AMZN MKTP US*2A3B4C5D6, UPS*1a2b..).
        token = re.sub(r'\*(?=\S*\d)\S{5,}$', '', token)
        if not token:
            break
        # A word glued to a ticket number (all digits after it) is the merchant; letters after the digits make an opaque code.
        glued = re.match(r'^([A-Z][A-Z&\'.\-]{2,})\d{10,}$', token)
        if glued:
            kept.append(glued[1])
            evidence = True
            break
        if re.search(r'[A-Z]{2,}\d{3,}[A-Z]', token) or (not kept and re.search(r'\d', token)):
            return None
        if kept and (re.fullmatch(r'#?\d{2,}\S*|\d[\d\-]{6,}', token) or re.search(r'[\dSOIL]{3}-\d{3}-\d{4}', token)):
            evidence = True
            # A street name and its number (INSURGENTES SUR 1602, MAIN ST 12) is an address, not the merchant.
            if re.fullmatch(r'\d{1,5}', token) and kept[-1] in _ADDRESS_LAST:
                return None
            break
        if kept and token in _STATES + ['OC'] and index == len(tokens) - 1:
            evidence = True
            break
        kept.append(token)
    # A town and state before the phone or store number (ANYTOWN TX 555-..) is the place, not the merchant.
    if 2 <= len(kept) <= 3 and kept[-1] in _STATES:
        return None
    while len(kept) > 1 and (kept[-1] in _STATES or re.fullmatch(r'[#\-]?[\d\-]+|[-*•·]+', kept[-1])):
        kept.pop()
    label = _without_place(' '.join(kept)).strip(' *-#•·')
    if not evidence or re.fullmatch(r'[A-Z]{1,3}', label) or (len(kept) == 1 and '*' in kept[0]) or concept_or_place(label, place=False) or generic_words_only(label) \
            or place_name(label) or bank_name(label) or re.search(r'\b(?:TO|FROM)\b', label):
        return None
    if len(re.sub(r'[^A-Z]', '', label)) < 3 or label in _PLACES or re.fullmatch(r'(?:COLUMBIA HEIGHTS|COLUMBIA HEIGH\S*)', label):
        return None
    span = re.search(re.escape(label).replace(r'\ ', r'\s+'), ' '.join(raw.split()), re.I)
    return (span[0] if span else label), 'card-line-merchant', (
        'Merchant as printed on this card line, with the issuer reference, store number, phone and place removed. '
        'It is not a verified legal identity; the original description remains available.')
