from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.orm import Session

from models.llm_models import get_model_by_id
from postgres.models.agent import AgentThread
from postgres.models.cost_record import CostJobType
from postgres.models.user import User
from services.agent.cancellation import clear_cancel, is_cancelled, request_cancel
from services.agent.exports import AgentArtifactExport, AgentExportFormat, render_artifact_export
from services.agent.graph import AgentGraphRunner, AgentRunCancelled
from services.agent.schemas import (
    AgentArtifact,
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
                max_tool_calls=12,
                thread_id=str(thread.id),
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

            answer = (final_result.get("answer") or "").strip()
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
            artifacts = (final_result.get("artifacts") or [])[:5]
            artifact_records = storage.persist_artifacts(db, thread=thread, run=run, artifacts=artifacts)
            storage.persist_tool_trace(db, run=run, trace=tool_trace)
            storage.finish_run(
                db,
                run=run,
                status="completed",
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
                    {
                        "name": item.get("name"),
                        "status": item.get("status"),
                        "summary": item.get("summary"),
                    }
                    for item in tool_trace
                ],
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
                status="completed",
            )
            clear_cancel(run_id)
            yield {"type": "done", "response": response.model_dump(mode="json")}
        except AgentRunCancelled as exc:
            db.rollback()
            run = db.merge(run)
            storage.finish_run(db, run=run, status="cancelled", error=str(exc))
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

        history = self._build_history(db, thread=thread)
        runner = AgentGraphRunner(provider=provider, model_id=model.id)

        try:
            result = runner.invoke(
                case_id=str(request.case_id),
                messages=history,
                artifact_preference=request.artifact_preference,
                max_tool_calls=12,
                thread_id=str(thread.id),
            )
            answer = (result.get("answer") or "").strip()
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
            artifacts = (result.get("artifacts") or [])[:5]
            artifact_records = storage.persist_artifacts(db, thread=thread, run=run, artifacts=artifacts)
            storage.persist_tool_trace(db, run=run, trace=tool_trace)
            storage.finish_run(
                db,
                run=run,
                status="completed",
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
                        {
                            "name": item.get("name"),
                            "status": item.get("status"),
                            "summary": item.get("summary"),
                        }
                        for item in tool_trace
                    ],
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
                status="completed",
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

    def export_artifact(
        self,
        *,
        db: Session,
        user: User,
        artifact_id: UUID,
        export_format: AgentExportFormat,
    ) -> AgentArtifactExport:
        artifact = storage.get_artifact_for_user(db, artifact_id=artifact_id, user=user)
        return render_artifact_export(artifact, export_format)

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
            description=f"AI Agent Query: {request.message[:100]}",
            extra_metadata={
                "agent": True,
                "thread_id": str(thread_id),
                "run_id": str(run_id),
                "artifact_preference": request.artifact_preference,
            },
        )


agent_service = AgentService()
