# fin/live-backlog — work in progress

## Review queue API contract (for the frontend_v2 work)

`GET /api/financial/statement-import/review/queue`

Parameters (all new ones optional; without them the response is exactly as before, every list complete):

| param | meaning |
|---|---|
| `case_id` | as before |
| `file_id` (repeatable) | as before: limit to these files |
| `limit` | cap on every entry list (`items`, `ready`, `filled`, `reader_fix`, `rechecking`, `copies`, `unreadable`). `0` = counts only. Omitted = no cap. |
| `offset` | start of the page in `page_list` (default 0). Other lists always start at 0. |
| `page_list` | which list `offset`/`issue` apply to: `waiting` (default, the `items` field), `ready`, `filled`, `reader_fix`, `rechecking`, `copies`, `unreadable` |
| `issue` | only entries of `page_list` whose `issue_reason` is this key (e.g. `currency`) |
| `fresh` | `1` = wait for a queue built from the current data (after a save). Default: a queue built moments ago may be returned while a new one is built in the background (`refreshing: true`). |

Response: every existing field, plus

```jsonc
{
  "totals":  {"waiting": 612, "ready": 3, "filled": 0, "reader_fix": 40, "rechecking": 113, "copies": 9, "unreadable": 4},
  "page":    {"list": "waiting", "issue": null, "offset": 0, "limit": 100, "returned": 100, "total": 612},
  "issue_counts": {"currency": 300, "reading": 250, "balance": 62},   // over every waiting entry (file filter applied)
  "ready_item_ids": ["..."],      // every ready entry's id, never truncated (for "Import N ready")
  "refreshing": false,            // true: this answer predates the latest change; a fresh one is being built
  "as_of": "2026-10-22T21:00:00+00:00"  // when this queue was built
}
```

* `totals[list]` is the full length of that list (file filter applied, issue filter not); `page.total` is the length after the issue filter. Show "showing `returned` of `total`" whenever `returned < total`.
* `counts` and `status_line` are always whole-case (or whole-filter) numbers, never page numbers.
* While `refreshing` is true, poll again (the existing 15 s poll is enough) and say the numbers are being updated.

`GET /api/financial/statement-import/review/status?case_id=` (counts only): `counts`, `status_line`, `reading`, `refreshing`, `as_of`. It never waits for a rebuild when a queue for the case was built before; use it for badges and the cross-case view instead of the full queue.

`POST /review/save` and `/review/fill` are unchanged.
