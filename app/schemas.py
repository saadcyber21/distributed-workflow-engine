from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class StepDefinition(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    type: Literal["echo", "delay", "llm_summary"]
    input: dict[str, Any] = Field(default_factory=dict)
    retries: int = Field(default=0, ge=0, le=5)


class WorkflowDefinition(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    steps: list[StepDefinition] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_step_ids(self):
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("step IDs must be unique")
        return self


class WorkflowOut(BaseModel):
    id: str
    name: str
    steps: list[StepDefinition]
    created_at: datetime


class RunCreate(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


class RunOut(BaseModel):
    id: str
    workflow_id: str
    status: str
    input: dict
    output: dict | None
    trace_id: str
    started_at: datetime
    finished_at: datetime | None
