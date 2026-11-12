"""Durable agent execution. Checkpoints are data, never executable serialized objects.

Each model response and each completed tool is committed before the next operation. A
recovered batch skips its completed calls. An ambiguous external write is held for
review rather than replayed. Source scope and permissions are rechecked by the caller.
"""
from __future__ import annotations

import json
import time
from copy import deepcopy
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage, messages_from_dict, messages_to_dict

VERSION = 1
DEFAULT_WINDOWS = 8
MAX_SECONDS = 3600
MUTATING_PREFIXES = ("propose_", "draft_", "plan_theory_", "save_", "update_", "delete_", "accept_")


def write_metadata(db, run, values):
    """Merge keys atomically with heartbeat progress; never replace a stale JSON object."""
    from sqlalchemy import text
    from services.agent.json_utils import to_jsonable
    safe = to_jsonable(values)
    db.flush()
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("UPDATE agent_runs SET extra_metadata = COALESCE(extra_metadata, '{}'::jsonb) || "
                        "CAST(:payload AS jsonb) WHERE id = :id"),
                   {"payload": json.dumps(safe), "id": str(run.id)})
        db.expire(run, ["extra_metadata"])
    else:
        db.refresh(run, ["extra_metadata"])
        run.extra_metadata = {**(run.extra_metadata or {}), **safe}
        db.flush()


def lock_execution(db, run, lease):
    """Hold the run row until commit and reject writes by a superseded worker."""
    from postgres.models.agent import AgentRun
    db.query(AgentRun).filter(AgentRun.id == run.id).populate_existing().with_for_update().one()
    if lease and (run.extra_metadata or {}).get("execution_lease") != lease:
        raise RuntimeError("Another worker owns this saved job")


def save_checkpoint(db, run, payload, request=None, lease=None):
    from services.agent import storage
    lock_execution(db, run, lease)
    if run.status != "running":
        from services.agent.graph import AgentRunCancelled
        raise AgentRunCancelled("Agent run stopped")
    values = {"execution_checkpoint": payload}
    if request is not None:
        values["execution_request"] = request.model_dump(mode="json")
    # Artifacts produced before an interrupted step must be available from the UI too.
    for artifact in payload.get("artifacts", []):
        artifact["metadata"] = {**(artifact.get("metadata") or {}),
            "all_cases": bool(payload.get("all_cases")),
            "source_case_ids": sorted({str(run.case_id), *(payload.get("cases_read") or {}).keys()})}
    records = storage.persist_artifacts(db, thread=run.thread, run=run, artifacts=payload.get("artifacts", []))
    stored = {str(record.id): record for record in records}
    for artifact in payload.get("artifacts", []):
        if artifact.get('id') in stored:
            artifact['metadata'] = stored[artifact['id']].extra_metadata or {}
    write_metadata(db, run, values)
    db.commit()
    return payload


def recover_run(run_id):
    """Run a claimed stale checkpoint on a fresh session; the same run owns the output."""
    from uuid import UUID
    from postgres.session import get_background_session
    from postgres.models.agent import AgentRun
    from postgres.models.user import User
    from services.agent.schemas import AgentMessageRequest
    from services.agent.service import agent_service
    with get_background_session() as db:
        run = db.get(AgentRun, UUID(str(run_id)))
        if run is None or run.status != "running":
            return
        token = (run.extra_metadata or {}).get('execution_resume_token')
        try:
            user = db.get(User, run.user_id)
            if user is None or not user.is_active:
                raise PermissionError("The user no longer has access")
            request = AgentMessageRequest(**run.extra_metadata["execution_request"])
            request.thread_id = run.thread_id
            # Preserve the model and scope selected for the original run.
            request.model, request.provider = run.model_id, run.provider
            for _event in agent_service.stream_message(db=db, user=user, request=request, resume_run_id=run.id,
                    resume_claim=token):
                pass
        except Exception as exc:
            db.rollback()
            run = db.get(AgentRun, UUID(str(run_id)))
            if run is not None and run.status == "running" and (run.extra_metadata or {}).get('execution_lease') == token:
                from services.agent.storage import finish_run
                try:
                    lock_execution(db, run, token)
                except RuntimeError:
                    db.rollback()
                    return
                finish_run(db, run=run, status="interrupted", error=f"Saved work could not resume: {exc}")
                db.commit()


