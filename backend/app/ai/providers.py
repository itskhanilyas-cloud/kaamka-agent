"""Text-generation providers behind one small interface, so the model can be swapped by config.

- MockTextProvider: deterministic, offline, clearly labelled. Used in tests and until Azure is wired.
- AzureOpenAITextProvider: Azure OpenAI v1 endpoint. In Azure it signs in with the app's
  managed identity (no key stored anywhere). A key is accepted only as a fallback for local use.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol


@dataclass
class TextResult:
    data: dict
    input_tokens: int
    output_tokens: int
    model: str
    is_mock: bool = False


class TextProvider(Protocol):
    name: str

    def generate_json(self, system: str, user: str, max_output_tokens: int) -> TextResult: ...


class ProviderError(Exception):
    pass


class MockTextProvider:
    """Returns well-formed placeholder content so the whole pipeline can run without spending money."""

    name = "mock"

    def generate_json(self, system: str, user: str, max_output_tokens: int) -> TextResult:
        brief = json.loads(user)
        topic = brief["idea"]
        n = brief["variants"]
        fmt = brief["format"]
        variants = []
        for i in range(n):
            v = {
                "hook": f"[MOCK {i + 1}] Stop wasting hours on {topic[:40]}",
                "caption": (f"[MOCK DRAFT — not AI output] {topic}.\n\nWe tested it on screen so you don't have to. "
                            "Try it today and tell us what worked.\n\nSave this for later."),
                "cta": "Save this for later",
                "hashtags": ["#AITools", "#StudyTips", "#Productivity", "#KaamKaAI"],
                "alt_text": f"Slide about {topic[:60]}",
            }
            if fmt == "CAROUSEL":
                v["slides"] = [{"title": f"Step {s}", "body": f"Placeholder step {s} for {topic[:30]}"} for s in range(1, 7)]
            if fmt == "REELS":
                v["script"] = [
                    {"seconds": "0-2", "visual": "Bold text on screen", "voiceover": v["hook"], "on_screen_text": "Try this"},
                    {"seconds": "2-12", "visual": "Screen recording of the tool", "voiceover": "Here's how it works.", "on_screen_text": "Step 1"},
                    {"seconds": "12-20", "visual": "Result side by side", "voiceover": "Save this for later.", "on_screen_text": "Save it"},
                ]
            variants.append(v)
        return TextResult(data={"variants": variants}, input_tokens=len(system + user) // 4,
                          output_tokens=300 * n, model="mock", is_mock=True)


class AzureOpenAITextProvider:
    name = "azure_openai"

    def __init__(self, endpoint: str, deployment: str, api_key: str | None = None, client=None):
        self.deployment = deployment
        if client is not None:  # injected in tests
            self.client = client
            return
        from openai import OpenAI

        base_url = endpoint.rstrip("/") + "/openai/v1/"
        if api_key:
            auth = api_key
        else:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            auth = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")
        self.client = OpenAI(base_url=base_url, api_key=auth, timeout=60, max_retries=2)

    def generate_json(self, system: str, user: str, max_output_tokens: int) -> TextResult:
        try:
            resp = self.client.chat.completions.create(
                model=self.deployment,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                max_completion_tokens=max_output_tokens,
            )
        except Exception as e:  # network, auth, quota: never include request content in the error
            raise ProviderError(f"Azure OpenAI call failed: {type(e).__name__}") from e
        text = resp.choices[0].message.content or ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ProviderError("model did not return valid JSON") from e
        usage = resp.usage
        return TextResult(data=data, input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                          output_tokens=getattr(usage, "completion_tokens", 0) or 0, model=self.deployment)


def get_text_provider(settings) -> TextProvider:
    if settings.text_provider == "azure_openai":
        if not settings.azure_openai_endpoint or not settings.azure_openai_deployment:
            raise ProviderError("KA_AZURE_OPENAI_ENDPOINT and KA_AZURE_OPENAI_DEPLOYMENT are required")
        key = settings.azure_openai_api_key.get_secret_value() if settings.azure_openai_api_key else None
        return AzureOpenAITextProvider(settings.azure_openai_endpoint, settings.azure_openai_deployment, key)
    return MockTextProvider()
