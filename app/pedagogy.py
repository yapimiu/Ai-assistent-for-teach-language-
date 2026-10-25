"""Deterministic, formative learning decisions; never exam certification."""

from dataclasses import dataclass
from enum import StrEnum
import math


class NextAction(StrEnum):
    CLARIFY = "clarify"
    PRACTICE = "practice"
    ADVANCE = "advance"


@dataclass(frozen=True)
class LearningDecision:
    next_action: NextAction
    demonstrates_mastery: bool
    hint_budget: int


def assess_answer(
    *,
    is_acceptable: bool | None,
    confidence: float,
    demonstrated_mastery: float = 0.0,
    exam_mode: bool = False,
) -> LearningDecision:
    """Choose follow-up work from validated evidence.

    ``demonstrated_mastery`` is prior evidence in [0, 1], not an official
    proficiency rating. Uncertain assessments require clarification, even
    when the model provisionally labels the answer correct or incorrect.
    """
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("confidence must be finite and between 0 and 1")
    if not math.isfinite(demonstrated_mastery) or not 0 <= demonstrated_mastery <= 1:
        raise ValueError("demonstrated_mastery must be finite and between 0 and 1")
    if is_acceptable is not None and type(is_acceptable) is not bool:
        raise TypeError("is_acceptable must be a bool or None")

    hint_budget = 0 if exam_mode else math.ceil(3 * (1 - demonstrated_mastery))
    if confidence < 0.7 or is_acceptable is None:
        return LearningDecision(NextAction.CLARIFY, False, hint_budget)
    if is_acceptable:
        return LearningDecision(NextAction.ADVANCE, True, hint_budget)
    return LearningDecision(NextAction.PRACTICE, False, hint_budget)
