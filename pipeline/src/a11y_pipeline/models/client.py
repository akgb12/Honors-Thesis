from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ModelMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["user", "assistant"]
    text: str
    image_png: bytes | None = None


class ModelRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)

    model: str
    system: str
    messages: list[ModelMessage]
    output_schema: type[BaseModel]
    prompt_version: str
    element_id: str
    max_tokens: int = Field(gt=0)


class ModelResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)

    output: BaseModel
    raw_text: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0)
    cost_usd: float = Field(ge=0)
    cached: bool = False


class ModelClient(Protocol):
    def complete_structured(self, request: ModelRequest) -> ModelResponse:
        # Complete one structured model request
        ...


ScriptValue = BaseModel | dict[str, Any]
