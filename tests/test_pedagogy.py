import unittest

from app.pedagogy import NextAction, assess_answer


class AssessmentTests(unittest.TestCase):
    def test_uncertainty_never_demonstrates_mastery(self):
        for acceptable, confidence in [(True, 0.69), (False, 0.4), (None, 1.0)]:
            with self.subTest(acceptable=acceptable, confidence=confidence):
                result = assess_answer(is_acceptable=acceptable, confidence=confidence)
                self.assertFalse(result.demonstrates_mastery)
                self.assertEqual(result.next_action, NextAction.CLARIFY)

    def test_confident_accepted_answer_advances_at_threshold(self):
        result = assess_answer(is_acceptable=True, confidence=0.7)
        self.assertTrue(result.demonstrates_mastery)
        self.assertEqual(result.next_action, NextAction.ADVANCE)

    def test_confident_incorrect_answer_requires_practice(self):
        result = assess_answer(is_acceptable=False, confidence=0.95)
        self.assertFalse(result.demonstrates_mastery)
        self.assertEqual(result.next_action, NextAction.PRACTICE)

    def test_hints_fade_with_prior_demonstrated_mastery(self):
        budgets = [assess_answer(is_acceptable=True, confidence=1,
                                demonstrated_mastery=level).hint_budget
                   for level in (0, 0.4, 0.7, 1)]
        self.assertEqual(budgets, [3, 2, 1, 0])

    def test_exam_mode_always_has_no_hints(self):
        for acceptable in (True, False, None):
            result = assess_answer(is_acceptable=acceptable, confidence=0.9,
                                   exam_mode=True)
            self.assertEqual(result.hint_budget, 0)

    def test_invalid_evidence_is_rejected(self):
        for field in ("confidence", "demonstrated_mastery"):
            for value in (-0.1, 1.1, float("nan"), float("inf")):
                kwargs = {"is_acceptable": True, "confidence": 1, field: value}
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    assess_answer(**kwargs)


if __name__ == "__main__":
    unittest.main()
