"""Thin wrapper around the OpenAI SDK pointed at Gemini, plus a small tool-calling agent loop.

Resilience:
- every request has a timeout (no more endless spinners)
- overload / rate-limit / timeout errors are retried with exponential backoff + jitter
- if the primary model stays overloaded, the next model in FALLBACK_MODELS is tried
"""
import json
import random
import re
import time
from typing import Any, Callable

import openai
from openai import OpenAI

from config import (GEMINI_BASE_URL, DEFAULT_MODEL, FALLBACK_MODELS,
                    REQUEST_TIMEOUT, RETRIES_PER_MODEL)

# Errors worth retrying: overloaded (503), rate-limited (429), server errors, timeouts, network drops
RETRYABLE = (openai.RateLimitError, openai.InternalServerError,
             openai.APITimeoutError, openai.APIConnectionError)


class LLMUnavailable(RuntimeError):
    """Raised when every model is overloaded after all retries."""


def parse_json(text: str) -> Any:
    """Parse JSON from an LLM reply, tolerating code fences and stray prose."""
    if not text:
        raise ValueError("Empty response from model")
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = cleaned.find(open_c), cleaned.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("Model did not return valid JSON")


class LLM:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        if not api_key:
            raise ValueError("Gemini API key is missing")
        # max_retries=0: we handle retries ourselves so waits stay short and visible
        self.client = OpenAI(api_key=api_key, base_url=GEMINI_BASE_URL,
                             timeout=REQUEST_TIMEOUT, max_retries=0)
        self.model = model
        self.models = list(dict.fromkeys([model] + FALLBACK_MODELS))  # de-duplicated, order kept
        self.last_model_used = model

    # ---------- resilient request ----------
    def _create(self, **kwargs):
        last_err = None
        for model in self.models:
            for attempt in range(RETRIES_PER_MODEL):
                try:
                    resp = self.client.chat.completions.create(model=model, **kwargs)
                    self.last_model_used = model
                    return resp
                except openai.NotFoundError as e:   # model name not available -> next model
                    last_err = e
                    break
                except RETRYABLE as e:
                    last_err = e
                    if attempt < RETRIES_PER_MODEL - 1:
                        time.sleep(min(2 ** attempt * 2, 10) + random.uniform(0, 1))  # 2s, 4s, 8s...
            # this model is still failing -> try the next one
        raise LLMUnavailable(
            "Gemini is overloaded right now and the backup models didn't respond either. "
            "Please try again in a minute or two."
        ) from last_err

    def ping(self, model: str) -> str:
        """One tiny request to a single model, no retries. Returns 'ok' or the error."""
        try:
            self.client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": "Reply with OK"}], max_tokens=5)
            return "ok"
        except openai.APIStatusError as e:
            return f"{e.status_code}: {'busy' if e.status_code in (429, 503) else str(e)[:80]}"
        except Exception as e:
            return str(e)[:80]

    # ---------- basic calls ----------
    def chat(self, messages: list, temperature: float = 0.4, **kwargs) -> str:
        resp = self._create(messages=messages, temperature=temperature, **kwargs)
        return resp.choices[0].message.content or ""

    def ask(self, system: str, user: str, temperature: float = 0.4) -> str:
        return self.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
        )

    def ask_json(self, system: str, user: str, temperature: float = 0.2) -> Any:
        messages = [
            {"role": "system", "content": system + "\nRespond with valid JSON only. No markdown, no commentary."},
            {"role": "user", "content": user},
        ]
        try:
            text = self.chat(messages, temperature, response_format={"type": "json_object"})
        except openai.BadRequestError:
            # only fall back when the model rejects response_format, not on overload errors
            text = self.chat(messages, temperature)
        try:
            return parse_json(text)
        except ValueError:
            repair = self.chat(
                [{"role": "system", "content": "Fix this into valid JSON. Output JSON only."},
                 {"role": "user", "content": text}], 0
            )
            return parse_json(repair)

    # ---------- agent loop (OpenAI-style function calling) ----------
    def run_agent(self, system: str, user: str, tools: list,
                  tool_impls: dict[str, Callable], max_steps: int = 6) -> str:
        """Let the model call tools until it produces a final answer."""
        messages: list = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for _ in range(max_steps):
            resp = self._create(messages=messages, tools=tools, tool_choice="auto")
            msg = resp.choices[0].message
            if not msg.tool_calls:
                return msg.content or ""
            # model_dump keeps Gemini's thought signatures (extra fields) intact
            messages.append(msg.model_dump(exclude_none=True))
            for tc in msg.tool_calls:
                fn = tool_impls.get(tc.function.name)
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    result = fn(**args) if fn else {"error": f"unknown tool {tc.function.name}"}
                except Exception as e:
                    result = {"error": str(e)}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False)[:12000],
                })
        messages.append({"role": "user", "content": "Stop searching and give your final answer now."})
        return self.chat(messages)
