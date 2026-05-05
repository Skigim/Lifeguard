from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal, TypeAlias

from lifeguard.utils import drop_none

ResponseKind = Literal[
    "score",
    "note",
    "text",
    "boolean",
    "single_select",
    "multi_select",
]


class InvalidFormSchemaError(ValueError):
    """Raised when a form field or category has an invalid schema."""


@dataclass(frozen=True)
class ChoiceOption:
    id: str
    label: str

    def to_firestore(self) -> dict:
        return drop_none(asdict(self))

    @classmethod
    def from_firestore(cls, data: dict) -> "ChoiceOption":
        return cls(id=data["id"], label=data["label"])


@dataclass(frozen=True)
class ScoreOptions:
    min_value: int = 1
    max_value: int = 5
    allow_note: bool = True

    def to_firestore(self) -> dict:
        return drop_none(asdict(self))

    @classmethod
    def from_firestore(cls, data: dict) -> "ScoreOptions":
        return cls(
            min_value=data.get("min_value", 1),
            max_value=data.get("max_value", 5),
            allow_note=data.get("allow_note", True),
        )


@dataclass(frozen=True)
class SelectOptions:
    choices: list[ChoiceOption] = field(default_factory=list)
    min_selected: int = 1
    max_selected: int = 1

    def to_firestore(self) -> dict:
        return {
            "choices": [choice.to_firestore() for choice in self.choices],
            "min_selected": self.min_selected,
            "max_selected": self.max_selected,
        }

    @classmethod
    def from_firestore(cls, data: dict) -> "SelectOptions":
        return cls(
            choices=[ChoiceOption.from_firestore(choice) for choice in data.get("choices", [])],
            min_selected=data.get("min_selected", 1),
            max_selected=data.get("max_selected", 1),
        )


@dataclass(frozen=True)
class TextOptions:
    style: Literal["short", "paragraph"] = "short"
    placeholder: str = ""
    validation_regex: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "style", _ensure_text_style(self.style))

    def to_firestore(self) -> dict:
        return drop_none(asdict(self))

    @classmethod
    def from_firestore(cls, data: dict) -> "TextOptions":
        return cls(
            style=_ensure_text_style(data.get("style", "short")),
            placeholder=data.get("placeholder", ""),
            validation_regex=data.get("validation_regex", ""),
        )


@dataclass(frozen=True)
class BooleanOptions:
    true_label: str = "Yes"
    false_label: str = "No"

    def to_firestore(self) -> dict:
        return drop_none(asdict(self))

    @classmethod
    def from_firestore(cls, data: dict) -> "BooleanOptions":
        return cls(
            true_label=data.get("true_label", "Yes"),
            false_label=data.get("false_label", "No"),
        )


@dataclass(frozen=True)
class NoteOptions:
    placeholder: str = ""
    required_reference: bool = False

    def to_firestore(self) -> dict:
        return drop_none(asdict(self))

    @classmethod
    def from_firestore(cls, data: dict) -> "NoteOptions":
        return cls(
            placeholder=data.get("placeholder", ""),
            required_reference=data.get("required_reference", False),
        )


FormCategoryOptions: TypeAlias = (
    ScoreOptions | SelectOptions | TextOptions | BooleanOptions | NoteOptions
)

FormFieldType: TypeAlias = Literal["short_text", "paragraph", "url"]


def _ensure_response_kind(response_kind: str) -> ResponseKind:
    if response_kind in {
        "score",
        "note",
        "text",
        "boolean",
        "single_select",
        "multi_select",
    }:
        return response_kind
    raise InvalidFormSchemaError(f"Unknown response kind: {response_kind}")


def _ensure_field_type(field_type: str) -> FormFieldType:
    if field_type in {"short_text", "paragraph", "url"}:
        return field_type
    raise InvalidFormSchemaError(f"Unknown field type: {field_type}")


