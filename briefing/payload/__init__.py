from briefing.payload.common import PayloadContext
from briefing.payload.evening import build_evening_payload
from briefing.payload.morning import build_morning_payload
from briefing.payload.weekend import build_weekend_evening_payload, build_weekend_morning_payload

BUILDERS = {
    "morning": build_morning_payload,
    "evening": build_evening_payload,
    "weekend_morning": build_weekend_morning_payload,
    "weekend_evening": build_weekend_evening_payload,
}

__all__ = ["BUILDERS", "PayloadContext"]
