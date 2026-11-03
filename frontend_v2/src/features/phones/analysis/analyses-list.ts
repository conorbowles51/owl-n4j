export const ANALYSES = [
  { code: "money_signals", path: "phone-money", title: "Money on the phones", what: "Bank and payment alerts and amounts on the phones, checked against the financial records." },
  { code: "message_reconciliation", path: "phone-analyses/messages", title: "Messages across phones", what: "Messages on both phones, deleted on one and still on the other, or missing from the other with the reason, and how far apart the phones' clocks read." },
  { code: "incident_window", path: "phone-analyses/incident-window", title: "Incident window", what: "Everything each phone recorded around one moment, side by side, with no data shown as no data." },
  { code: "deletion_timeline", path: "phone-analyses/deletions", title: "Deleted and hidden", what: "What was deleted or made unreadable, when it can be placed, and conversations that lost more than the rest." },
  { code: "relationships", path: "phone-analyses/relationships", title: "Relationships over time", what: "For each person on each phone: when contact began and ended, how each phone names them, and where contact rose or fell." },
  { code: "device_users", path: "phone-analyses/two-phones", title: "Who used which phone", what: "Numbers, SIMs, accounts and networks two phones share, how often each was used while the other was not, and signs of more than one user." },
  { code: "reparse_comparison", path: "phone-analyses/read-again", title: "Read again by an independent tool", what: "Each phone read again by an open-source tool from the production's verified files, compared with the report: totals, records only one side has, and times or content that differ." },
  { code: "typed_words", path: "phone-analyses/typed-words", title: "Typed words", what: "Keyboard learned words and autofill values that match names, numbers and accounts in the case, and whether they appear anywhere else on the phone." },
  { code: "intent", path: "phone-analyses/searches", title: "Searches and pages", what: "Searches and visited pages that match names, numbers and accounts in the case, with the time each records." },
  { code: "common_contacts", path: "phone-analyses/common-contacts", title: "Common contacts", what: "The people two phone owners are both in contact with, with the calls, messages and emails on each side." },
  { code: "contact_matrix", path: "phone-analyses/who-contacts-whom", title: "Who contacts whom", what: "For each pair, the calls, messages and emails one sent to the other, in each direction, calls by whether they connected." },
  { code: "number_switching", path: "phone-analyses/number-changes", title: "Possible number changes", what: "A number or account whose contact stops while another, in contact with mostly the same people, starts soon after." },
  { code: "awareness", path: "phone-analyses/groups", title: "Group admins and membership", what: "Admins of each group chat at extraction and the membership changes the phones record." },
]

export const NOT_BUILT = [
  { title: "Where two phones were together", why: "Not built: no two phones in the measured cases were placed in the same quarter hour often enough (43 times at most, 200 needed)." },
  { title: "Plans and check-ins against location", why: "Not built: the measured phones hold 3 calendar entries with a place (20 needed)." },
]
