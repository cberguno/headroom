import json
import re

from alpaca_trading import config


def extract_json(text):
    """Pull the first JSON object out of an LLM response, tolerating ```json fences
    and stray prose around it. Returns None (never raises) if nothing parses.
    """
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = [fence.group(1)] if fence else []
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        candidates.append(brace.group(0))
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def complete(system_prompt, user_prompt, model=None, temperature=0.4):
    """One-shot chat completion via litellm (supports OpenAI/Anthropic/Gemini/etc.
    based on which *_API_KEY is set and the model id used).
    """
    import litellm  # imported lazily so importing this module doesn't require the package at collection time

    response = litellm.completion(
        model=model or config.LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )
    return response["choices"][0]["message"]["content"]
