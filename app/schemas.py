from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ErrorDetail(StrictModel):
    error_type: str = Field(min_length=1, max_length=60)
    topic: str = Field(min_length=1, max_length=100)
    original: str = Field(max_length=2000)
    corrected: str = Field(max_length=2000)
    explanation_ru: str = Field(min_length=1, max_length=2000)


class Assessment(StrictModel):
    skill: Literal["reading", "grammar", "vocabulary", "writing"]
    task_id: int
    answer_text: str = Field(max_length=6000)
    is_acceptable: bool | None
    errors: list[ErrorDetail] = Field(max_length=12)
    corrected_answer: str = Field(max_length=6000)
    explanation_ru: str = Field(max_length=4000)
    feedback_ro: str = Field(max_length=2000)
    estimated_level: Literal["unknown", "A1", "A2", "B1", "B2"]
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    recommended_next_action: Literal["clarify", "practice", "advance"]

    @model_validator(mode="after")
    def accepted_has_no_errors(self):
        if self.is_acceptable is True and self.errors:
            raise ValueError("Accepted answers must not contain errors")
        return self


class TeachingTask(StrictModel):
    skill: Literal["reading", "grammar", "vocabulary", "writing"]
    topic: str = Field(min_length=1, max_length=100)
    objective_ru: str = Field(min_length=1, max_length=1000)
    explanation_ru: str = Field(min_length=1, max_length=3000)
    prompt_ro: str = Field(min_length=1, max_length=4000)
    reference_answer: str = Field(min_length=1, max_length=3000)
