from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.orm import Session

from models.llm_models import get_model_by_id
from postgres.models.agent import AgentRun, AgentThread
from postgres.models.cost_record import CostRecord
from postgres.models.cost_record import CostJobType
from postgres.models.user import User
from services.agent.cancellation import clear_cancel, is_cancelled, request_cancel
from services.agent.exports import AgentArtifactExport, AgentExportFormat, render_artifact_export
from services.agent.graph import AgentGraphRunner, AgentRunCancelled
from services.agent.json_utils import truncate_payload
from services.agent.schemas import (
    AgentArtifact,
    AgentClarification,
    AgentClarificationOption,
    AgentCost,
    AgentMessageRequest,
    AgentMessageResponse,
    AgentModelInfo,
    AgentRunDetail,
    AgentRunStatusResponse,
    AgentThreadDetail,
    AgentThreadSummary,
    AgentToolTraceItem,
)
import services.agent.storage as storage
import services.agent.model_choice as model_choice
import services.agent.plain_answer as plain_answer
import services.agent.run_record as run_record
import services.agent.run_settle as run_settle
from services import ai_budget
from services.ai_costs_service import CostOperationKind, record_cost
from services.ai_model_policy import get_workload_model
from services.ai_provider_credentials import get_provider_api_key
from services.case_service import check_case_access
from services.system_log_service import LogOrigin, LogType, system_log_service
from services.significant_service import get_significant_entity_keys
from services.mandate_context_service import mandate_context_service


DEFAULT_AGENT_MAX_TOOL_CALLS = 28
WITHHELD_ALL_CASES_ANSWER = ("[An earlier answer in this conversation read other cases in all-cases mode. It is "
                             "withheld from this message, which reads this case only.]")
logger = logging.getLogger(__name__)


