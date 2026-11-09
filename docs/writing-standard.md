# Loupe writing standard

Every word Loupe shows or generates follows this standard: screens, error messages, emails, export headers, reports,
the instructions sent to language models, and the text those models write back. The full reference is the skill
`writing-clearly-and-concisely` (Strunk, *The Elements of Style*, and Wikipedia's "Signs of AI writing"). This page
is Loupe's short version. Where the two differ, this page wins.

The machine-readable copy is `shared/writing-standard.json`. Three things read it:

- `backend/services/writing_standard.py` adds the instruction block to every prompt sent to a model, and cleans
  generated text before a person reads it (the post-check).
- `scripts/check_writing.py` lints every user-facing string in `frontend_v2/src`, every error message the API
  returns and the text of every report generator. A hit fails the test baseline
  (`backend/tests/test_writing_standard.py`).
- The evidence engine reads the same file for its summaries and extraction prompts.

## The rules

From Strunk, the six that matter most for Loupe:

1. **Use the active voice** (rule 10). "Loupe read 412 payments from the statement", not "412 payments were read".
2. **Put statements in positive form** (rule 11). Say what is, not what is not: "Choose a case first", not
   "case_id is required".
3. **Use definite, specific, concrete language** (rule 12). Names, dates, amounts and counts beat adjectives.
4. **Omit needless words** (rule 13). "successfully", "in order to", "please note", "the fact that" add nothing.
5. **Keep related words together** (rule 16). The amount next to its currency, the date next to its event.
6. **Place the emphatic words at the end** (rule 18), or lead with the answer.

## Never write these

The full lists are in `shared/writing-standard.json`. In short:

- **Filler and promotional words:** delve, tapestry, multifaceted, realm, testament, pivotal, crucial, robust,
  seamless, leverage, utilize, showcase, foster, notably, groundbreaking, cutting-edge, empower, elevate.
- **Chatbot phrases:** "It's important to note", "It's worth noting", "In summary", "In conclusion", "I hope this
  helps", "Let me know if", "Feel free to", "As an AI", "Great question", "plays a key role", "based on available
  information".
- **Vague errors:** "Something went wrong", "An unexpected error occurred". Say what failed and what to do.
- **Internal terms:** proof-class codes (P0 to P4), pipeline stage names, field names such as `case_id`, constant
  names, and programming values such as `null`, `undefined` or `NaN`. Say what they mean instead.

## Loupe's own rules (these win over everything above)

- **A quote is a quote.** Evidence text is never reworded: quotes, statement lines, message text, transcripts,
  file names, names, amounts and dates stay exactly as recorded. The post-check never touches text inside
  quotation marks, code or links.
- **Model readings keep their label and citation.** Plainer wording never hides that a model wrote something.
- **True numbers.** Money in the currency's own units (12,345.67 MXN); counts as counted, with what was left out.
- **They/them** for a person whose pronouns are unknown.
- **No internal codes** on any screen, report or answer.
- **No em dashes in text written to Alex.**
- API field names and stored values do not change; only the words people read do.

## Ten examples from Loupe

| Before | After |
|---|---|
| Something went wrong | This part of the page stopped working |
| An unexpected error occurred | The page hit an error it did not expect. Try again; if it happens again, reload the page. |
| Successfully imported statements are retained if another one needs attention. | Statements already imported stay imported if another one needs attention. |
| The attempt stopped part way because something went wrong. | The attempt stopped part way on an error. |
| Entities merged successfully, but some source entities could not be removed. You may see duplicates. | The entities were merged, but some of the originals could not be removed. Duplicates may show. |
| The original theory is marked Converted only after this finding is created successfully. | The original theory is marked Converted only once this finding is saved. |
| All queries are filtered by case_id to ensure data isolation between different investigations. | Every search reads only the open case, so one investigation never shows another's data. |
| case_id is required | Choose a case first. |
| Invalid case_id filter | That case filter is not a known case. |
| case_id is required when scope='case' | Choose a case to list case conversations. |

## Adding text

New text passes `python3 scripts/check_writing.py` (it needs `node` for the screens; `--backend-only` without).
A word that is right in its place (a query-language example a person types, the literal underscore character) goes
in `lint_exempt` in the JSON with the reason, never by loosening the lists.
