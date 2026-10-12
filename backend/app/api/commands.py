"""Every exposed command becomes ``POST /api/commands/<command_name>``.

The request body is the command's own pydantic model, so OpenAPI (and the
generated frontend types) describe each command exactly. Authorisation is
done by the command bus, never here.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Body
from pydantic import BaseModel

from app.api.deps import Exec
from app.platform.commands import Command, bus


class CommandResponse(BaseModel):
    command_id: uuid.UUID
    result: Any = None
    replayed: bool = False


def build_router() -> APIRouter:
    router = APIRouter(prefix="/commands", tags=["commands"])
    for cmd_type in sorted(bus.registered(), key=lambda c: c.command_name):
        if not getattr(cmd_type, "exposed", True):
            continue
        router.add_api_route(
            f"/{cmd_type.command_name}",
            _endpoint(cmd_type),
            methods=["POST"],
            response_model=CommandResponse,
            name=cmd_type.command_name,
            summary=(cmd_type.__doc__ or cmd_type.command_name).strip().split("\n")[0],
            operation_id=f"cmd_{cmd_type.command_name.replace('.', '_')}",
        )
    return router


def _endpoint(cmd_type: type[Command]) -> Any:
    def endpoint(run: Exec, cmd: Any = Body(...)) -> CommandResponse:
        res = run(cmd)
        return CommandResponse(command_id=res.command_id, result=res.result, replayed=res.replayed)

    endpoint.__annotations__["cmd"] = cmd_type
    endpoint.__name__ = f"cmd_{cmd_type.command_name.replace('.', '_')}"
    return endpoint
