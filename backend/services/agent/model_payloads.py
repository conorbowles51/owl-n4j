"""What the model sees of a tool result: the whole result when it fits, otherwise a stated page of it.

The run keeps every tool result whole (``AgentToolContext.result_store``). The model gets the same data unless the
serialized result is larger than its share of the model's context. Then the largest lists (or mappings) are cut to
a prefix that fits, and ``_paging`` states, for each one, its ``total``, how many items were ``returned`` and the
``next_page`` call that reads the rest from the stored result. Nothing is dropped without saying so: there is no
fixed item cut and no silent key or text cut.
"""
import json

from services.agent.json_utils import to_jsonable

PAGE_TOOL = "read_tool_result_page"
# Characters per model token for JSON tool output (UUIDs and punctuation tokenize densely); conservative.
CHARS_PER_TOKEN = 3
# Share of the model's context window that tool results may use over one run, leaving room for the prompts,
# the conversation and the answer.
RUN_CONTEXT_SHARE = 0.6
# Context window used when the model's is not recorded (models.llm_models): a conservative 128k tokens.
DEFAULT_CONTEXT_TOKENS = 128_000
# One tool message never takes more than this, so one large result cannot use up the run on its own. A full
# 100-row ledger page with provenance measured about 400,000 characters (lx-agent, BNB2), so it fits whole.
MAX_MESSAGE_CHARS = 600_000
# Never page below this: a page has room for at least a few items and the paging note.
MIN_MESSAGE_CHARS = 12_000
# A single text value larger than this is shown in part with its length stated (only when it alone cannot fit).
MAX_TEXT_CHARS = 20_000
NOTE_ROOM = 400  # characters kept for the note a cut adds
PAGED_SUMMARY = " This result is shown in part; _paging states what is not shown and how to read it."


def run_budget_chars(context_window_tokens=None):
    """Characters of tool results one run may send to a model with this context window."""
    tokens = context_window_tokens if isinstance(context_window_tokens, int) and context_window_tokens > 0 else DEFAULT_CONTEXT_TOKENS
    return int(tokens * CHARS_PER_TOKEN * RUN_CONTEXT_SHARE)


def message_budget_chars(run_budget, used_chars):
    """This message's share: what is left of the run budget, capped per message, never below the minimum page."""
    return max(MIN_MESSAGE_CHARS, min(MAX_MESSAGE_CHARS, int(run_budget) - int(used_chars or 0)))


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str))


def _pageable(value):
    """A list, or a mapping whose entries are all of one kind (labels to their fields, keys to counts). A mapping
    with fields of different kinds is a record (a result envelope with its totals): never cut."""
    if isinstance(value, list):
        return True
    if not isinstance(value, dict) or len(value) < 3:
        return False
    kinds = {type(item) for item in value.values()}
    return len(kinds) == 1 and kinds <= {dict, list, int, float}


def _sequences(value, path=()):
    """Every list and uniform mapping in a payload with its path."""
    found = []
    # The top of a tool's data or artifact is its record: never cut by key (its lists still page).
    record = isinstance(value, dict) and path in (("data",), ("artifact",))
    if path and not record and _pageable(value):
        found.append((path, value))
    children = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else ()
    for key, child in children:
        if isinstance(child, (list, dict)):
            found.extend(_sequences(child, path + (key,)))
    return found


def _get(value, path):
    for key in path:
        value = value[key]
    return value


def _set(value, path, replacement):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = replacement


def _slice(sequence, offset, count):
    if isinstance(sequence, list):
        return sequence[offset:offset + count]
    keys = list(sequence)[offset:offset + count]
    return {key: sequence[key] for key in keys}


def _fit_count(sequence, offset, room, at_least_one=True):
    """How many items from ``offset`` fit in ``room`` characters (at least one when any remain, unless told not to)."""
    items = list(sequence.items())[offset:] if isinstance(sequence, dict) else sequence[offset:]
    used, count = 2, 0
    for item in items:
        used += _size(item if isinstance(sequence, list) else {item[0]: item[1]}) + 1
        if used > room and (count or not at_least_one):
            break
        count += 1
        if used > room:
            break
    return count


def _note(path, total, offset, returned, result_id):
    remaining = total - offset - returned
    note = dict(path=list(path), total=total, offset=offset, returned=returned, remaining=remaining)
    if remaining > 0:
        note["next_page"] = dict(tool=PAGE_TOOL, result_id=result_id, path=list(path), offset=offset + returned)
        note["message"] = (f"Showing {returned} of {total} from item {offset}; {remaining} more: call {PAGE_TOOL} "
                           "with next_page, or say the answer covers part of the result.")
    return note


