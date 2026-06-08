"""Keyword-based ASR emotion trigger placeholder."""

from __future__ import annotations


FATIGUE_KEYWORDS = ("累", "困", "休息一下")
NEGATIVE_KEYWORDS = ("烦", "焦虑", "压力大", "不想做了", "好难受", "emo", "崩溃", "陪陪我")


class ASREmotionTrigger:
    """Detect simple emotion triggers from recognized ASR text."""

    def analyze(self, text: str | None) -> dict:
        normalized = self._normalize(text)
        if not normalized:
            return self._normal_result()

        fatigue_keyword = self._find_keyword(normalized, FATIGUE_KEYWORDS)
        if fatigue_keyword is not None:
            return {
                "should_trigger": True,
                "reason": "fatigue_keyword",
                "matched_keyword": fatigue_keyword,
                "emotion_tag": "tired",
                "confidence": 0.75,
                "fatigue_score": 0.8,
            }

        negative_keyword = self._find_keyword(normalized, NEGATIVE_KEYWORDS)
        if negative_keyword is not None:
            return {
                "should_trigger": True,
                "reason": "negative_keyword",
                "matched_keyword": negative_keyword,
                "emotion_tag": "stressed",
                "confidence": 0.7,
                "fatigue_score": 0.5,
            }

        return self._normal_result()

    @staticmethod
    def _normalize(text: str | None) -> str:
        if text is None:
            return ""
        return str(text).strip().lower()

    @staticmethod
    def _find_keyword(text: str, keywords: tuple[str, ...]) -> str | None:
        for keyword in keywords:
            if keyword.lower() in text:
                return keyword
        return None

    @staticmethod
    def _normal_result() -> dict:
        return {
            "should_trigger": False,
            "reason": "normal",
            "matched_keyword": None,
            "emotion_tag": "neutral",
            "confidence": 0.0,
            "fatigue_score": 0.0,
        }


def detect_asr_emotion_trigger(text: str | None) -> dict:
    """Convenience wrapper for one-off ASR trigger detection."""

    return ASREmotionTrigger().analyze(text)
