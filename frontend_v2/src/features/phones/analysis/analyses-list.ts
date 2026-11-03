export const ANALYSES = [
  { path: "phone-money", title: "Money on the phones", what: "Bank and payment alerts and amounts on the phones, checked against the financial records." },
  { path: "phone-analyses/messages", title: "Messages across phones", what: "Messages on both phones, deleted on one and still on the other, or missing from the other with the reason, and how far apart the phones' clocks read." },
  { path: "phone-analyses/deletions", title: "Deleted and hidden", what: "What was deleted or made unreadable, when it can be placed, and conversations that lost more than the rest." },
  { path: "phone-analyses/relationships", title: "Relationships over time", what: "For each person on each phone: when contact began and ended, how each phone names them, and where contact rose or fell." },
  { path: "phone-analyses/two-phones", title: "Who used which phone", what: "Numbers, SIMs, accounts and networks two phones share, how often each was used while the other was not, and signs of more than one user." },
  { path: "phone-analyses/groups", title: "Group admins and membership", what: "Admins of each group chat at extraction and the membership changes the phones record." },
]

export const NOT_BUILT = [
  { title: "Where two phones were together", why: "Not built: no two phones in the measured cases were placed in the same quarter hour often enough (43 times at most, 200 needed)." },
  { title: "Plans and check-ins against location", why: "Not built: the measured phones hold 3 calendar entries with a place (20 needed)." },
]
