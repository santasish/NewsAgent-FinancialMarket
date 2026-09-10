from __future__ import annotations

import logging
import time

from briefing.config import Config
from briefing.llm.base import model_for


class GeminiProvider:
    """Google Gemini free tier. Key: https://aistudio.google.com/apikey"""

    name = "gemini"

    def __init__(self, config: Config) -> None:
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "google-genai is not installed. Run: pip install -r requirements.txt"
            ) from exc

        # The SDK warns about automatic function calling on every generate_content call.
        # We pass no tools, so it is noise that would fill the cron logs.
        logging.getLogger("google_genai.models").setLevel(logging.ERROR)

        self.config = config
        self._genai = genai
        self._client = genai.Client(api_key=config.secret("GEMINI_API_KEY"))
        self._min_interval = 60.0 / config.get("llm.rate_limit.requests_per_minute", 10)
        self._last_call = 0.0
        self.usage: dict[str, int] = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    def complete(self, system: str, user: str, tier: str) -> str:
        from google.genai import types

        self._throttle()
        response = self._client.models.generate_content(
            model=model_for(self.config, self.name, tier),
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=self.config.get("llm.temperature", 0.2),
            ),
        )
        meta = getattr(response, "usage_metadata", None)
        if meta:
            self.usage["calls"] += 1
            self.usage["input_tokens"] += getattr(meta, "prompt_token_count", 0) or 0
            self.usage["output_tokens"] += getattr(meta, "candidates_token_count", 0) or 0

        return response.text or ""