def claim_resume(db, run_id, user):
    """Atomically reserve one resumed worker before returning a streaming response."""
    import uuid
    from datetime import datetime, timezone
    from postgres.models.agent import AgentRun
    from services.agent import storage
    storage.get_run_for_user(db, run_id=run_id, user=user)
    run = db.query(AgentRun).filter(AgentRun.id == run_id).populate_existing().with_for_update().one()
    meta = run.extra_metadata or {}
    checkpoint = meta.get('execution_checkpoint')
    if run.status not in ('interrupted', 'failed', 'cancelled', 'clarification_required'):
        raise ValueError('This job is already running or cannot be resumed in its current state.')
    if not checkpoint or not meta.get('execution_request'):
        raise ValueError('This older run has no resumable checkpoint.')
    reason = ((meta.get('clarification') or {}).get('context') or {}).get('reason')
    if run.status == 'clarification_required' and reason not in ('tool_budget_exhausted', 'no_progress'):
        raise ValueError('Answer the outstanding question before resuming.')
    if (checkpoint.get('inflight') or {}).get('name', '').startswith(MUTATING_PREFIXES):
        raise ValueError('An interrupted case action needs its saved result checked before retrying.')
    checkpoint = extend_budget_checkpoint(checkpoint)
    token = str(uuid.uuid4())
    run.status, run.completed_at, run.error = 'running', None, None
    run.heartbeat_at = datetime.now(timezone.utc)
    write_metadata(db, run, {'execution_resume_token': token, 'execution_resume_pending': True,
                            'execution_lease': token, 'execution_checkpoint': checkpoint})
    db.commit()
    return run, token


def consume_resume_claim(db, run, token):
    from postgres.models.agent import AgentRun
    db.query(AgentRun).filter(AgentRun.id == run.id).populate_existing().with_for_update().one()
    meta = run.extra_metadata or {}
    if (not token or run.status != 'running' or meta.get('execution_resume_token') != token
            or not meta.get('execution_resume_pending')):
        raise ValueError('This saved job was already resumed by another request.')
    write_metadata(db, run, {'execution_resume_pending': False})
    db.commit()


def extend_budget_checkpoint(checkpoint):
    """Explicit resume grants one further bounded envelope; the task and calls remain intact."""
    value = deepcopy(checkpoint)
    reason = (value.get("clarification") or {}).get("context", {}).get("reason")
    if reason in ('tool_budget_exhausted', 'no_progress'):
        value.update(phase="tools", clarification=None, answer="", elapsed_seconds=0, malformed_streak=0,
                     budget_base=value.get('used_steps', len(value.get("trace", []))))
        if reason == 'no_progress':
            value['resume_note'] = ('The investigator explicitly resumed this saved task after a no-progress stop. '
                'Preserve completed work and the latest user requirements. Change the failed approach; do not repeat '
                'unsuccessful paging guesses or unchanged reads. Use the authoritative result ID, path and next-page '
                'offset supplied by tools, or re-read the relevant source to obtain a fresh valid continuation.')
    return value


def instruction_ledger(messages, *, all_cases=False):
    """Lossless user instructions in order, with scopes; no model-written replacement."""
    return [{"sequence": m.sequence_number, "text": m.content} for m in messages
            if m.role == "user" and (all_cases or not (
                m.run and (m.run.extra_metadata or {}).get("all_cases")))]


def task_specification(db, thread, request):
    """The exact instruction record is authoritative; derived outlines must never replace it."""
    from postgres.models.agent import AgentMessage
    rows = (db.query(AgentMessage).filter(AgentMessage.thread_id == thread.id, AgentMessage.role == 'user')
            .order_by(AgentMessage.sequence_number).all())
    instructions = instruction_ledger(rows, all_cases=request.all_cases)
    if request.case_layer == 'significant':
        instructions = [{"sequence": rows[-1].sequence_number, "text": request.message}] if rows else []
    from services.agent.completion_checks import delivery_contract
    return {"version": 1, "instructions": instructions, "latest_request": request.message,
            "delivery_contract": delivery_contract(instructions),
            "source_scope": {"case_id": str(thread.case_id), "all_cases": request.all_cases, "layer": request.case_layer},
            "artifact_preference": request.artifact_preference,
            "precedence": "Later explicit instructions replace conflicting earlier instructions; retain the others."}