def _cut_texts(value, limit):
    """Shorten single oversized texts, stating how much is not shown (last resort, after paging lists)."""
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f" [... {len(value) - limit} more characters not shown]"
    if isinstance(value, list):
        return [_cut_texts(item, limit) for item in value]
    if isinstance(value, dict):
        return {key: _cut_texts(item, limit) for key, item in value.items()}
    return value


def page_for_model(data, *, budget_chars, result_id=None, offset=0, path=None):
    """``data`` whole when it fits ``budget_chars``; otherwise its largest sequences cut to fit, with ``_paging``.

    ``path``/``offset``: page one sequence of a stored result from ``offset`` (the next-page tool)."""
    safe = to_jsonable(data)
    if path is not None:
        sequence = _get(safe, path) if path else safe
        if not isinstance(sequence, (list, dict)):
            raise ValueError("That path is not a list or mapping in this result.")
        total = len(sequence)
        if offset < 0 or offset > total:
            raise ValueError(f"Use an offset from 0 to {total}.")
        count = _fit_count(sequence, offset, budget_chars - 1_000)
        return dict(items=_slice(sequence, offset, count), _paging=[_note(path, total, offset, count, result_id)])
    if _size(safe) <= budget_chars:
        return safe
    if not isinstance(safe, dict):
        safe = {"value": safe}
    notes = []
    done = set()
    # The notes are part of the message, so every size check counts them, with room kept for the next note.
    while _size(safe) + _size(notes) > budget_chars:
        candidates = [(p, s) for p, s in _sequences(safe) if p not in done and len(s) > 1]
        if not candidates:
            break
        sequence_path, sequence = max(candidates, key=lambda item: _size(item[1]))
        done.add(sequence_path)
        room = budget_chars - (_size(safe) - _size(sequence)) - _size(notes) - NOTE_ROOM
        count = _fit_count(sequence, 0, room, at_least_one=False) if room > 0 else 0
        if count >= len(sequence):
            continue
        _set(safe, sequence_path, _slice(sequence, 0, count))
        notes.append(_note(sequence_path, len(sequence), 0, count, result_id))
    if _size(safe) + _size(notes) > budget_chars:
        safe = _cut_texts(safe, min(MAX_TEXT_CHARS, max(1_000, budget_chars // 4)))
        notes.append(dict(message="Some long text values are shown in part; each states how many characters are "
                                  "not shown."))
    safe["_paging"] = notes
    return safe


def model_view(data, artifact=None):
    """What one tool call puts before the model, before paging: its data, and the artifact it built if any."""
    view = {"data": to_jsonable(data)}
    if artifact:
        view["artifact"] = to_jsonable(artifact)
    return view


def context_window_for(model_id):
    """The model's recorded context window in tokens (models.llm_models), or None when it is not recorded."""
    try:
        from models.llm_models import get_model_by_id
        model = get_model_by_id(model_id) if model_id else None
    except Exception:  # noqa: BLE001 - an unknown model uses the conservative default
        return None
    return getattr(model, "context_window", None)


def tool_message_payload(*, result_id, summary, data, artifact=None, budget_chars=MAX_MESSAGE_CHARS):
    """The tool message the model reads: the whole view when it fits ``budget_chars``, otherwise a stated page.

    Every tool, ledger tools included, goes through the same budget. Ledger pages keep their own
    total_matching/next_offset; when even one ledger page is larger than the budget it is paged here too."""
    paged_summary = (summary + PAGED_SUMMARY).strip()
    # The envelope around the page is part of the message too: the page gets what is left of the budget.
    envelope = _size({"result_id": result_id, "summary": paged_summary, "data": None, "artifact": None,
                      "_paging": None})
    view = page_for_model(model_view(data, artifact), budget_chars=max(1_000, budget_chars - envelope),
                          result_id=result_id)
    payload = {"result_id": result_id, "summary": summary, "data": view.get("data"),
               "artifact": view.get("artifact")}
    if view.get("_paging"):
        payload["_paging"] = view["_paging"]
        payload["summary"] = paged_summary
    return payload


def tool_data_for_model(name, data, *, result_id=None, budget_chars=MAX_MESSAGE_CHARS):
    """The data part only (kept for callers that page data alone)."""
    return page_for_model(data, budget_chars=budget_chars, result_id=result_id)
