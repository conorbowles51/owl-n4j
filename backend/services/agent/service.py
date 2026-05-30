from __future__ import annotations

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
from services.ai_costs_service import CostOperationKind, record_cost
from services.case_service import check_case_access
from services.system_log_service import LogOrigin, LogType, system_log_service


DEFAULT_AGENT_MAX_TOOL_CALLS = 28


class AgentService:
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

        model = get_model_by_id(request.model)
        if not model:
            raise ValueError(f"Invalid model: {request.model}")
        provider = model.provider.value
        if request.provider and request.provider != provider:
            raise ValueError(f"Model {request.model} belongs to provider {provider}, not {request.provider}")

        thread = self._resolve_thread(db, user=user, request=request)
        user_message = storage.append_message(
            db,
            thread=thread,
            role="user",
            content=request.message,
        )
        run = storage.create_run(
            db,
            thread=thread,
            user=user,
            provider=provider,
            model_id=model.id,
            input_message=request.message,
            extra_metadata={"artifact_preference": request.artifact_preference},
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
                "server": "OpenAI (remote)" if provider == "openai" else "Ollama (local)",
            },
        }

        history = self._build_history(db, thread=thread)
        runner = AgentGraphRunner(provider=provider, model_id=model.id)
        final_result: dict[str, Any] | None = None

        try:
            for event in runner.stream(
                case_id=str(request.case_id),
                messages=history,
                artifact_preference=request.artifact_preference,
                max_tool_calls=DEFAULT_AGENT_MAX_TOOL_CALLS,
                thread_id=str(thread.id),
                available_artifacts=self._available_artifacts_for_runner(thread),
                should_cancel=lambda: is_cancelled(run_id),
            ):
                if event.get("type") == "final":
                    final_result = event.get("result") or {}
                    continue
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
            answer = (final_result.get("answer") or "").strip()
            if runner_clarification:
                answer = runner_clarification.question
            if not answer:
                answer = "I could not produce an answer from the available case data."

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
            storage.persist_tool_trace(db, run=run, trace=tool_trace)
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
                artifacts=[storage.to_api_artifact(record) for record in artifact_records],
                tool_trace=[AgentToolTraceItem(**self._public_trace_item(item)) for item in tool_trace],
                model_info=AgentModelInfo(
                    provider=provider,
                    model_id=model.id,
                    model_name=model.name,
                    server="OpenAI (remote)" if provider == "openai" else "Ollama (local)",
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
            )
            clear_cancel(run_id)
            yield {"type": "done", "response": response.model_dump(mode="json")}
        except AgentRunCancelled as exc:
            db.rollback()
            run = db.merge(run)
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

        model = get_model_by_id(request.model)
        if not model:
            raise ValueError(f"Invalid model: {request.model}")
        provider = model.provider.value
        if request.provider and request.provider != provider:
            raise ValueError(f"Model {request.model} belongs to provider {provider}, not {request.provider}")

        thread = self._resolve_thread(db, user=user, request=request)
        user_message = None
        if request.persist:
            user_message = storage.append_message(
                db,
                thread=thread,
                role="user",
                content=request.message,
            )

        run = storage.create_run(
            db,
            thread=thread,
            user=user,
            provider=provider,
            model_id=model.id,
            input_message=request.message,
            extra_metadata={"artifact_preference": request.artifact_preference},
        )
        db.flush()
        self._log_agent_event(
            db,
            action="agent_run_started",
            user=user,
            run=run,
            details={"thread_id": str(thread.id), "streaming": False},
        )

        history = self._build_history(db, thread=thread)
        runner = AgentGraphRunner(provider=provider, model_id=model.id)

        try:
            result = runner.invoke(
                case_id=str(request.case_id),
                messages=history,
                artifact_preference=request.artifact_preference,
                max_tool_calls=DEFAULT_AGENT_MAX_TOOL_CALLS,
                thread_id=str(thread.id),
                available_artifacts=self._available_artifacts_for_runner(thread),
            )
            runner_clarification = self._clarification_from_runner(
                result.get("clarification"),
                thread_id=str(thread.id),
                run_id=str(run.id),
                original_message=request.message,
            )
            answer = (result.get("answer") or "").strip()
            if runner_clarification:
                answer = runner_clarification.question
            if not answer:
                answer = "I could not produce an answer from the available case data."

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
            storage.persist_tool_trace(db, run=run, trace=tool_trace)
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
                artifacts=[storage.to_api_artifact(record) for record in artifact_records],
                tool_trace=[AgentToolTraceItem(**self._public_trace_item(item)) for item in tool_trace],
                model_info=AgentModelInfo(
                    provider=provider,
                    model_id=model.id,
                    model_name=model.name,
                    server="OpenAI (remote)" if provider == "openai" else "Ollama (local)",
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
                )
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

    def get_thread(self, *, db: Session, user: User, thread_id: UUID) -> AgentThreadDetail:
        return storage.get_thread_detail(db, thread_id=thread_id, user=user)

    def get_run(self, *, db: Session, user: User, run_id: UUID) -> AgentRunDetail:
        return storage.get_run_detail(db, run_id=run_id, user=user)

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
        )

    def _build_history(self, db: Session, *, thread: AgentThread) -> list[HumanMessage | AIMessage]:
        messages = storage.recent_messages(db, thread_id=thread.id, limit=20)
        history: list[HumanMessage | AIMessage] = []
        for message in messages:
            if message.role == "user":
                history.append(HumanMessage(content=message.content))
            elif message.role == "assistant":
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
        if provider != "openai" or not usage:
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
