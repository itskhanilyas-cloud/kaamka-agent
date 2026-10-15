import json
from types import SimpleNamespace

import pytest

from app.ai import generator, providers, quality
from app.services import budget
from tests.conftest import OWNER, as_owner

PRICING = generator.Pricing(in_inr_per_m=100, out_inr_per_m=600)


# --- fake Azure OpenAI client: records the request, returns a canned response ----------
class FakeCompletions:
    def __init__(self, content: str, fail: Exception | None = None):
        self.content, self.fail, self.calls = content, fail, []

    def create(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise self.fail
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
                               usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=2000))


def fake_azure(content: str, fail: Exception | None = None):
    comp = FakeCompletions(content, fail)
    client = SimpleNamespace(chat=SimpleNamespace(completions=comp))
    return providers.AzureOpenAITextProvider("https://x.openai.azure.com/", "text-main", client=client), comp


GOOD_VARIANT = {
    "hook": "Turn a 40-page PDF into notes in 10 minutes",
    "caption": "Exams close? Here is a free workflow: upload your PDF, ask for a one-page summary, then turn it "
               "into flashcards. Test it on one chapter first. Save this for revision week.",
    "cta": "Save this for revision week",
    "hashtags": ["#AITools", "#StudyTips", "#ExamPrep"],
    "alt_text": "Carousel cover showing a PDF turning into notes",
    "slides": [{"title": f"Step {i}", "body": "Short clear step."} for i in range(1, 7)],
}


def run(db, provider, **kw):
    args = dict(idea="Turn long PDFs into revision notes", media_type="CAROUSEL", pillar="workflow", variants=1,
                pricing=PRICING, monthly_cap_inr=100, max_output_tokens=4000, actor=OWNER)
    args.update(kw)
    return generator.generate(db, provider, **args)


# --- provider + generator -------------------------------------------------------------
def test_azure_provider_sends_json_request_to_deployment(db):
    provider, comp = fake_azure(json.dumps({"variants": [GOOD_VARIANT]}))
    out = run(db, provider)
    call = comp.calls[0]
    assert call["model"] == "text-main" and call["response_format"] == {"type": "json_object"}
    assert call["max_completion_tokens"] == 4000
    assert out[0]["quality"]["blocked"] is False and out[0]["is_mock"] is False


def test_actual_cost_replaces_estimate(db):
    provider, _ = fake_azure(json.dumps({"variants": [GOOD_VARIANT]}))
    run(db, provider)
    # 1000 in @ ₹100/M + 2000 out @ ₹600/M = ₹0.10 + ₹1.20
    assert budget.spent_this_month(db) == pytest.approx(1.3, abs=0.01)


def test_budget_cap_blocks_before_calling_model(db):
    budget.reserve(db, "video_ai", 99.99, 100, OWNER)
    provider, comp = fake_azure(json.dumps({"variants": [GOOD_VARIANT]}))
    with pytest.raises(budget.BudgetExceeded):
        run(db, provider)
    assert comp.calls == []  # no money spent


def test_provider_failure_releases_reservation_and_hides_details(db):
    provider, _ = fake_azure("", fail=RuntimeError("401 key=sk-secretsecretsecret"))
    with pytest.raises(providers.ProviderError) as e:
        run(db, provider)
    assert "secret" not in str(e.value)
    assert budget.spent_this_month(db) == 0


def test_invalid_json_is_an_error(db):
    provider, _ = fake_azure("not json")
    with pytest.raises(providers.ProviderError):
        run(db, provider)


def test_input_validation(db):
    provider = providers.MockTextProvider()
    for bad in (dict(pillar="crypto"), dict(variants=9), dict(idea="hi"), dict(media_type="STORIES")):
        with pytest.raises(generator.GenerationError):
            run(db, provider, **bad)


def test_mock_is_labelled_and_free(db):
    out = run(db, providers.MockTextProvider(), variants=2, media_type="REELS", pillar="tool_test")
    assert len(out) == 2 and all(o["is_mock"] for o in out)
    assert all("[MOCK" in o["variant"]["caption"] for o in out)
    assert budget.spent_this_month(db) == 0


def test_brief_carries_brand_rules_and_no_invented_results():
    system, user = generator.build_brief("Test 3 free PPT makers", "REELS", "tool_test", 2, True, None)
    assert "#Affiliate" in system and "guaranteed" in system
    assert json.loads(user)["test_notes"].startswith("none")


# --- quality checklist ----------------------------------------------------------------
def test_quality_passes_good_variant():
    r = quality.evaluate(GOOD_VARIANT, "CAROUSEL", False)
    assert r.score == 100 and not r.blocked


def test_quality_blocks_overclaiming():
    bad = dict(GOOD_VARIANT, caption=GOOD_VARIANT["caption"] + " Guaranteed to go viral!")
    r = quality.evaluate(bad, "CAROUSEL", False)
    assert r.blocked and any(c.name == "no_overclaiming" and not c.passed for c in r.checks)


def test_quality_blocks_missing_affiliate_disclosure():
    assert quality.evaluate(GOOD_VARIANT, "CAROUSEL", True).blocked
    ok = dict(GOOD_VARIANT, caption="#Affiliate " + GOOD_VARIANT["caption"])
    assert not quality.evaluate(ok, "CAROUSEL", True).blocked


def test_quality_reel_hook_timing():
    reel = dict(GOOD_VARIANT, script=[{"seconds": "0-5", "visual": "x", "voiceover": "y", "on_screen_text": "z"}])
    r = quality.evaluate(reel, "REELS", False)
    assert any(c.name == "reel_opens_fast" and not c.passed for c in r.checks)


def test_variants_sorted_best_first(db):
    weak = dict(GOOD_VARIANT, hashtags=["nohash"], cta="")
    provider, _ = fake_azure(json.dumps({"variants": [weak, GOOD_VARIANT]}))
    out = run(db, provider, variants=2)
    assert out[0]["quality"]["score"] > out[1]["quality"]["score"]


# --- API --------------------------------------------------------------------------------
def test_studio_endpoint_creates_drafts_with_mock(client):
    r = client.post("/api/studio/generate", headers=as_owner(),
                    json={"idea": "Free AI tools for college presentations", "media_type": "CAROUSEL",
                          "pillar": "tool_test", "variants": 2})
    assert r.status_code == 201
    body = r.json()
    assert body["provider"] == "mock" and len(body["drafts"]) == 2
    posts = client.get("/api/posts", headers=as_owner()).json()
    assert len(posts) == 2 and all(p["status"] == "draft" and p["is_mock"] for p in posts)


def test_studio_endpoint_rejects_bad_pillar(client):
    r = client.post("/api/studio/generate", headers=as_owner(),
                    json={"idea": "Free AI tools", "media_type": "IMAGE", "pillar": "nope"})
    assert r.status_code == 422


def test_studio_requires_owner(client):
    r = client.post("/api/studio/generate", json={"idea": "x" * 10, "media_type": "IMAGE", "pillar": "news"})
    assert r.status_code == 401


def test_azure_provider_requires_config(settings_env, monkeypatch):
    monkeypatch.setattr(settings_env, "text_provider", "azure_openai")
    with pytest.raises(providers.ProviderError):
        providers.get_text_provider(settings_env)


def test_quality_flags_devanagari():
    v = dict(GOOD_VARIANT, caption=GOOD_VARIANT["caption"] + " अलग-अलग")
    r = quality.evaluate(v, "CAROUSEL", False)
    assert any(c.name == "roman_script_only" and not c.passed for c in r.checks)