def _ensure_text_style(style: str) -> Literal["short", "paragraph"]:
    if style in {"short", "paragraph"}:
        return style
    raise InvalidFormSchemaError(f"Unknown text style: {style}")


def _default_options_for_kind(response_kind: ResponseKind) -> FormCategoryOptions:
    if response_kind == "score":
        return ScoreOptions()
    if response_kind in {"single_select", "multi_select"}:
        return SelectOptions()
    if response_kind == "text":
        return TextOptions()
    if response_kind == "boolean":
        return BooleanOptions()
    if response_kind == "note":
        return NoteOptions()
    raise InvalidFormSchemaError(f"Unknown response kind: {response_kind}")


def _options_from_firestore(
    response_kind: str,
    data: dict | None,
) -> FormCategoryOptions:
    resolved_kind = _ensure_response_kind(response_kind)
    payload = data or {}
    if resolved_kind == "score":
        return ScoreOptions.from_firestore(payload)
    if resolved_kind in {"single_select", "multi_select"}:
        return SelectOptions.from_firestore(payload)
    if resolved_kind == "text":
        return TextOptions.from_firestore(payload)
    if resolved_kind == "boolean":
        return BooleanOptions.from_firestore(payload)
    if resolved_kind == "note":
        return NoteOptions.from_firestore(payload)
    raise InvalidFormSchemaError(f"Unknown response kind: {resolved_kind}")


def _options_to_firestore(
    response_kind: str,
    options: FormCategoryOptions | None,
) -> dict:
    resolved_kind = _ensure_response_kind(response_kind)
    resolved_options = options or _default_options_for_kind(resolved_kind)

    if resolved_kind == "score" and isinstance(resolved_options, ScoreOptions):
        return resolved_options.to_firestore()
    if resolved_kind in {"single_select", "multi_select"} and isinstance(
        resolved_options, SelectOptions
    ):
        return resolved_options.to_firestore()
    if resolved_kind == "text" and isinstance(resolved_options, TextOptions):
        return resolved_options.to_firestore()
    if resolved_kind == "boolean" and isinstance(resolved_options, BooleanOptions):
        return resolved_options.to_firestore()
    if resolved_kind == "note" and isinstance(resolved_options, NoteOptions):
        return resolved_options.to_firestore()
    raise InvalidFormSchemaError(
        f"Options do not match response kind: {resolved_kind}"
    )


@dataclass(frozen=True)
class FormField:
    id: str
    label: str
    field_type: FormFieldType = "short_text"
    required: bool = True
    placeholder: str = ""
    validation_regex: str = ""

    def to_firestore(self) -> dict:
        return drop_none(asdict(self))

    @classmethod
    def from_firestore(cls, data: dict) -> "FormField":
        return cls(
            id=data["id"],
            label=data["label"],
            field_type=_ensure_field_type(data.get("field_type", "short_text")),
            required=data.get("required", True),
            placeholder=data.get("placeholder", ""),
            validation_regex=data.get("validation_regex", ""),
        )


@dataclass(frozen=True)
class FormCategory:
    id: str
    name: str
    description: str = ""
    response_kind: ResponseKind = "note"
    required: bool = True
    options: FormCategoryOptions | None = None

    def __post_init__(self) -> None:
        resolved_kind = _ensure_response_kind(self.response_kind)
        object.__setattr__(self, "response_kind", resolved_kind)
        if self.options is None:
            object.__setattr__(
                self,
                "options",
                _default_options_for_kind(resolved_kind),
            )
            return

        _options_to_firestore(resolved_kind, self.options)

    def to_firestore(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "response_kind": self.response_kind,
            "required": self.required,
            "options": _options_to_firestore(self.response_kind, self.options),
        }

    @classmethod
    def from_firestore(cls, data: dict) -> "FormCategory":
        response_kind = _ensure_response_kind(data.get("response_kind", "note"))
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            response_kind=response_kind,
            required=data.get("required", True),
            options=_options_from_firestore(response_kind, data.get("options")),
        )