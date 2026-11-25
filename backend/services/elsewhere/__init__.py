"""Elsewhere in the case: for one phone record, or one checkable statement, what the other phones, the financial
records, the documents and the case timeline hold that bears on it (phones redesign, screens 1 and 7).

Each item carries its source, a citation, a relation and the reason for it. Relations are computed here by rules
(same people, numbers, accounts, amounts, check numbers, dates, places); no model decides one:

- ``agrees``: the other source holds the same thing (the same message on another phone, the same check number
  with the same amount, the same amount and the same person in the window);
- ``disagrees``: the other source holds the same thing with a different value (a check number with another
  amount, a phone that was somewhere else at the time);
- ``missing_here``: a source that should hold it does not (a party's phone that holds the messages either side
  of it but not this one);
- ``possible_match``: something that could be it, labelled "not confirmed" and never counted as agreement;
- ``nothing_found``: a result, saying what was searched.

Parts: ``phones``, ``financial``, ``documents``, ``timeline``. A screen asks for each part on its own request so
the fast ones fill first (``service.run``).
"""
