from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, get_args

from lifeguard.features.forms.schema import ResponseKind

SessionStatus = Literal["draft", "completed", "cancelled"]

_RESPONSE_KINDS = set(get_args(ResponseKind))
_SESSION_STATUSES = set(get_args(SessionStatus))


def _ensure_response_kind(response_kind: str) -> ResponseKind:
    if response_kind in _RESPONSE_KINDS:
        return response_kind
    raise ValueError(f"Unknown response kind: {response_kind}")


def _ensure_session_status(status: str) -> SessionStatus:
    if status in _SESSION_STATUSES:
        return status
    raise ValueError(f"Unknown session status: {status}")


def _ensure_response_value(
    response_kind: ResponseKind,
    value: int | str | bool | list[str],
) -> int | str | bool | list[str]:
    if response_kind == "score":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Score responses require an integer value")
        return value

    if response_kind in {"note", "text", "single_select"}:
        if not isinstance(value, str):
            raise ValueError(f"{response_kind} responses require a string value")
        return value

    if response_kind == "boolean":
        if not isinstance(value, bool):
            raise ValueError("Boolean responses require a boolean value")
        return value

    if response_kind == "multi_select":
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError("Multi-select responses require a list of string values")
        return value

    raise ValueError(f"Unknown response kind: {response_kind}")


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if hasattr(value, "to_datetime"):
        return value.to_datetime()
    raise ValueError(f"Unsupported datetime value: {value!r}")


@dataclass
class FormCategoryResponse:
    category_id: str
    response_kind: ResponseKind
    value: int | str | bool | list[str]
    note: str = ""
    reference: str = ""

    def __post_init__(self) -> None:
        self.response_kind = _ensure_response_kind(self.response_kind)
        self.value = _ensure_response_value(self.response_kind, self.value)

    def to_firestore(self) -> dict:
        return {
            "category_id": self.category_id,
            "response_kind": self.response_kind,
            "value": self.value,
            "note": self.note,
            "reference": self.reference,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> "FormCategoryResponse":
        return cls(
            category_id=data["category_id"],
            response_kind=_ensure_response_kind(data["response_kind"]),
            value=data.get("value"),
            note=data.get("note", ""),
            reference=data.get("reference", ""),
        )


@dataclass
class FormResponseSession:
    id: str
    guild_id: int
    feature_key: str
    owner_id: str
    responder_id: int
    responses: list[FormCategoryResponse] = field(default_factory=list)
    status: SessionStatus = "draft"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        self.status = _ensure_session_status(self.status)

    def to_firestore(self) -> dict:
        return {
            "id": self.id,
            "guild_id": self.guild_id,
            "feature_key": self.feature_key,
            "owner_id": self.owner_id,
            "responder_id": self.responder_id,
            "responses": [response.to_firestore() for response in self.responses],
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> "FormResponseSession":
        return cls(
            id=data["id"],
            guild_id=data["guild_id"],
            feature_key=data["feature_key"],
            owner_id=data["owner_id"],
            responder_id=data["responder_id"],
            responses=[
                FormCategoryResponse.from_firestore(item)
                for item in data.get("responses", [])
            ],
            status=_ensure_session_status(data.get("status", "draft")),
            created_at=_parse_datetime(data.get("created_at"))
            or datetime.now(timezone.utc),
            completed_at=_parse_datetime(data.get("completed_at")),
        )