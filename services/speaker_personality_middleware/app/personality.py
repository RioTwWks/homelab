"""Map recognized speaker labels to Hermes personality profiles."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)

VALID_PERSONALITIES = frozenset({"child", "student", "adult"})


@dataclass(frozen=True)
class PersonalityDecision:
    personality: str
    speaker: str | None
    confidence: float
    used_default: bool
    reason: str


def resolve_personality(
    settings: Settings,
    recognition: dict[str, Any],
) -> PersonalityDecision:
    """
    Pick personality from recognition result and configured map.

    Falls back to ``default_personality`` (adult) when confidence is low or speaker unknown.
    """
    speaker_raw = recognition.get("speaker")
    speaker = str(speaker_raw).strip() if speaker_raw is not None else ""
    try:
        confidence = float(recognition.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    threshold = settings.confidence_threshold
    default = settings.default_personality
    if default not in VALID_PERSONALITIES:
        default = "adult"

    if confidence < threshold:
        logger.info(
            "Low confidence %.3f < %.3f — using default personality %s",
            confidence,
            threshold,
            default,
        )
        return PersonalityDecision(
            personality=default,
            speaker=speaker or None,
            confidence=confidence,
            used_default=True,
            reason="confidence_below_threshold",
        )

    if not speaker:
        return PersonalityDecision(
            personality=default,
            speaker=None,
            confidence=confidence,
            used_default=True,
            reason="empty_speaker",
        )

    mapped = settings.personality_map.get(speaker)
    if mapped:
        personality = mapped if mapped in VALID_PERSONALITIES else default
        return PersonalityDecision(
            personality=personality,
            speaker=speaker,
            confidence=confidence,
            used_default=personality == default and mapped not in VALID_PERSONALITIES,
            reason="mapped" if personality == mapped else "invalid_map_target",
        )

    # Unknown speaker with high confidence — safe default adult
    logger.info("Speaker %s not in personality_map — default %s", speaker, default)
    return PersonalityDecision(
        personality=default,
        speaker=speaker,
        confidence=confidence,
        used_default=True,
        reason="speaker_not_mapped",
    )
