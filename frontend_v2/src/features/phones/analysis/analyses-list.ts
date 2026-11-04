export const ANALYSES = [
  { code: "money_signals", path: "phone-money", title: "Money on the phones", what: "Bank and payment alerts and amounts on the phones, checked against the financial records." },
  { code: "message_reconciliation", path: "phone-analyses/messages", title: "Messages across phones", what: "Messages on both phones, deleted on one and still on the other, or missing from the other with the reason, and how far apart the phones' clocks read." },
  { code: "incident_window", path: "phone-analyses/incident-window", title: "Incident window", what: "Everything each phone recorded around one moment, side by side, with no data shown as no data." },
  { code: "deletion_timeline", path: "phone-analyses/deletions", title: "Deleted and hidden", what: "What was deleted or made unreadable, when it can be placed, and conversations that lost more than the rest." },
  { code: "relationships", path: "phone-analyses/relationships", title: "Relationships over time", what: "For each person on each phone: when contact began and ended, how each phone names them, and where contact rose or fell." },
  { code: "device_users", path: "phone-analyses/two-phones", title: "Who used which phone", what: "Numbers, SIMs, accounts and networks two phones share, how often each was used while the other was not, whether they were together or apart and used while apart, and signs of more than one user." },
  { code: "reparse_comparison", path: "phone-analyses/read-again", title: "Read again by an independent tool", what: "Each phone read again by an open-source tool from the production's verified files, compared with the report: totals, records only one side has, and times or content that differ." },
  { code: "typed_words", path: "phone-analyses/typed-words", title: "Typed words", what: "Keyboard learned words and autofill values that match names, numbers and accounts in the case, and whether they appear anywhere else on the phone." },
  { code: "intent", path: "phone-analyses/searches", title: "Searches and pages", what: "Searches and visited pages that match names, numbers and accounts in the case, with the time each records." },
  { code: "common_contacts", path: "phone-analyses/common-contacts", title: "Common contacts", what: "The people two phone owners are both in contact with, with the calls, messages and emails on each side." },
  { code: "contact_matrix", path: "phone-analyses/who-contacts-whom", title: "Who contacts whom", what: "For each pair, the calls, messages and emails one sent to the other, in each direction, calls by whether they connected." },
  { code: "number_switching", path: "phone-analyses/number-changes", title: "Possible number changes", what: "A number or account whose contact stops while another, in contact with mostly the same people, starts soon after." },
  { code: "extraction_comparison", path: "phone-analyses/two-extractions", title: "Two extractions of one phone", what: "Whether two extractions are of one device, and what is in one and not the other, deleted between them, or new." },
  { code: "other_devices", path: "phone-analyses/devices-accounts", title: "Devices and accounts across phones", what: "WiFi networks, Bluetooth devices, accounts and web services each phone shows, and every one two or more phones share, graded by how well it matches." },
  { code: "plans", path: "phone-analyses/plans", title: "Plans and check-ins against location", what: "Calendar entries, check-ins and notes, and where the phone places one, whether its own location at the time agrees." },
  { code: "awareness", path: "phone-analyses/groups", title: "Reading, replies and group roles", what: "When messages were read or played, how long replies took, messages read with no reply or still unread, and the admins and membership changes of each group chat." },
]

/** Analyses not offered, each with the measured reason. Empty while every planned analysis is built. */
export const NOT_BUILT: { title: string; why: string }[] = []