def stream(runner, *, case_id, messages, artifact_preference="auto", max_tool_calls=28,
           available_artifacts=None, should_cancel=None, allowed_entity_keys=None,
           mandate_context_block="", final_answer_rules="", proposer=None, user_id=None,
           all_cases=False, on_progress=None, hidden_tools=frozenset(),
           checkpoint_callback=None, resume_checkpoint=None, automatic_windows=DEFAULT_WINDOWS,
           access_check=None, delivery_contract=None, steering=None, **_ignored):
    from services.agent import graph as g, live_runs, fit, tool_groups
    checkpoint = deepcopy(resume_checkpoint or {})
    if checkpoint and (checkpoint.get("version") != VERSION or checkpoint.get("case_id") != case_id
                       or checkpoint.get("all_cases", False) != bool(all_cases)
                       or checkpoint.get("allowed_entity_keys") != allowed_entity_keys):
        raise ValueError("Saved agent work has a different source scope; start a new request.")
    state_messages = messages_from_dict(checkpoint["messages"]) if checkpoint else list(messages)
    spent = messages_from_dict(checkpoint.get("spent", []))
    billed_count = int(checkpoint.get("billed_count", 0))
    runner.messages_so_far = spent
    runner.billed_message_count = billed_count
    trace = checkpoint.get("trace", [])
    progress_trace_start = len(trace)
    artifacts = checkpoint.get("artifacts", [])
    context = g.AgentToolContext(case_id=case_id, artifact_preference=artifact_preference,
                                allowed_entity_keys=set(allowed_entity_keys) if allowed_entity_keys is not None else None,
                                artifact_store=g._artifact_store_from_available(available_artifacts),
                                proposer=proposer, user_id=user_id, all_cases=all_cases)
    for key in ("result_store", "model_views", "artifact_store", "cases_read", "other_case_citations"):
        getattr(context, key).update(checkpoint.get(key, {}))
    for key in ('rereads', 'reread_source'):
        getattr(context, key).update(checkpoint.get(key, {}))
    context.page_reads = {(item[0], tuple(item[1]), item[2]) for item in checkpoint.get('page_reads', [])}
    context.working_notes = deepcopy(checkpoint.get('working_notes', []))
    context.free_calls = int(checkpoint.get('free_calls', 0))
    context.reread_calls = int(checkpoint.get('reread_calls', 0))
    for artifact in context.artifact_store.values():
        for source_id in (artifact.get("metadata") or {}).get("source_case_ids", []):
            if source_id != case_id:
                context.cases_read.setdefault(source_id, None)
    tools = g.make_agent_tools(context)
    by_name = {t.name: t for t in tools if t.name not in hidden_tools}
    # The person's tool switches and notes taken so far (services.agent.tool_groups), kept across a resume.
    steer_applied = deepcopy(checkpoint.get('steering_applied', []))

    def bind():
        switched_off = tool_groups.hidden_tools(steer_applied)
        return runner.base_model.bind_tools(g.tools_for_binding(runner.base_model,
            [t for t in tools if t.name not in hidden_tools and t.name not in fit.hidden_tools()
             and t.name not in switched_off]))

    bound = bind()
    phase = checkpoint.get("phase", "agent")
    completed = set(checkpoint.get("completed_calls", []))
    inflight = checkpoint.get("inflight")
    clarification = checkpoint.get("clarification")
    answer = checkpoint.get("answer", "")
    from services.agent import completion_checks
    contract = checkpoint.get('delivery_contract') or delivery_contract or completion_checks.delivery_contract(
        [m.content for m in messages if isinstance(m, HumanMessage)])
    repair_attempts = int(checkpoint.get('repair_attempts', 0))
    if (checkpoint and phase != 'done'
            and checkpoint.get('completion_check_version') != completion_checks.COMPLETION_CHECK_VERSION):
        # An upgraded checker gets a bounded fresh repair window; previous false
        # diagnoses must not consume the new checker's entire repair allowance.
        repair_attempts = 0
    render_receipts = checkpoint.get('render_receipts') or {}
    completion_issues = checkpoint.get('completion_issues') or []
    source_receipts = checkpoint.get('source_coverage_receipts') or []
    evidence_review_receipts = checkpoint.get('evidence_review_receipts') or {}
    source_messages = messages_from_dict(checkpoint.get('source_observations') or [])
    from services.agent.claim_validation import fingerprint
    source_message_keys = {fingerprint([m.tool_call_id, m.content]) for m in source_messages}
    malformed_streak = int(checkpoint.get('malformed_streak', 0))
    resume_note = checkpoint.get('resume_note')
    if checkpoint and not resume_note and phase != 'done':
        resume_note = ('Saved work has resumed; this is an execution note, not a new investigator instruction. '
            'Preserve the current draft, all completed work and the original requested scope. Before rewriting '
            'content to address a historical validation failure, inspect the latest saved artifact with the current '
            'tools. Earlier checker results can be stale after an application update. Recheck first and repair '
            'only current problems; do not convert valid tables or remove content to satisfy an obsolete error.')
    used = int(checkpoint.get('used_steps', len(trace)))
    total_budget = checkpoint.get("budget_base", 0) + max(1, max_tool_calls) * max(1, min(automatic_windows, 32))
    elapsed_before = checkpoint.get("elapsed_seconds", 0)
    started = time.monotonic()
    run_budget = g.run_budget_chars(g.context_window_for(getattr(runner, "model_id", None)))

    def ensure_access():
        if should_cancel and should_cancel():
            raise g.AgentRunCancelled("Agent run cancelled")
        if access_check:
            access_check(list(context.cases_read))

    def note(value):
        if on_progress:
            # "step N of up to <budget>": the budget this run stops at (lx-agentfit, tool steering F).
            on_progress({**value, "budget": total_budget} if isinstance(value, dict) else value)

    def save():
        payload = dict(version=VERSION, case_id=case_id, all_cases=bool(all_cases),
                       allowed_entity_keys=allowed_entity_keys, phase=phase,
                       messages=messages_to_dict(state_messages), spent=messages_to_dict(spent),
                       trace=trace, artifacts=artifacts, completed_calls=sorted(completed), inflight=inflight,
                       clarification=clarification, answer=answer,
                       delivery_contract=contract, repair_attempts=repair_attempts,
                       completion_check_version=completion_checks.COMPLETION_CHECK_VERSION,
                       render_receipts=render_receipts, completion_issues=completion_issues,
                       source_coverage_receipts=source_receipts,
                       evidence_review_receipts=evidence_review_receipts,
                       source_observations=messages_to_dict(source_messages),
                       malformed_streak=malformed_streak,
                       resume_note=resume_note,
                       used_steps=used, free_calls=context.free_calls, reread_calls=context.reread_calls,
                       working_notes=context.working_notes, rereads=context.rereads,
                       reread_source=context.reread_source,
                       page_reads=[[source, list(path), offset] for source, path, offset in context.page_reads],
                       steering_applied=steer_applied,
                       budget_base=checkpoint.get("budget_base", 0), billed_count=billed_count,
                       elapsed_seconds=elapsed_before + time.monotonic() - started)
        for key in ("result_store", "model_views", "artifact_store", "cases_read", "other_case_citations"):
            payload[key] = getattr(context, key)
        if checkpoint_callback:
            persisted = checkpoint_callback(g.to_jsonable(payload))  # failure stops before another external operation
            if isinstance(persisted, dict):
                stored = {a.get('id'): a for a in persisted.get('artifacts', [])}
                for value in artifacts:
                    if value.get('id') in stored:
                        value['metadata'] = stored[value['id']].get('metadata') or {}
                        if value['id'] in context.artifact_store:
                            context.artifact_store[value['id']]['metadata'] = value['metadata']

    def system_prompt():
        return g.render_system_prompt(case_id=case_id, significant=allowed_entity_keys is not None,
                mandate_context_block=mandate_context_block, artifact_preference=artifact_preference,
                available_artifact_context=g._format_available_artifacts(list(context.artifact_store.values())),
                all_cases=context.all_cases)

    def model_context(values):
        from services.agent.context_projection import project
        from services.agent.source_coverage import source_observations
        projected = project(values, budget_chars=run_budget)
        for observation in source_observations(projected, context.result_store):
            key = fingerprint([observation.tool_call_id, observation.content])
            if key not in source_message_keys:
                source_message_keys.add(key)
                source_messages.append(observation)
        return projected

    ensure_access()
    save()
    yield {"type": "status", "stage": "reasoning", "message": "Resuming saved work" if checkpoint else "Working on the request"}
    while phase != "done":
        ensure_access()
        if phase == "agent":
            if resume_note:
                state_messages.append(HumanMessage(content=resume_note))
                resume_note = None
                save()
            # Switches and notes the person sent while the last step ran apply from this step (the running step
            # finished first). Read from the run row: the web process that took them is not this worker.
            fresh = tool_groups.apply(steering() or [], steer_applied, step=used) if steering else []
            if fresh:
                if any(entry.get("kind") == "switch" for entry in fresh):
                    bound = bind()
                    state_messages.append(HumanMessage(content=tool_groups.switch_message(fresh)))
                for entry in fresh:
                    if entry.get("kind") == "note":
                        state_messages.append(HumanMessage(content=tool_groups.note_message(entry)))
                save()
                yield {"type": "steering", "entries": [tool_groups.trail_entry(e) for e in fresh],
                       "applied": [tool_groups.trail_entry(e) for e in steer_applied],
                       "off": sorted(tool_groups.off_groups(steer_applied))}
            note(live_runs.progress_thinking(step=used))
            response = g.invoke_model(bound, [SystemMessage(content=system_prompt()), *model_context(g.lean_messages(state_messages))],
                                      note=note, step=used, should_cancel=should_cancel)
            state_messages.append(response)
            spent.append(response)
            phase = "tools" if getattr(response, "tool_calls", []) else "finalize"
            if getattr(response, 'invalid_tool_calls', None):
                malformed_streak += 1
                if not getattr(response, 'tool_calls', []):
                    phase = 'agent'
                    if malformed_streak >= 3:
                        clarification = {'question': 'The model could not produce a valid next editing step after three attempts. '
                            'Completed work is saved. Resume it to try again, or keep the current draft.',
                            'context': {'reason': 'no_progress'}, 'options': [
                                {'id': 'resume', 'label': 'Resume saved work'}, {'id': 'stop', 'label': 'Keep the draft'}],
                            'allow_free_text': True}
                        phase = 'finalize'
                yield {'type': 'status', 'stage': 'repairing', 'message': 'Retrying an invalid editing request in smaller steps'}
            else:
                malformed_streak = 0
            save()
        if phase == "tools":
            pending = next((m for m in reversed(state_messages) if isinstance(m, AIMessage) and m.tool_calls), None)
            calls = pending.tool_calls if pending else []
            for call in calls:
                call_id = call["id"]
                if call_id in completed:
                    continue
                ensure_access()
                if used >= total_budget or elapsed_before + time.monotonic() - started >= MAX_SECONDS:
                    clarification = g._budget_continuation_clarification(total_budget)
                    clarification["question"] = ("The job reached its work budget. Completed work is saved; "
                                                   "resume it to extend the budget, or keep this partial result.")
                    phase = "finalize"
                    break
                name, args = call["name"], call.get("args") or {}
                if inflight and inflight.get("id") == call_id and name.startswith(MUTATING_PREFIXES):
                    raise ValueError("A case action was interrupted before its result was recorded. Check the saved "
                                     "proposal before retrying; it has not been executed again.")
                inflight = {"id": call_id, "name": name}
                save()
                note(live_runs.progress_for_tool(step=used + 1, name=name, args=args, index=1, batch=1))
                begin = time.perf_counter()
                # Size the next observation against retained context, not the
                # lifetime sum of already-compacted reads. Reserve room for the
                # recent tool pairs so a long job need not reread tiny fragments.
                from services.agent.context_projection import project
                from services.agent.model_payloads import MIN_MESSAGE_CHARS
                retained = project(g.lean_messages(state_messages), budget_chars=run_budget)
                budget = max(MIN_MESSAGE_CHARS, min(run_budget // 4,
                    g.message_budget_chars(run_budget, g._tool_message_chars(retained))))
                context.page_budget_chars = budget
                free_before = context.free_calls
                try:
                    if name not in by_name:
                        raise ValueError(f'Unknown or unavailable tool: {name}')
                    switched_off = tool_groups.refusal(name, steer_applied)
                    if switched_off:
                        raise ValueError(switched_off)
                    # Checkpoint each call in order. Experimental parallel execution
                    # must not start another call before the first result is durable.
                    raw = g._free_call_refusal(name, context) or by_name[name].invoke(args)
                    output = raw if isinstance(raw, dict) else {"summary": str(raw), "data": raw}
                except Exception as exc:
                    error = g._tool_error_text(name, exc, by_name)
                    output = {"status": "error", "error": error, "summary": f"{name} failed: {error}", "data": {"error": error}}
                result_id, artifact = output.get("result_id"), output.get("artifact")
                saved_progress = (isinstance(artifact, dict) and bool(artifact.get('id'))
                    and output.get('status') != 'error'
                    and not any(previous.get('id') == artifact['id'] for previous in artifacts))
                if result_id:
                    context.model_views[result_id] = g.model_view(output.get("data"), artifact)
                if isinstance(artifact, dict):
                    artifacts.append(g.to_jsonable(artifact))
                clarification = output.get("clarification") or clarification
                model_payload = g.tool_message_payload(result_id=result_id, summary=str(output.get("summary") or ""),
                               data=output.get("data"), artifact=artifact, budget_chars=budget)
                item = dict(id=call_id, name=name, arguments=g.to_jsonable(args),
                            status="error" if output.get("status") == "error" else "success",
                            duration_ms=int((time.perf_counter() - begin) * 1000), summary=output.get("summary", ""),
                            result_id=result_id, error=output.get("error"), result_preview=g.truncate_payload(output.get("data")),
                            activity=g.activity_for_tool_call(name, args, call_id),
                            record=g.call_facts(name, args, output, model_payload))
                trace.append(item)
                state_messages.append(ToolMessage(tool_call_id=call_id, name=name, content=json.dumps(model_payload, ensure_ascii=False)))
                completed.add(call_id)
                used += 1 - (context.free_calls - free_before)
                inflight = None
                if saved_progress:
                    progress_trace_start = len(trace)
                # Do not keep spending on the same unsuccessful request or unchanged read.
                repeats = [t for t in trace[progress_trace_start:] if t['name'] == name and t['arguments'] == args
                           and t.get('result_preview') == item.get('result_preview')
                           and t.get('error') == item.get('error')]
                paging_errors = [t for t in trace[max(progress_trace_start, len(trace) - 10):]
                                 if t['name'] == name and t['status'] == 'error'] if name == 'read_tool_result_page' and item['status'] == 'error' else []
                if (len(repeats) >= 3 or len(paging_errors) >= 3) and not name.startswith(MUTATING_PREFIXES):
                    clarification = {"question": "The same step is returning no new information. Work is saved; "
                        "choose a different source or refine the request to continue.",
                        "context": {"reason": "no_progress"}, "options": [
                            {"id": "refine", "label": "Refine the request"},
                            {"id": "stop", "label": "Keep the partial result"}], "allow_free_text": True}
                    phase = "finalize"
                save()
                yield {"type": "tool_result", "tool": item}
                if artifact:
                    yield {"type": "artifact", "artifact": artifact}
                if phase == "finalize":
                    break
            else:
                phase = "finalize" if clarification else "agent"
            save()
        if phase == "finalize":
            note(live_runs.progress_writing(step=used))
            yield {'type': 'status', 'stage': 'checking', 'message': 'Checking saved deliverables against the request'}
            from services.agent.source_coverage import document_coverage
            source_receipts = document_coverage(source_messages, context.result_store)
            completion_issues = completion_checks.assess(context, artifacts, contract, render_receipts, source_receipts=source_receipts)
            # Review authored claims separately from the drafting conversation.
            # Grounded diagnoses enter the same bounded repair loop as other checks.
            if not clarification:
                from services.agent.evidence_review import review
                review_position = {}
                def record_review_position(current, total):
                    review_position.update(current=current, total=total)
                def invoke_review(request_messages):
                    ensure_access()
                    if elapsed_before + time.monotonic() - started >= MAX_SECONDS:
                        raise ValueError('The source review reached the job time budget. Saved review work can be resumed.')
                    position = f"{review_position['current']} of {review_position['total']}"
                    note({**live_runs.progress_thinking(step=used), 'title': f'Checking report sources: {position}',
                          'detail': 'Checking factual relationships and unsupported conclusions in the saved report.'})
                    response = g.invoke_model(runner.base_model, request_messages,
                                              note=note, step=used, should_cancel=should_cancel)
                    spent.append(response)
                    return response
                completion_issues.extend(review(completion_checks.latest_outputs(context, artifacts),
                    context.result_store, evidence_review_receipts, invoke=invoke_review, checkpoint=save,
                    max_chars=min(160_000, max(12_000, run_budget // 2)), on_progress=record_review_position))
            save()
            if completion_issues and not clarification and repair_attempts < 3 and used < total_budget:
                repair_attempts += 1
                state_messages.append(HumanMessage(content='Automated completion check, not a new investigator instruction. '
                    'Repair these specific issues using the existing artifact tools before finishing. Preserve the user scope, sources and corrections. '
                    'Each issue identifies the affected artifact and revision. Correct that artifact family; fixing a separate '
                    'copy does not repair the original. Address every affected family and preserve its version history. '
                    'Expand requested reports substantively; do not pad them with repeated text or '
                    'empty pages. Revise the latest saved artifact, then check it again. Checks do not certify source truth or '
                    'visual quality.\n' + json.dumps({'attempt': repair_attempts, 'delivery_contract': contract,
                                                     'issues': completion_issues}, ensure_ascii=False)))
                phase = 'agent'
                save()
                yield {'type': 'status', 'stage': 'repairing', 'message': f'Revising detected deliverable issues (pass {repair_attempts} of 3)'}
                continue
            # Remove incomplete tool batches before contacting providers with strict call-response pairing.
            safe_messages = list(state_messages)
            # A budget may stop inside a parallel call batch: every requested id still needs a response.
            pending_ids = {}
            for message in safe_messages:
                if isinstance(message, AIMessage):
                    pending_ids.update({c['id']: c['name'] for c in message.tool_calls})
                elif isinstance(message, ToolMessage):
                    pending_ids.pop(message.tool_call_id, None)
            safe_messages.extend(ToolMessage(tool_call_id=k, name=v,
                content='Not executed: work budget reached. No result exists for this call.') for k, v in pending_ids.items())
            if completion_issues:
                answer = completion_checks.revision_needed_answer(completion_checks.latest_outputs(context, artifacts), completion_issues)
            elif not clarification or (clarification.get("context") or {}).get("reason") in ("tool_budget_exhausted", "no_progress"):
                note(live_runs.progress_writing(step=used))
                checked_final_rules = final_answer_rules + ('\nThe saved work still needs revision. State the remaining '
                        'issues and do not claim the request is complete: ' + json.dumps(completion_issues, ensure_ascii=False)
                        if completion_issues else '')
                model, request_messages = g._finalizer_request(state_messages=model_context(safe_messages),
                    final_answer_rules=checked_final_rules, out_of_steps=bool(clarification),
                    agent_system_prompt=system_prompt(), agent_model=bound, base_model=runner.base_model)
                request_messages = g._with_found_so_far(request_messages, {'tool_trace': trace}, bool(clarification))
                response = g.invoke_model(model, request_messages, note=note, step=used, should_cancel=should_cancel)
                if getattr(response, "tool_calls", []):
                    spent.append(response)
                    response = g.invoke_model(runner.base_model, [SystemMessage(content=g._final_answer_system_prompt(checked_final_rules)),
                        *g.finalizer_messages(model_context(safe_messages)), HumanMessage(content=g._FINAL_ANSWER_REQUEST)],
                        note=note, step=used, should_cancel=should_cancel)
                replies, answer = g._in_plain_words(runner.base_model, response)
                spent.extend(replies)
                answer = g.link_named_files(g.link_document_citations(
                    g.replace_result_handles(answer, context.result_store)), g._tool_text({'messages': safe_messages}))
                answer = g._with_kept_sources(answer, context, bool(clarification))
            # A group the person switched off is named under Not examined, with its steps (rule 1).
            answer = tool_groups.with_not_examined(answer, steer_applied, last_step=used)
            phase = "done"
            save()
    if clarification:
        yield {"type": "clarification", "clarification": clarification}
    if answer:
        yield {"type": "answer", "answer": g._streamed_answer(context, case_id, answer)}
    yield {"type": "final", "result": {"answer": answer, "artifacts": artifacts, "clarification": clarification,
           'completion_issues': completion_issues, 'render_receipts': render_receipts, 'repair_attempts': repair_attempts,
           'source_coverage_receipts': source_receipts,
           'evidence_review_receipts': {key: value for key, value in evidence_review_receipts.items() if value.get('active')},
           "tool_trace": trace, "messages": spent, "steering": steer_applied, "usage": runner._extract_usage(spent[billed_count:]), **g._cross_case_result(context, case_id)}}
