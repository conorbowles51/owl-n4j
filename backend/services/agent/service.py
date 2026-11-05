from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.orm import Session

from models.llm_models import get_model_by_id
from postgres.models.agent import AgentThread
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
import services.agent.run_record as run_record
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
    ):
        if not request.persist:
            raise ValueError("Ephemeral agent runs are not supported yet")

        check_case_access(db, request.case_id, user, required_permission=("case", "view"))
        if request.all_cases and request.case_layer == "significant":
            raise ValueError("All-cases mode reads whole cases; switch the case layer to All data to use it.")
        allowed_entity_keys = (
            get_significant_entity_keys(db, case_id=request.case_id)
            if request.case_layer == "significant"
            else None
        )

        default_provider, default_model_id = get_workload_model(db, "agent")
        if request.provider and request.provider != default_provider:
            raise ValueError("Per-run provider overrides are disabled. Change Agent routing in Settings → AI settings.")
        if request.model and request.model != default_model_id:
            raise ValueError("Per-run model overrides are disabled. Change Agent routing in Settings → AI settings.")
        requested_model = default_model_id
        requested_provider = default_provider
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
            },
            mandate_override=mandate_context.override,
            tool_budget=DEFAULT_AGENT_MAX_TOOL_CALLS,
            **self._prompt_version(db),
        )
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
        yield {
            "type": "run_started",
            "thread_id": str(thread.id),
            "run_id": run_id,
            "user_message_id": str(user_message.id),
            "model_info": {
                "provider": provider,
                "model_id": model.id,
                "model_name": model.name,
                "server": f"{provider.title()} (remote)",
            },
        }

        history = (
            [HumanMessage(content=request.message)]
            if request.case_layer == "significant"
            else self._build_history(db, thread=thread, all_cases=request.all_cases)
        )
        runner = AgentGraphRunner(provider=provider, model_id=model.id, api_key=api_key)
        final_result: dict[str, Any] | None = None
        collected_trace: list[dict[str, Any]] = []

        try:
            for event in runner.stream(
                case_id=str(request.case_id),
                messages=history,
                artifact_preference=request.artifact_preference,
                max_tool_calls=DEFAULT_AGENT_MAX_TOOL_CALLS,
                thread_id=str(thread.id),
                available_artifacts=(
                    []
                    if request.case_layer == "significant"
                    else self._available_artifacts_for_runner(thread)
                ),
                should_cancel=lambda: is_cancelled(run_id),
                allowed_entity_keys=allowed_entity_keys,
                mandate_context_block=self._prompt_block(mandate_context.block, request, feedback),
                final_answer_rules=self._final_rules(request),
                proposer=self._proposer(db, user, request, provider, model, run, thread),
                user_id=str(user.id),
                all_cases=request.all_cases,
            ):
                if event.get("type") == "final":
                    final_result = event.get("result") or {}
                    continue
                if event.get("type") == "tool_result" and isinstance(event.get("tool"), dict):
                    # Each call is stored as soon as it has run (the record survives a stopped or dead run).
                    collected_trace.append(event["tool"])
                    self._store_call_now(db, run=run, sequence=len(collected_trace), item=event["tool"])
                    event = {**event, "tool": {k: v for k, v in event["tool"].items() if k != "record"}}
                yield event

            if is_cancelled(run_id):
                raise AgentRunCancelled("Agent run cancelled")
            if final_result is None:
                raise ValueError("Agent run did not produce a final result")

            runner_clarification = self._clarification_from_runner(
                final_result.get("clarification"),
                thread_id=str(thread.id),
                run_id=str(run.id),
                original_message=request.message,
            )
            answer = self._name_other_cases(db, run, final_result, request.case_id)
            if runner_clarification:
                answer = runner_clarification.question
            if not answer:
                answer = "I could not produce an answer from the available case data."
            answer, citation_check = storage.checked_answer(db, case_id=thread.case_id, answer=answer)
            storage.update_run_metadata(db, run=run, metadata={"citation_check": citation_check})

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

            tool_trace = final_result.get("tool_trace") or []
            artifacts = self._with_refinement_metadata(
                (final_result.get("artifacts") or [])[:5],
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
            run_record.persist_call_facts(
                db, run=run, trace=tool_trace, answer=answer,
                # Only artifacts that were kept: an artifact thrown away (a clarification) is no use of an item.
                artifacts=[storage.to_api_artifact(r).model_dump(mode="json") for r in artifact_records],
                messages=final_result.get("messages"),
                budget_exhausted=self._is_tool_budget_clarification(runner_clarification),
            )
            if runner_clarification:
                storage.update_run_metadata(
                    db,
                    run=run,
                    metadata={"clarification": runner_clarification.model_dump(mode="json")},
                )
            storage.finish_run(
                db,
                run=run,
                status="clarification_required" if runner_clarification else "completed",
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
                action="agent_clarification_requested" if runner_clarification else "agent_run_completed",
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
                status="clarification_required" if runner_clarification else "completed",
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
            self._record_stopped_run(db, run=run, trace=collected_trace)
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
                self._record_stopped_run(db, run=run, trace=collected_trace)
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
            }

    def handle_message(
        self,
        *,
        db: Session,
        user: User,
        request: AgentMessageRequest,
    ) -> AgentMessageResponse:
        if not request.persist:
            raise ValueError("Ephemeral agent runs are not supported yet")

        check_case_access(db, request.case_id, user, required_permission=("case", "view"))
        if request.all_cases and request.case_layer == "significant":
            raise ValueError("All-cases mode reads whole cases; switch the case layer to All data to use it.")
        allowed_entity_keys = (
            get_significant_entity_keys(db, case_id=request.case_id)
            if request.case_layer == "significant"
            else None
        )

        default_provider, default_model_id = get_workload_model(db, "agent")
        if request.provider and request.provider != default_provider:
            raise ValueError("Per-run provider overrides are disabled. Change Agent routing in Settings → AI settings.")
        if request.model and request.model != default_model_id:
            raise ValueError("Per-run model overrides are disabled. Change Agent routing in Settings → AI settings.")
        requested_model = default_model_id
        requested_provider = default_provider
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
        user_message = None
        if request.persist:
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
            },
            mandate_override=mandate_context.override,
            tool_budget=DEFAULT_AGENT_MAX_TOOL_CALLS,
            **self._prompt_version(db),
        )
        db.flush()
        self._log_agent_event(
            db,
            action="agent_run_started",
            user=user,
            run=run,
            details={"thread_id": str(thread.id), "streaming": False},
        )

        history = (
            [HumanMessage(content=request.message)]
            if request.case_layer == "significant"
            else self._build_history(db, thread=thread, all_cases=request.all_cases)
        )
        runner = AgentGraphRunner(provider=provider, model_id=model.id, api_key=api_key)

        try:
            result = runner.invoke(
                case_id=str(request.case_id),
                messages=history,
                artifact_preference=request.artifact_preference,
                max_tool_calls=DEFAULT_AGENT_MAX_TOOL_CALLS,
                thread_id=str(thread.id),
                available_artifacts=(
                    []
                    if request.case_layer == "significant"
                    else self._available_artifacts_for_runner(thread)
                ),
                allowed_entity_keys=allowed_entity_keys,
                mandate_context_block=self._prompt_block(mandate_context.block, request, feedback),
                final_answer_rules=self._final_rules(request),
                proposer=self._proposer(db, user, request, provider, model, run, thread),
                user_id=str(user.id),
                all_cases=request.all_cases,
            )
            runner_clarification = self._clarification_from_runner(
                result.get("clarification"),
                thread_id=str(thread.id),
                run_id=str(run.id),
                original_message=request.message,
            )
            answer = self._name_other_cases(db, run, result, request.case_id)
            if runner_clarification:
                answer = runner_clarification.question
            if not answer:
                answer = "I could not produce an answer from the available case data."
            answer, citation_check = storage.checked_answer(db, case_id=thread.case_id, answer=answer)
            storage.update_run_metadata(db, run=run, metadata={"citation_check": citation_check})

            usage = result.get("usage")
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

            tool_trace = result.get("tool_trace") or []
            artifacts = self._with_refinement_metadata(
                (result.get("artifacts") or [])[:5],
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
            run_record.persist_call_facts(
                db, run=run, trace=tool_trace, answer=answer,
                # Only artifacts that were kept: an artifact thrown away (a clarification) is no use of an item.
                artifacts=[storage.to_api_artifact(r).model_dump(mode="json") for r in artifact_records],
                messages=result.get("messages"),
                budget_exhausted=self._is_tool_budget_clarification(runner_clarification),
            )
            if runner_clarification:
                storage.update_run_metadata(
                    db,
                    run=run,
                    metadata={"clarification": runner_clarification.model_dump(mode="json")},
                )
            storage.finish_run(
                db,
                run=run,
                status="clarification_required" if runner_clarification else "completed",
                final_answer=answer,
                usage=usage,
            )

            assistant_message = None
            if request.persist:
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
                action="agent_clarification_requested" if runner_clarification else "agent_run_completed",
                user=user,
                run=run,
                details={
                    "tool_count": len(tool_trace),
                    "artifact_count": len(artifact_records),
                    "artifact_types": [record.type for record in artifact_records],
                    "streaming": False,
                    "question": runner_clarification.question if runner_clarification else None,
                },
            )
            db.commit()
            db.refresh(thread)
            db.refresh(run)

            return AgentMessageResponse(
                thread_id=str(thread.id),
                run_id=str(run.id),
                user_message_id=str(user_message.id) if user_message else None,
                assistant_message_id=str(assistant_message.id) if assistant_message else None,
                answer=answer,
                citation_check=citation_check,
                artifacts=[storage.to_api_artifact(record) for record in artifact_records],
                tool_trace=[AgentToolTraceItem(**self._public_trace_item(item)) for item in tool_trace],
                model_info=AgentModelInfo(
                    provider=provider,
                    model_id=model.id,
                    model_name=model.name,
                    server=f"{provider.title()} (remote)",
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
                status="clarification_required" if runner_clarification else "completed",
                mandate={
                    **mandate_context_service.metadata(
                        db, case_id=request.case_id, version_id=thread.mandate_version_id
                    ),
                    "temporary_override": bool(mandate_context.override),
                },
            )
        except Exception as exc:
            db.rollback()
            # Re-open a small transaction so failed runs are still visible when possible.
            try:
                check_case_access(db, request.case_id, user, required_permission=("case", "view"))
                thread = self._resolve_thread(db, user=user, request=request)
                failed_run = storage.create_run(
                    db,
                    thread=thread,
                    user=user,
                    provider=provider,
                    model_id=model.id,
                    input_message=request.message,
                    extra_metadata={"artifact_preference": request.artifact_preference},
                    tool_budget=DEFAULT_AGENT_MAX_TOOL_CALLS,
                    **self._prompt_version(db),
                )
                failed_run.record_summary = {"items_returned": 0, "basis": (
                    "The run failed before its tool calls could be stored (a run sent without streaming keeps its "
                    "calls only when it finishes); what it searched is not known.")}
                storage.finish_run(db, run=failed_run, status="failed", error=str(exc))
                self._log_agent_event(
                    db,
                    action="agent_run_failed",
                    user=user,
                    run=failed_run,
                    success=False,
                    error=str(exc),
                    details={"streaming": False},
                )
                db.commit()
            except Exception:
                db.rollback()
            raise

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

    def _build_history(self, db: Session, *, thread: AgentThread, all_cases: bool = False
                       ) -> list[HumanMessage | AIMessage]:
        messages = storage.recent_messages(db, thread_id=thread.id, limit=20)
        history: list[HumanMessage | AIMessage] = []
        for message in messages:
            if message.role == "user":
                history.append(HumanMessage(content=message.content))
            elif message.role == "assistant":
                run = getattr(message, "run", None)
                if not all_cases and isinstance(getattr(run, "extra_metadata", None), dict) \
                        and run.extra_metadata.get("all_cases"):
                    # An answer that read other cases never reaches a message that reads this case only.
                    history.append(AIMessage(content=WITHHELD_ALL_CASES_ANSWER))
                    continue
                history.append(AIMessage(content=message.content))
        return history

    @staticmethod
    def _available_artifacts_for_runner(thread: AgentThread) -> list[dict[str, Any]]:
        artifacts = sorted(
            storage.supported_artifacts(thread.artifacts),
            key=lambda item: item.created_at or item.id,
        )
        return [
            storage.to_api_artifact(artifact).model_dump(mode="json")
            for artifact in artifacts[-8:]
        ]

    @staticmethod
    def _is_tool_budget_clarification(clarification: AgentClarification | None) -> bool:
        return bool(
            clarification
            and isinstance(clarification.context, dict)
            and clarification.context.get("reason") == "tool_budget_exhausted"
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
            case_id=request.case_id,
            user_id=user.id,
            agent_run_id=run_id,
            description=f"AI Agent Query: {request.message[:100]}",
            extra_metadata={
                "agent": True,
                "thread_id": str(thread_id),
                "run_id": str(run_id),
                "artifact_preference": request.artifact_preference,
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
            question=str(payload.get("question") or "Can you clarify how you want me to proceed?"),
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
        normalized = request_message.lower()
        refinement_terms = (
            "add ",
            "remove ",
            "only ",
            "instead",
            "update",
            "refine",
            "expand",
            "narrow",
            "center",
            "centred",
            "centered",
        )
        if not artifacts or not any(term in normalized for term in refinement_terms):
            return artifacts
        previous_artifacts = sorted(thread.artifacts, key=lambda item: item.created_at or item.id)
        if not previous_artifacts:
            return artifacts
        source = previous_artifacts[-1]
        enriched: list[dict[str, Any]] = []
        for artifact in artifacts:
            metadata = dict(artifact.get("metadata") or {})
            metadata.setdefault("refinement", True)
            metadata.setdefault("source_artifact_id", str(source.id))
            metadata.setdefault("source_artifact_type", source.type)
            metadata.setdefault("source_artifact_title", source.title)
            metadata.setdefault("refinement_request", request_message[:500])
            enriched.append({**artifact, "metadata": metadata})
        return enriched

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