class AgentService:
    @staticmethod
    def _proposer(db, user, request, provider, model, run, thread):
        """Who the run is for and which model runs it, for the proposal tools (the agent's only write). A person
        who can only view the case gets none: a proposal is a write, so it needs case edit."""
        try:
            check_case_access(db, request.case_id, user, required_permission=("case", "edit"))
            can_propose = True
        except Exception:  # noqa: BLE001 - view-only: the run reads, it does not propose
            can_propose = False
        return dict(for_name=user.name or user.email, for_user_id=str(user.id), for_email=user.email,
                    model=getattr(model, "name", None) or model.id, model_id=model.id, provider=provider,
                    run_id=str(run.id), thread_id=str(thread.id), can_propose=can_propose)

    def stream_message(
        self,
        *,
        db: Session,
        user: User,
        request: AgentMessageRequest,
        live=None,
        resume_run_id: UUID | None = None,
        resume_claim: str | None = None,
    ):
        """``live`` (services.agent.live_runs.LiveRun): the channel a detached run reports its steps to as they start;
        without it the steps still reach the run's stored progress through the heartbeat."""
        if not request.persist:
            raise ValueError("Ephemeral agent runs are not supported yet")

        check_case_access(db, request.case_id, user, required_permission=("case", "view"))
        ai_budget.check(db, request.case_id, "this agent question")
        if request.fault_drill:
            from services.agent.graph import FAULT_DRILL_CASES
            if str(request.case_id) not in FAULT_DRILL_CASES:
                raise ValueError("A fault drill runs only in the automated-checks case.")
        if request.all_cases and request.case_layer == "significant":
            raise ValueError("All-cases mode reads whole cases; switch the case layer to All data to use it.")
        allowed_entity_keys = (
            get_significant_entity_keys(db, case_id=request.case_id)
            if request.case_layer == "significant"
            else None
        )

        # The Settings default, or the model a person picked for this message (services.agent.model_choice, AG-08).
        choice, chosen = model_choice.resolve(db, model=request.model, provider=request.provider,
                                              reasoning=request.reasoning, workload_model=get_workload_model)
        requested_model = choice.model_id
        requested_provider = choice.provider
        model = get_model_by_id(requested_model)
        if not model:
            raise ValueError(f"Invalid model: {requested_model}")
        provider = model.provider.value
        if requested_provider != provider:
            raise ValueError(f"Model {requested_model} belongs to provider {provider}, not {requested_provider}")
        api_key = get_provider_api_key(db, provider)
        if not api_key:
            raise ValueError(
                f"{provider.title()} is not connected. Add its API key in Settings → AI settings."
            )

        thread = self._resolve_thread(db, user=user, request=request)
        mandate_context = mandate_context_service.resolve(
            db,
            case_id=request.case_id,
            version_id=thread.mandate_version_id,
            override=request.mandate_override,
        )
        from services.agent import durable_execution
        resume_checkpoint = None
        feedback = self._proposal_feedback(db, request)
        if resume_run_id is not None:
            run = storage.get_run_for_user(db, run_id=resume_run_id, user=user)
            if run.thread_id != thread.id or run.case_id != request.case_id:
                raise PermissionError("Saved work belongs to another conversation")
            durable_execution.consume_resume_claim(db, run, resume_claim)
            resume_checkpoint = (run.extra_metadata or {}).get("execution_checkpoint")
            if not resume_checkpoint:
                raise ValueError("This run has no saved checkpoint")
            resume_checkpoint = dict(resume_checkpoint, billed_count=(run.extra_metadata or {}).get('execution_billed_count', 0))
            if run.status == 'clarification_required':
                resume_checkpoint = durable_execution.extend_budget_checkpoint(resume_checkpoint)
            from postgres.models.agent import AgentMessage
            user_message = db.query(AgentMessage).filter(AgentMessage.thread_id == thread.id,
                AgentMessage.role == 'user', AgentMessage.run_id == run.id).first()
            if user_message is None:
                raise ValueError("The original question for this saved run could not be found")
            run.status, run.error, run.completed_at = 'running', None, None
            clear_cancel(str(run.id))
        else:
            user_message = storage.append_message(
                db,
                thread=thread,
                role="user",
                content=request.message,
            )
            feedback = self._proposal_feedback(db, request)
            run = storage.create_run(
                db,
                thread=thread,
                user=user,
                provider=provider,
                model_id=model.id,
                input_message=request.message,
                extra_metadata={
                    "artifact_preference": request.artifact_preference,
                    "case_layer": request.case_layer,
                    **self._workflow_metadata(request),
                    **({"all_cases": True} if request.all_cases else {}),
                    **({"proposal_feedback": feedback} if feedback else {}),
                    "model_choice": {"reasoning": choice.reasoning, "chosen_by_person": chosen,
                                     "written_by": model_choice.written_by(model.name, choice.reasoning)},
                },
                mandate_override=mandate_context.override,
                tool_budget=DEFAULT_AGENT_MAX_TOOL_CALLS,
                **self._prompt_version(db),
            )
            user_message.run_id = run.id
        import uuid
        execution_lease = resume_claim or str(uuid.uuid4())
        if resume_claim:
            durable_execution.lock_execution(db, run, execution_lease)
        task_specification = ((run.extra_metadata or {}).get('task_specification') if resume_run_id else None) or durable_execution.task_specification(db, thread, request)
        if 'delivery_contract' not in task_specification:
            from services.agent.completion_checks import delivery_contract
            task_specification = {**task_specification, 'delivery_contract': delivery_contract(task_specification.get('instructions') or [request.message])}
        durable_execution.write_metadata(db, run, {"execution_lease": execution_lease,
            "task_specification": task_specification})
        db.commit()
        db.refresh(thread)
        db.refresh(user_message)
        db.refresh(run)

        run_id = str(run.id)
        self._log_agent_event(
            db,
            action="agent_run_started",
            user=user,
            run=run,
            details={"thread_id": str(thread.id), "streaming": True},
        )
        from services.agent import live_runs
        yield {
            "type": "run_started",
            "started_at": run.started_at.isoformat() if run.started_at else live_runs.now_iso(),
            "server_time": live_runs.now_iso(),
            "progress": live_runs.progress_thinking(step=0),
            "thread_id": str(thread.id),
            "run_id": run_id,
            "user_message_id": str(user_message.id),
            "model_info": {
                "provider": provider,
                "model_id": model.id,
                "model_name": model.name,
                "server": f"{provider.title()} (remote)",
                "reasoning": choice.reasoning,
                "written_by": model_choice.written_by(model.name, choice.reasoning),
            },
        }

        history = (
            [HumanMessage(content=request.message)]
            if request.case_layer == "significant"
            else self._build_history(db, thread=thread, all_cases=request.all_cases, user=user)
        )
        runner = AgentGraphRunner(provider=provider, model_id=model.id, api_key=api_key, reasoning=choice.reasoning)
        if request.fault_drill:
            from services.agent import graph as agent_graph
            runner.base_model = agent_graph.FaultDrill(runner.base_model)
            storage.update_run_metadata(db, run=run, metadata={"fault_drill": "first model request fails once"})
            db.commit()
        # What the question names, so the answer stays on it (services.agent.question_scope, AG-02).
        focus_plan, focus = self._question_focus(db, request)
        final_result: dict[str, Any] | None = None
        collected_trace: list[dict[str, Any]] = list((resume_checkpoint or {}).get("trace", []))

        # Beaten while this worker lives, so a restart-killed run is settled as interrupted (services.agent.run_settle).
        hidden_tools, offer_note = self._tools_not_offered(db, request)
        if hidden_tools:
            storage.update_run_metadata(db, run=run, metadata={"tools_not_offered": sorted(hidden_tools)})
            db.commit()
        from services.agent import tool_groups
        if not (run.extra_metadata or {}).get("tool_groups_chosen"):
            storage.update_run_metadata(db, run=run, metadata={
                "tool_groups_chosen": tool_groups.chosen_from_question(request.message)})
            db.commit()
        heartbeat = run_settle.RunHeartbeat(run.id, lease=execution_lease)
        if live is not None:
            live.run_id = run_id
            live.on_progress_change = heartbeat.note_progress
            on_progress = live.set_progress
        else:
            on_progress = heartbeat.note_progress
        try:
            heartbeat.start()
            for event in runner.stream(
                case_id=str(request.case_id),
                messages=history,
                artifact_preference=request.artifact_preference,
                max_tool_calls=DEFAULT_AGENT_MAX_TOOL_CALLS,
                thread_id=str(thread.id),
                available_artifacts=(
                    []
                    if request.case_layer == "significant"
                    else self._available_artifacts_for_runner(thread, all_cases=request.all_cases, db=db, user=user)
                ),
                should_cancel=lambda: is_cancelled(run_id) or heartbeat.lost_lease,
                allowed_entity_keys=allowed_entity_keys,
                mandate_context_block="\n\n".join(x for x in (self._prompt_block(mandate_context.block, request, feedback),
                                                               offer_note, focus_plan) if x),
                hidden_tools=hidden_tools,
                final_answer_rules="\n\n".join(x for x in (self._final_rules(request), focus) if x),
                proposer=self._proposer(db, user, request, provider, model, run, thread),
                user_id=str(user.id),
                all_cases=request.all_cases,
                on_progress=on_progress,
                resume_checkpoint=resume_checkpoint,
                checkpoint_callback=lambda state: durable_execution.save_checkpoint(db, run, state, request, execution_lease),
                access_check=lambda cases: self._checkpoint_access(db, user, request, cases),
                delivery_contract=task_specification.get('delivery_contract'),
                steering=lambda: self._steering_requests(db, run.id),
            ):
                if event.get("type") == "steering":
                    # What the run took and at which step: the agent page's trail and card read it back.
                    storage.update_run_metadata(db, run=run, metadata={"steering_applied": event.get("applied") or []})
                    db.commit()
                if event.get("type") == "final":
                    final_result = event.get("result") or {}
                    continue
                if event.get("type") == "tool_result" and isinstance(event.get("tool"), dict):
                    # Each call is stored as soon as it has run (the record survives a stopped or dead run).
                    collected_trace.append(event["tool"])
                    self._store_call_now(db, run=run, sequence=len(collected_trace), item=event["tool"])
                    event = {**event, "tool": {k: v for k, v in event["tool"].items() if k != "record"}}
                if event.get("type") in ("answer", "assistant_draft") and isinstance(event.get("answer"), str):
                    # Text shown while the run works is in plain words too, as the stored answer is.
                    event = {**event, "answer": plain_answer.checked(event["answer"])[0]}
                if event.get("type") == "clarification" and isinstance(event.get("clarification"), dict):
                    question = event["clarification"].get("question")
                    if isinstance(question, str):
                        event = {**event, "clarification": {**event["clarification"],
                                                            "question": plain_answer.checked(question)[0]}}
                yield event

            if is_cancelled(run_id):
                raise AgentRunCancelled("Agent run cancelled")
            if final_result is None:
                raise ValueError("Agent run did not produce a final result")
            durable_execution.lock_execution(db, run, execution_lease)
            if run.status != 'running':
                raise AgentRunCancelled('Agent run stopped')

            runner_clarification = self._clarification_from_runner(
                final_result.get("clarification"),
                thread_id=str(thread.id),
                run_id=str(run.id),
                original_message=request.message,
            )
            answer = self._name_other_cases(db, run, final_result, request.case_id)
            if runner_clarification:
                # Out of steps: the partial answer stays, followed by the offer to continue.
                answer = (f"{answer}\n\n{runner_clarification.question}"
                          if answer and self._is_tool_budget_clarification(runner_clarification)
                          else runner_clarification.question)
            if not answer:
                answer = "I could not produce an answer from the available case data."
            answer, plain_check = plain_answer.checked(answer)  # internal terms in plain words (lx-agentlive C)
            answer, citation_check = storage.checked_answer(db, case_id=thread.case_id, answer=answer)
            storage.update_run_metadata(db, run=run, metadata={"citation_check": citation_check,
                                                               "plain_check": plain_check})

            usage = final_result.get("usage")
            cost_record = self._record_usage(
                db=db,
                usage=usage,
                provider=provider,
                model_id=model.id,
                request=request,
                user=user,
                thread_id=thread.id,
                run_id=run.id,
            )

            durable_execution.write_metadata(db, run, {"execution_billed_count": len(final_result.get("messages") or [])})
            tool_trace = final_result.get("tool_trace") or []
            artifacts = self._with_refinement_metadata(
                (final_result.get("artifacts") or []),
                request_message=request.message,
                thread=thread,
            )
            persist_partial_artifacts = self._is_tool_budget_clarification(runner_clarification)
            artifact_records = (
                storage.persist_artifacts(db, thread=thread, run=run, artifacts=artifacts)
                if artifacts and (not runner_clarification or persist_partial_artifacts)
                else []
            )
            storage.persist_tool_trace(db, run=run, trace=tool_trace, skip_existing=True)
            if runner_clarification:
                storage.update_run_metadata(
                    db,
                    run=run,
                    metadata={"clarification": runner_clarification.model_dump(mode="json")},
                )
            current_outputs = {}
            for artifact in artifact_records:
                meta = artifact.extra_metadata or {}
                key = meta.get('deliverable_id', str(artifact.id))
                old = current_outputs.get(key)
                if old is None or int(meta.get('revision', 1)) >= int((old.extra_metadata or {}).get('revision', 1)):
                    current_outputs[key] = artifact
            if not runner_clarification:
                storage.update_run_metadata(db, run=run, metadata={"clarification": None})
            needs_revision = any((a.extra_metadata or {}).get("validation", {}).get("status") == "needs_revision"
                                 for a in current_outputs.values()) or bool(final_result.get('completion_issues'))
            durable_execution.write_metadata(db, run, {'completion_checks': {
                'issues': final_result.get('completion_issues') or [], 'render_receipts': final_result.get('render_receipts') or {},
                'source_coverage': final_result.get('source_coverage_receipts') or [],
                'evidence_review': final_result.get('evidence_review_receipts') or {},
                'repair_attempts': final_result.get('repair_attempts', 0)}})
            completion_status = "clarification_required" if runner_clarification else ("needs_revision" if needs_revision else "completed")
            if needs_revision:
                from services.agent.completion_checks import revision_needed_answer
                answer = revision_needed_answer(artifacts, final_result.get('completion_issues') or [])
            run_record.persist_call_facts(
                db, run=run, trace=tool_trace, answer=answer,
                # Only retained artifacts contribute to the final saved answer.
                artifacts=[storage.to_api_artifact(r).model_dump(mode="json") for r in artifact_records],
                messages=final_result.get("messages"),
                budget_exhausted=self._is_tool_budget_clarification(runner_clarification),
            )
            storage.finish_run(
                db,
                run=run,
                status=completion_status,
                final_answer=answer,
                usage=usage,
            )
            assistant_message = storage.append_message(
                db,
                thread=thread,
                role="assistant",
                content=answer,
                run=run,
                provider=provider,
                model_id=model.id,
                artifact_ids=[str(record.id) for record in artifact_records],
                tool_trace_summary=[
                    self._trace_summary_item(item)
                    for item in tool_trace
                ],
            )
            self._log_agent_event(
                db,
                action="agent_clarification_requested" if runner_clarification else ("agent_run_needs_revision" if needs_revision else "agent_run_completed"),
                user=user,
                run=run,
                details={
                    "tool_count": len(tool_trace),
                    "artifact_count": len(artifact_records),
                    "artifact_types": [record.type for record in artifact_records],
                    "streaming": True,
                    "question": runner_clarification.question if runner_clarification else None,
                },
            )
            db.commit()
            db.refresh(run)
            db.refresh(assistant_message)

            response = AgentMessageResponse(
                thread_id=str(thread.id),
                run_id=str(run.id),
                user_message_id=str(user_message.id),
                assistant_message_id=str(assistant_message.id),
                answer=answer,
                citation_check=citation_check,
                artifacts=[storage.to_api_artifact(record) for record in artifact_records],
                tool_trace=[AgentToolTraceItem(**self._public_trace_item(item)) for item in tool_trace],
                model_info=AgentModelInfo(
                    provider=provider,
                    model_id=model.id,
                    model_name=model.name,
                    server=f"{provider.title()} (remote)",
                    reasoning=choice.reasoning,
                    written_by=model_choice.written_by(model.name, choice.reasoning),
                ),
                cost=AgentCost(
                    usd=float(cost_record.cost_usd),
                    prompt_tokens=cost_record.prompt_tokens,
                    completion_tokens=cost_record.completion_tokens,
                    total_tokens=cost_record.total_tokens,
                    cost_record_id=str(cost_record.id),
                )
                if cost_record
                else None,
                clarification=runner_clarification,
                status=completion_status,
                mandate={
                    **mandate_context_service.metadata(
                        db, case_id=request.case_id, version_id=thread.mandate_version_id
                    ),
                    "temporary_override": bool(mandate_context.override),
                },
            )
            clear_cancel(run_id)
            yield {"type": "done", "response": response.model_dump(mode="json")}
        except AgentRunCancelled as exc:
            db.rollback()
            run = db.merge(run)
            try:
                durable_execution.lock_execution(db, run, execution_lease)
            except RuntimeError:
                db.rollback()
                yield {"type": "error", "run_id": run_id, "thread_id": str(thread.id),
                       "message": "This saved job is continuing in another worker.", "retryable": False}
                return
            self._record_stopped_run(db, run=run, trace=collected_trace)
            self._record_stop_usage(db=db, runner=runner, provider=provider, model_id=model.id,
                                    request=request, user=user, thread_id=thread.id, run_id=run.id)
            storage.finish_run(db, run=run, status="cancelled", error=str(exc))
            self._log_agent_event(
                db,
                action="agent_run_cancelled",
                user=user,
                run=run,
                success=False,
                error=str(exc),
            )
            db.commit()
            clear_cancel(run_id)
            yield {
                "type": "cancelled",
                "run_id": run_id,
                "thread_id": str(thread.id),
                "message": str(exc),
            }
        except Exception as exc:
            db.rollback()
            try:
                run = db.merge(run)
                durable_execution.lock_execution(db, run, execution_lease)
            except RuntimeError:
                db.rollback()
                yield {"type": "error", "run_id": run_id, "thread_id": str(thread.id),
                       "message": "This saved job is continuing in another worker.", "retryable": False}
                return
            try:
                self._record_stopped_run(db, run=run, trace=collected_trace)
                self._record_stop_usage(db=db, runner=runner, provider=provider, model_id=model.id,
                                        request=request, user=user, thread_id=thread.id, run_id=run.id)
                storage.finish_run(db, run=run, status="failed", error=str(exc))
                self._log_agent_event(
                    db,
                    action="agent_run_failed",
                    user=user,
                    run=run,
                    success=False,
                    error=str(exc),
                    details={"streaming": True},
                )
                db.commit()
            except Exception:
                db.rollback()
            clear_cancel(run_id)
            yield {
                "type": "error",
                "run_id": run_id,
                "thread_id": str(thread.id),
                "message": str(exc),
                "retryable": bool(getattr(exc, "retryable", False)),
            }
        finally:
            heartbeat.stop()

    def handle_message(self, *, db: Session, user: User, request: AgentMessageRequest) -> AgentMessageResponse:
        for event in self.stream_message(db=db, user=user, request=request):
            if event.get("type") == "done":
                return AgentMessageResponse(**event["response"])
            if event.get("type") in ("error", "cancelled"):
                raise ValueError(event.get("message") or "Agent work stopped")
        raise ValueError("Agent work produced no response")

    @staticmethod
    def _checkpoint_access(db, user, request, other_cases):
        from services.agent.all_cases import may_open
        from postgres.models.case_membership import CaseMembership
        db.refresh(user, ["is_active", "global_role"])
        if not user.is_active:
            raise PermissionError("This user no longer has access")
        db.query(CaseMembership).filter(CaseMembership.case_id == request.case_id,
                                       CaseMembership.user_id == user.id).populate_existing().first()
        check_case_access(db, request.case_id, user, required_permission=("case", "view"))
        for case_id in other_cases:
            if not request.all_cases or not may_open(db, user, case_id):
                raise PermissionError("Access to a source case changed; the saved work cannot be resumed")

    @staticmethod
    def _steering_requests(db: Session, run_id) -> list[dict[str, Any]]:
        """The switches and notes the person has sent for this run, read fresh from the run row (the web process
        that took them is not this worker). A failed read takes nothing this step; the next step reads again."""
        from sqlalchemy import text
        try:
            if db.get_bind().dialect.name == "postgresql":
                value = db.execute(text("SELECT extra_metadata->'steering' FROM agent_runs WHERE id = :id"),
                                   {"id": str(run_id)}).scalar()
            else:
                from postgres.models.agent import AgentRun
                row = db.get(AgentRun, run_id)
                db.refresh(row, ["extra_metadata"])
                value = (row.extra_metadata or {}).get("steering")
        except Exception:  # noqa: BLE001
            logger.warning("Reading the run's tool switches failed", exc_info=True)
            return []
        return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []

    def steer_run(self, *, db: Session, user: User, run_id: UUID, kind: str, group: str | None = None,
                  on: bool | None = None, note: str | None = None) -> dict[str, Any]:
        """A tool switch or a note from the person who asked, for a run still working. Stored on the run; the worker
        takes it before its next step."""
        from services.agent import tool_groups
        from services.agent.durable_execution import write_metadata
        run = storage.get_run_for_user(db, run_id=run_id, user=user)
        db.query(AgentRun).filter(AgentRun.id == run.id).populate_existing().with_for_update().one()
        if run.status != "running":
            raise ValueError("This run has finished, so it cannot be changed. Ask a new question instead.")
        entry = tool_groups.new_entry(kind=kind, user_id=str(user.id), group=group, on=on, note=note)
        requested = [e for e in (run.extra_metadata or {}).get("steering") or [] if isinstance(e, dict)]
        write_metadata(db, run, {"steering": [*requested, entry]})
        self._log_agent_event(db, action="agent_run_steered", user=user, run=run,
                              details={"kind": entry["kind"], "group": entry.get("group"), "on": entry.get("on"),
                                       "note_chars": len(entry.get("note") or "")})
        db.commit()
        db.refresh(run)
        return {"entry": tool_groups.trail_entry(entry), "steering": storage.steering_view(run)}

    def cancel_run(self, *, db: Session, user: User, run_id: UUID) -> AgentRunStatusResponse:
        run = storage.get_run_for_user(db, run_id=run_id, user=user)
        if run.status == "running":
            request_cancel(str(run.id))
            storage.finish_run(
                db,
                run=run,
                status="cancelled",
                error="Cancellation requested by user",
            )
            self._log_agent_event(
                db,
                action="agent_run_cancelled",
                user=user,
                run=run,
                success=False,
                error="Cancellation requested by user",
            )
            db.commit()
            db.refresh(run)
        return AgentRunStatusResponse(
            run_id=str(run.id),
            thread_id=str(run.thread_id),
            status=run.status,
            error=run.error,
            completed_at=run.completed_at,
        )

    def list_threads(self, *, db: Session, user: User, case_id: UUID | None = None) -> list[AgentThreadSummary]:
        return storage.list_threads(db, user=user, case_id=case_id)

    def list_workflows(self, *, db: Session, user: User, case_id: UUID | None = None) -> dict[str, Any]:
        """The workflow catalogue; with a case, readiness on its own counts (read-only)."""
        from services.agent import workflows
        if case_id is None:
            return workflows.catalogue()
        check_case_access(db, case_id, user, required_permission=("case", "view"))
        return workflows.catalogue(workflows.case_counts(db.connection(), case_id))

    def get_thread(self, *, db: Session, user: User, thread_id: UUID) -> AgentThreadDetail:
        return storage.get_thread_detail(db, thread_id=thread_id, user=user)

    def adopt_current_mandate(self, *, db: Session, user: User, thread_id: UUID) -> dict[str, Any]:
        thread = storage.get_thread_for_user(db, thread_id=thread_id, user=user)
        active = mandate_context_service.active_version(db, case_id=thread.case_id)
        thread.mandate_version_id = active.id if active else None
        db.commit()
        return mandate_context_service.metadata(
            db, case_id=thread.case_id, version_id=thread.mandate_version_id
        )

    def active_runs(self, *, db: Session, user: User, case_id: UUID) -> list[dict[str, Any]]:
        return storage.active_runs(db, user=user, case_id=case_id)

    def get_run(self, *, db: Session, user: User, run_id: UUID) -> AgentRunDetail:
        return storage.get_run_detail(db, run_id=run_id, user=user)

    def get_run_record(self, *, db: Session, user: User, run_id: UUID) -> dict[str, Any]:
        from services.agent.run_record_export import load_record
        run = storage.get_run_for_user(db, run_id=run_id, user=user)
        return load_record(db, run)

    def export_run_record(self, *, db: Session, user: User, run_id: UUID, kind: str, export_format: str):
        """The DMD strategy summary or the "what was not examined" statement of one run (CSV or PDF)."""
        from services.agent.run_record_export import render_record_export
        run = storage.get_run_for_user(db, run_id=run_id, user=user)
        exported = render_record_export(db, run, kind, export_format)
        self._log_agent_event(db, action="agent_run_record_exported", user=user, run=run,
                              details={"kind": kind, "format": export_format})
        db.commit()
        return exported

    def get_cost_summary(self, *, db: Session, user: User) -> dict[str, Any]:
        records = (
            db.query(CostRecord)
            .filter(CostRecord.job_type == CostJobType.AI_ASSISTANT.value)
            .filter(CostRecord.user_id == user.id)
            .all()
        )
        agent_records = [
            record
            for record in records
            if isinstance(record.extra_metadata, dict) and record.extra_metadata.get("agent")
        ]
        linked = [record for record in agent_records if record.agent_run_id is not None]
        orphaned = [record for record in agent_records if record.agent_run_id is None]

        def summarize(rows: list[CostRecord]) -> dict[str, Any]:
            return {
                "records": len(rows),
                "usd": round(sum(float(record.cost_usd or 0) for record in rows), 6),
                "prompt_tokens": sum(record.prompt_tokens or 0 for record in rows),
                "completion_tokens": sum(record.completion_tokens or 0 for record in rows),
                "total_tokens": sum(record.total_tokens or 0 for record in rows),
            }

        return {
            "agent": summarize(agent_records),
            "linked_runs": summarize(linked),
            "orphaned_runs": summarize(orphaned),
        }

    def export_artifact(
        self,
        *,
        db: Session,
        user: User,
        artifact_id: UUID,
        export_format: AgentExportFormat,
    ) -> AgentArtifactExport:
        artifact = storage.get_artifact_for_user(db, artifact_id=artifact_id, user=user)
        exported = render_artifact_export(artifact, export_format)
        self._log_agent_event(
            db,
            action="agent_artifact_exported",
            user=user,
            run=artifact.run,
            details={"artifact_id": str(artifact.id), "artifact_type": artifact.type, "format": export_format},
        )
        db.commit()
        return exported

    @staticmethod
    def _workflow_metadata(request: AgentMessageRequest) -> dict[str, Any]:
        """The guided workflow this run follows, recorded on the run (agent-workflows). Unknown id: refused."""
        if not request.workflow_id:
            return {}
        from services.agent import workflows
        w = workflows.get(request.workflow_id)
        return {"workflow": {"id": w.id, "number": w.number, "title": w.title,
                             "steps": [s.tool for s in w.steps], "proposals": [t for t, _ in w.proposals]}}

    @staticmethod
    def _tools_not_offered(db: Session, request: AgentMessageRequest) -> tuple[frozenset[str], str]:
        """Tools whose kind of case material this case holds none of, so their definitions are not sent with every
        model turn (lx-agentlive B: 17,867 of 71,134 definition characters are phone-only, re-sent each turn of a
        run in a case with no phones). Each kind keeps its coverage tool, so the agent can still say the case holds
        none, and a guided workflow's own steps are always offered. All-cases runs and a count that failed (None)
        hide nothing. Returns the names and a plain note for the prompt.

        Decision (8 Nov): phones and financial records only, the two kinds whose count is exact
        (services.agent.workflows.case_counts). Reverse if a hidden tool is shown to be needed by a case with none
        of its material."""
        if request.all_cases:
            return frozenset(), ""
        from services.agent import capabilities, workflows
        try:
            counts = workflows.case_counts(db.connection(), request.case_id)
        except Exception:  # noqa: BLE001 - nothing hidden when the case cannot be counted
            logger.warning("Agent tool offer: case counts failed", exc_info=True)
            return frozenset(), ""
        keep = set((AgentService._workflow_metadata(request).get("workflow") or {}).get("steps") or [])
        others = lambda type_id: set().union(*[set(capabilities.tools_for_type(t["id"]))  # noqa: E731
                                               for t in capabilities.DATA_TYPES if t["id"] != type_id])
        hidden: set[str] = set()
        notes = []
        if counts.get("phones") == 0:
            hidden |= set(capabilities.tools_for_type("phones")) - others("phones") - {"phone_coverage"} - keep
            notes.append("This case holds no phone extractions, so the phone tools are not offered; say so if "
                         "asked about phones.")
        if counts.get("ledger") == 0 and counts.get("financial_sources") == 0 and counts.get("trades") == 0:
            hidden |= (set(capabilities.tools_for_type("financials")) - others("financials")
                       - {"get_financial_coverage"} - keep)
            notes.append("This case holds no bank or brokerage statements, so the payment tools are not offered; "
                         "say so if asked about money in statements.")
        brief = ""
        from services.agent import fit
        if fit.on("S"):
            # lx-agentfit R2b item S: what the case holds and lacks, before the first tool.
            from services.agent import case_briefing
            try:
                brief = case_briefing.briefing(db.connection(), request.case_id, counts)
            except Exception:  # noqa: BLE001 - no briefing is the behaviour with S off
                logger.warning("Agent case briefing failed", exc_info=True)
        return frozenset(hidden), "\n\n".join(x for x in (brief, " ".join(notes)) if x)

    @staticmethod
    def _question_focus(db: Session, request: AgentMessageRequest) -> tuple[str, str]:
        from services.agent import question_scope
        return question_scope.focus_for(db, request.case_id, request.message)

    @staticmethod
    def _final_rules(request: AgentMessageRequest) -> str:
        """The guided workflow's closing rules for the final answer, which is written under its own prompt."""
        if not request.workflow_id:
            return ""
        from services.agent import workflows
        return workflows.final_rules(workflows.get(request.workflow_id))

    @staticmethod
    def _proposal_feedback(db: Session, request: AgentMessageRequest) -> dict | None:
        """Past confirms and corrections per kind in this case. Not in all-cases mode: one case's outcomes are not
        another's."""
        if request.all_cases:
            return None
        from services.agent import proposal_feedback
        return proposal_feedback.safe_read(db, request.case_id)

    @staticmethod
    def _prompt_block(mandate_block: str, request: AgentMessageRequest, feedback: dict | None = None) -> str:
        """The mandate block, the guided workflow's plan when the run follows one, and what people did with earlier
        proposals in this case."""
        from services.agent import proposal_feedback, workflows
        plan = (workflows.render_block(workflows.get(request.workflow_id), budget=DEFAULT_AGENT_MAX_TOOL_CALLS)
                if request.workflow_id else "")
        return "\n\n".join(x for x in (mandate_block, plan, proposal_feedback.block(feedback)) if x)

    @staticmethod
    def _name_other_cases(db: Session, run, result: dict[str, Any], case_id) -> str:
        """All-cases mode: every citation of another case's record names that case (deterministic), and the run
        record keeps the cases read."""
        answer = (result.get("answer") or "").strip()
        if not result.get("all_cases"):
            return answer
        from services.agent.all_cases import name_cases_in_answer
        cited = {href: tuple(owner) for href, owner in (result.get("other_case_citations") or {}).items()}
        cases_read = result.get("cases_read") or []
        storage.update_run_metadata(db, run=run, metadata={"all_cases": True, "cases_read": cases_read})
        titles = {str(c["case_id"]): c.get("case_name") for c in cases_read if not c.get("this_case")}
        return name_cases_in_answer(answer, cited, str(case_id), titles=titles).strip()

    @staticmethod
    def _prompt_version(db: Session) -> dict[str, Any]:
        """The prompt version this run is given (sha256 and readable label), registered on first use."""
        try:
            sha, source = run_record.current_prompt_version()
            return {"prompt_version": sha, "prompt_version_label": run_record.register_prompt_version(db, sha, source)}
        except Exception as exc:  # noqa: BLE001 - the run goes ahead; its record says the version was not read
            logger.exception("Agent prompt version could not be computed")
            db.rollback()
            return {"prompt_version": None, "prompt_version_label": f"not recorded: {type(exc).__name__}"}

    @staticmethod
    def _store_call_now(db: Session, *, run, sequence: int, item: dict[str, Any]) -> None:
        try:
            storage.persist_tool_call(db, run=run, sequence=sequence, item=item)
            db.commit()
        except Exception:  # noqa: BLE001 - the final step stores any call not stored here
            logger.exception("Agent tool call %s of run %s could not be stored as it ran", sequence, run.id)
            db.rollback()

    @staticmethod
    def _record_stopped_run(db: Session, *, run, trace: list[dict[str, Any]]) -> None:
        """A cancelled or failed run keeps the calls it made and what they returned."""
        try:
            storage.persist_tool_trace(db, run=run, trace=trace, skip_existing=True)
            run_record.persist_call_facts(db, run=run, trace=trace, answer=None, artifacts=None, messages=None)
        except Exception:  # noqa: BLE001 - the run is still marked stopped; its record says what is missing
            logger.exception("Run record of stopped run %s could not be completed", run.id)
            db.rollback()
            run.record_summary = {"basis": "The run stopped and its record could not be completed; the tool calls "
                                           "stored as they ran are shown as stored."}

    def _resolve_thread(self, db: Session, *, user: User, request: AgentMessageRequest) -> AgentThread:
        if request.thread_id:
            return storage.get_thread_for_user(
                db,
                thread_id=request.thread_id,
                user=user,
                case_id=request.case_id,
            )
        return storage.create_thread(
            db,
            user=user,
            case_id=request.case_id,
            title=storage.summarize_title(request.message),
            mandate_version_id=(
                active.id
                if (active := mandate_context_service.active_version(db, case_id=request.case_id))
                else None
            ),
        )

    def _build_history(self, db: Session, *, thread: AgentThread, all_cases: bool = False, user=None
                       ) -> list[HumanMessage | AIMessage]:
        messages = storage.recent_messages(db, thread_id=thread.id, limit=20)
        history: list[HumanMessage | AIMessage] = []
        from postgres.models.agent import AgentMessage
        from services.agent.durable_execution import instruction_ledger
        earliest = getattr(messages[0], 'sequence_number', 0) if messages else 0
        earlier = (db.query(AgentMessage).filter(AgentMessage.thread_id == thread.id,
                   AgentMessage.sequence_number < earliest, AgentMessage.role == 'user')
                   .order_by(AgentMessage.sequence_number).all()) if earliest else []
        ledger = instruction_ledger(earlier, all_cases=all_cases)
        if ledger:
            import json
            history.append(HumanMessage(content="Earlier investigator instructions, in order. Preserve required "
                "subjects and accepted corrections. Later explicit instructions override earlier ones. "
                "This is historical context, not a new request:\n" + json.dumps(ledger, ensure_ascii=False)))
        for message in messages:
            if message.role == "user":
                history.append(HumanMessage(content=message.content))
            elif message.role == "assistant":
                run = getattr(message, "run", None)
                if run is not None and user is not None:
                    try:
                        storage.check_run_source_access(db, run, user)
                    except PermissionError:
                        history.append(AIMessage(content="[An earlier answer is withheld because access to a source case changed.]"))
                        continue
                if not all_cases and isinstance(getattr(run, "extra_metadata", None), dict) \
                        and run.extra_metadata.get("all_cases"):
                    # An answer that read other cases never reaches a message that reads this case only.
                    history.append(AIMessage(content=WITHHELD_ALL_CASES_ANSWER))
                    continue
                history.append(AIMessage(content=message.content))
        return history

    @staticmethod
    def _available_artifacts_for_runner(thread: AgentThread, *, all_cases=False, db=None, user=None) -> list[dict[str, Any]]:
        artifacts = sorted(
            storage.supported_artifacts(thread.artifacts),
            key=lambda item: item.created_at or item.id,
        )
        visible = []
        for artifact in artifacts:
            run_meta = artifact.run.extra_metadata or {} if artifact.run else {}
            if not all_cases and ((artifact.extra_metadata or {}).get('all_cases') or run_meta.get('all_cases')):
                continue
            if db is not None and user is not None:
                try:
                    storage.check_artifact_access(db, artifact, user)
                except PermissionError:
                    continue
            visible.append(storage.to_api_artifact(artifact).model_dump(mode="json"))
        return visible

    @staticmethod
    def _is_tool_budget_clarification(clarification: AgentClarification | None) -> bool:
        return bool(
            clarification
            and isinstance(clarification.context, dict)
            and clarification.context.get("reason") in ("tool_budget_exhausted", "no_progress")
        )

    @staticmethod
    def _public_trace_item(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "arguments": item.get("arguments") or {},
            "status": item.get("status") or "error",
            "duration_ms": item.get("duration_ms") or 0,
            "summary": item.get("summary"),
            "result_id": item.get("result_id"),
            "error": item.get("error"),
            "activity": item.get("activity"),
        }

    @staticmethod
    def _trace_summary_item(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "arguments": truncate_payload(item.get("arguments") or {}, max_items=8, max_text_chars=300),
            "status": item.get("status") or "error",
            "duration_ms": item.get("duration_ms") or 0,
            "summary": item.get("summary"),
            "result_id": item.get("result_id"),
            "error": item.get("error"),
            "activity": item.get("activity"),
        }

    def _record_stop_usage(self, *, db: Session, runner, run_id, **kwargs):
        """The billed tokens of a stopped or failed run, recorded in a savepoint. Recording them never decides how
        the run ends: an error here is logged and the run is still marked failed or cancelled with its own error
        (a raise here used to roll the mark back and leave the run 'running', later settled as a restart cut)."""
        try:
            usage = runner.spent_so_far()
            with db.begin_nested():
                self._record_usage(db=db, usage=usage, run_id=run_id, **kwargs)
                from postgres.models.agent import AgentRun
                from services.agent.durable_execution import write_metadata
                stopped = db.get(AgentRun, run_id)
                if stopped is not None:
                    write_metadata(db, stopped, {"execution_billed_count": len(getattr(runner, 'messages_so_far', []) or [])})
        except Exception:
            logger.exception("Could not record the spend of stopped agent run %s", run_id)

    @staticmethod
    def _record_usage(
        *,
        db: Session,
        usage: dict[str, Any] | None,
        provider: str,
        model_id: str,
        request: AgentMessageRequest,
        user: User,
        thread_id,
        run_id,
    ):
        if not usage:
            return None
        if not any(usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")):
            return None
        return record_cost(
            db=db,
            job_type=CostJobType.AI_ASSISTANT,
            provider=provider,
            model_id=model_id,
            operation_kind=CostOperationKind.CHAT_COMPLETION,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            prompt_cache_hit_tokens=usage.get("prompt_cache_hit_tokens"),
            prompt_cache_miss_tokens=usage.get("prompt_cache_miss_tokens"),
            case_id=request.case_id,
            user_id=user.id,
            agent_run_id=run_id,
            description=f"AI Agent Query: {request.message[:100]}",
            extra_metadata={
                "agent": True,
                "thread_id": str(thread_id),
                "run_id": str(run_id),
                "artifact_preference": request.artifact_preference,
                # Each model call's [prompt tokens, of them read from the cache, completion tokens].
                **({"steps": usage["steps"]} if usage.get("steps") else {}),
            },
        )

    @staticmethod
    def _clarification_from_runner(
        payload: dict[str, Any] | None,
        *,
        thread_id: str,
        run_id: str,
        original_message: str,
    ) -> AgentClarification | None:
        if not isinstance(payload, dict):
            return None
        options = payload.get("options")
        if not isinstance(options, list) or len(options) < 2:
            return None
        normalized_options = [
            AgentClarificationOption(
                id=str(option.get("id") or f"option_{index}"),
                label=str(option.get("label") or option.get("id") or f"Option {index}"),
                description=option.get("description"),
            )
            for index, option in enumerate(options[:4], start=1)
            if isinstance(option, dict)
        ]
        if len(normalized_options) < 2:
            return None
        return AgentClarification(
            question=plain_answer.checked(
                str(payload.get("question") or "Can you clarify how you want me to proceed?"))[0],
            options=normalized_options,
            allow_free_text=bool(payload.get("allow_free_text", True)),
            pending_run_id=run_id,
            thread_id=thread_id,
            original_message=original_message,
            context=payload.get("context") if isinstance(payload.get("context"), dict) else {},
        )

    @staticmethod
    def _with_refinement_metadata(
        artifacts: list[dict[str, Any]],
        *,
        request_message: str,
        thread: AgentThread,
    ) -> list[dict[str, Any]]:
        # Revision lineage comes from the selected artifact, never whichever artifact happened to be newest.
        return artifacts

    @staticmethod
    def _log_agent_event(
        db: Session,
        *,
        action: str,
        user: User,
        run,
        success: bool = True,
        error: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "run_id": str(run.id),
            "thread_id": str(run.thread_id),
            "case_id": str(run.case_id),
            "status": run.status,
            **(details or {}),
        }
        system_log_service.log(
            LogType.AI_ASSISTANT,
            LogOrigin.BACKEND,
            action,
            details=payload,
            user=user.email,
            success=success,
            error=error,
            db=db,
        )


agent_service = AgentService()
