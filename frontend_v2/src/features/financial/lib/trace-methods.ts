export const traceMethods: Record<
  string,
  { label: string; explanation: string }
> = {
  lowest_intermediate_balance: {
    label: "Lowest intermediate balance",
    explanation:
      "Use money not assigned to a claim first. Once claimed money is spent, later deposits do not restore it.",
  },
  first_in_first_out: {
    label: "First in, first out",
    explanation:
      "Allocate each withdrawal to the oldest available funds first, including the opening balance.",
  },
  last_in_first_out: {
    label: "Last in, first out",
    explanation:
      "Allocate each withdrawal to the most recently deposited available funds first.",
  },
  pro_rata: {
    label: "Pro rata",
    explanation:
      "Divide each withdrawal across the available funds in proportion to their amounts.",
  },
  direct: {
    label: "Direct amount matching",
    explanation:
      "Look for one available deposit or attributed portion with the same amount as the funded withdrawal. Leave it unidentified if there is no unique match. An amount match alone does not prove where the payment came from.",
  },
}
