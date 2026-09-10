from __future__ import annotations

import json
from typing import Any

from briefing.config import Config
from briefing.llm.base import Provider

CORE_RULES_PLACEHOLDER = "{{CORE_RULES}}"


def load_prompt(config: Config, prompt_name: str, *, require_core_rules: bool = True) -> str:
    """Load a prompt, injecting the shared non-negotiables.

    Edition prompts must carry the placeholder — a briefing written without those rules
    is not one we want to deliver. Utility prompts like the scorer opt out: they are
    classifiers, and briefing-writing instructions only muddy their output.
    """
    template = (config.prompts_dir / f"{prompt_name}.txt").read_text(encoding="utf-8")
    if CORE_RULES_PLACEHOLDER not in template:
        if require_core_rules:
            raise ValueError(f"prompt {prompt_name!r} is missing {CORE_RULES_PLACEHOLDER}")
        return template
    core_rules = (config.prompts_dir / "_core_rules.txt").read_text(encoding="utf-8")
    return template.replace(CORE_RULES_PLACEHOLDER, core_rules)


def generate(
    config: Config,
    provider: Provider,
    prompt_name: str,
    payload: dict[str, Any],
) -> str:
    system = load_prompt(config, prompt_name)
    user = json.dumps(payload, ensure_ascii=False, indent=2)
    return provider.complete(system=system, user=user, tier="generate").strip()
