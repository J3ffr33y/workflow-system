"""The only door to language models (CLAUDE.md rule 8).

Business modules describe a task (system prompt, user content, JSON schema)
and pass a deterministic ``fallback`` used by the offline "fake" provider.
The gateway decides whether the call may happen (provider switched on,
client consent), makes it, records it in ``ai_calls`` and returns parsed JSON.

Callers must treat every answer as a draft for a human to review.
"""

import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.platform.ai_gateway.models import AiCall

log = logging.getLogger("flow.ai")


class AiUnavailable(AppError):
    status_code = 409
    code = "ai_unavailable"


class AiConsentRequired(AppError):
    status_code = 409
    code = "ai_consent_required"


@dataclass(frozen=True)
class AiTask:
    name: str
    system: str
    user: str
    schema: dict[str, Any]
    client_id: uuid.UUID | None
    client_consent: bool


@dataclass(frozen=True)
class AiAnswer:
    data: dict[str, Any]
    provider: str
    model: str


def provider_info() -> dict[str, Any]:
    s = get_settings()
    return {
        "provider": s.ai_provider,
        "model": s.ai_model if s.ai_provider == "anthropic" else s.ai_provider,
        "external": s.ai_provider == "anthropic",
    }


def run_task(
    session: Session,
    task: AiTask,
    fallback: Callable[[], dict[str, Any]],
    *,
    command_id: uuid.UUID | None = None,
) -> AiAnswer:
    s = get_settings()
    started = time.monotonic()
    if s.ai_provider == "off":
        raise AiUnavailable("AI is switched off (FLOW_AI_PROVIDER=off)")
    if s.ai_provider == "fake":
        data = fallback()
        _record(session, task, "fake", "fake", "succeeded", started, command_id)
        return AiAnswer(data=data, provider="fake", model="fake")
    # External provider: client data leaves the system, so consent is required.
    if not task.client_consent:
        raise AiConsentRequired(
            "this client has not agreed to AI processing; set the client's AI consent field first"
        )
    if s.anthropic_api_key is None:
        raise AiUnavailable("FLOW_ANTHROPIC_API_KEY is not set")
    try:
        data, usage = _call_anthropic(task, s.anthropic_api_key.get_secret_value(), s.ai_model, s.ai_effort)
    except _Refused as e:
        _record(session, task, "anthropic", s.ai_model, "refused", started, command_id, error=str(e))
        raise AiUnavailable("the model declined this request") from e
    except Exception as e:
        log.warning("ai call failed: task=%s error=%s", task.name, type(e).__name__)
        _record(session, task, "anthropic", s.ai_model, "failed", started, command_id, error=type(e).__name__)
        raise AiUnavailable(f"model call failed ({type(e).__name__})") from e
    _record(session, task, "anthropic", s.ai_model, "succeeded", started, command_id, usage=usage)
    return AiAnswer(data=data, provider="anthropic", model=s.ai_model)


class _Refused(Exception):
    pass


def _call_anthropic(
    task: AiTask, api_key: str, model: str, effort: str
) -> tuple[dict[str, Any], tuple[int | None, int | None]]:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key, max_retries=2)
    output_config: Any = {"effort": effort, "format": {"type": "json_schema", "schema": task.schema}}
    # Streaming: long evidence inputs and report drafts can outlast a plain
    # request's HTTP timeout. "fallbacks: default" re-runs a policy decline on
    # Anthropic's recommended fallback model instead of failing the draft.
    with client.beta.messages.stream(
        model=model,
        max_tokens=32000,
        system=task.system,
        messages=[{"role": "user", "content": task.user}],
        output_config=output_config,
        betas=["server-side-fallback-2026-07-01"],
        extra_body={"fallbacks": "default"},
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise _Refused(getattr(msg.stop_details, "category", None) or "refusal")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("answer truncated at max_tokens")
    text = next(b.text for b in msg.content if b.type == "text")
    return json.loads(text), (msg.usage.input_tokens, msg.usage.output_tokens)


def _record(
    session: Session,
    task: AiTask,
    provider: str,
    model: str,
    status: str,
    started: float,
    command_id: uuid.UUID | None,
    *,
    usage: tuple[int | None, int | None] = (None, None),
    error: str | None = None,
) -> None:
    session.add(
        AiCall(
            command_id=command_id,
            task=task.name,
            provider=provider,
            model=model,
            client_id=task.client_id,
            status=status,
            input_tokens=usage[0],
            output_tokens=usage[1],
            duration_ms=int((time.monotonic() - started) * 1000),
            error=error,
        )
    )


__all__ = ["AiAnswer", "AiConsentRequired", "AiTask", "AiUnavailable", "provider_info", "run_task"]
