"""Model layer: stub for tests, OpenAI-compatible client for live runs, hard budget."""
import json
import os
import re


class BudgetExceeded(Exception):
    pass


class StubExhausted(Exception):
    pass


class Budget:
    """Hard caps per run. The pipeline stops, it never degrades silently."""

    def __init__(self, max_calls, max_total_completion_tokens, max_tokens_per_call):
        self.max_calls = max_calls
        self.max_total = max_total_completion_tokens
        self.per_call = max_tokens_per_call
        self.calls = 0
        self.completion_tokens = 0
        self.prompt_tokens = 0

    def before_call(self):
        if self.calls >= self.max_calls:
            raise BudgetExceeded(f"call cap reached ({self.max_calls})")
        if self.completion_tokens >= self.max_total:
            raise BudgetExceeded(f"completion token cap reached ({self.max_total})")
        self.calls += 1

    def record(self, usage):
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)

    def summary(self):
        return {"calls": self.calls, "prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens}


class StubModel:
    """Scripted responses, in order. Proves the plumbing; says nothing about model quality."""

    def __init__(self, responses, name="stub"):
        self.responses, self.name, self.i = list(responses), name, 0

    def complete(self, system, user, max_tokens, temperature):
        if self.i >= len(self.responses):
            raise StubExhausted(f"{self.name}: no scripted response for call {self.i + 1}")
        r = self.responses[self.i]
        self.i += 1
        return (r(system, user) if callable(r) else r), {"prompt_tokens": 0, "completion_tokens": 0}


class OpenAICompatModel:
    """Any OpenAI-compatible endpoint (for example NVIDIA's). The key comes from the environment only."""

    def __init__(self, model, base_url, api_key_env):
        key = os.environ.get(api_key_env)
        if not key:
            raise RuntimeError(f"set {api_key_env} in the environment; keys are never read from files or arguments")
        from openai import OpenAI  # imported lazily so tests need no network package

        self.name, self.client = model, OpenAI(base_url=base_url, api_key=key)

    def complete(self, system, user, max_tokens, temperature):
        r = self.client.chat.completions.create(
            model=self.name,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature, top_p=1, max_tokens=max_tokens, stream=False,
        )
        u = getattr(r, "usage", None)
        usage = {"prompt_tokens": getattr(u, "prompt_tokens", 0), "completion_tokens": getattr(u, "completion_tokens", 0)}
        return r.choices[0].message.content or "", usage


class Metered:
    """Wraps a model with the shared budget."""

    def __init__(self, model, budget, temperature):
        self.model, self.budget, self.temperature = model, budget, temperature

    @property
    def name(self):
        return self.model.name

    def chat(self, system, user):
        self.budget.before_call()
        text, usage = self.model.complete(system, user, self.budget.per_call, self.temperature)
        self.budget.record(usage)
        return text


def extract_json(text):
    """Pull one JSON object out of model text: strips reasoning blocks and code fences."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"```(?:json)?", "", text)
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError("no JSON object found in model output")
