"""Content Studio: turns an idea into scored post variants and saves them as drafts.

Flow: build brief -> reserve worst-case cost against the monthly cap -> call provider ->
replace the estimate with the actual cost -> run the quality checklist -> save drafts, best first.
Nothing here publishes or requests approval; you choose which draft to submit.
"""
import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import MediaType, Post, PostStatus
from ..services import audit, budget
from ..services.policy import SYSTEM_ACTOR
from . import quality
from .brand import PILLARS, VOICE
from .providers import TextProvider

FORMAT_GUIDE = {
    "IMAGE": "A single educational image post: one strong hook (also the on-image headline) and a caption.",
    "CAROUSEL": "A 5-8 slide carousel. Slide 1 is the hook, the last slide is the call to action. Max 30 words per slide.",
    "REELS": "A 15-30 second faceless Reel: screen recording + text on screen + AI voiceover. Scene-by-scene script; the hook lands in seconds 0-2.",
}

SCHEMA_HINT = {
    "variants": [{
        "hook": "string, max 12 words",
        "caption": "string, 150-1200 characters, ends with the call to action",
        "cta": "string",
        "hashtags": ["#Tag", "3-8 items"],
        "alt_text": "string describing the image for screen readers",
        "slides": [{"title": "string", "body": "string, max 30 words"}],
        "script": [{"seconds": "0-2", "visual": "string", "voiceover": "string", "on_screen_text": "string"}],
    }]
}


class GenerationError(Exception):
    pass


@dataclass
class Pricing:
    in_inr_per_m: float
    out_inr_per_m: float

    def cost(self, tokens_in: int, tokens_out: int) -> float:
        return round(tokens_in / 1e6 * self.in_inr_per_m + tokens_out / 1e6 * self.out_inr_per_m, 4)


def build_brief(idea: str, media_type: str, pillar: str, variants: int, has_affiliate_link: bool,
                test_notes: str | None) -> tuple[str, str]:
    system = (VOICE + "\n\nReturn ONLY a JSON object matching this shape (omit 'slides' unless CAROUSEL, "
              "omit 'script' unless REELS):\n" + json.dumps(SCHEMA_HINT))
    user = json.dumps({
        "idea": idea, "format": media_type, "format_guide": FORMAT_GUIDE[media_type],
        "pillar": PILLARS[pillar], "variants": variants, "has_affiliate_link": has_affiliate_link,
        "test_notes": test_notes or "none: do not claim any result",
        "instruction": f"Write {variants} clearly different variants (different hooks and angles).",
    }, ensure_ascii=False)
    return system, user


def generate(db: Session, provider: TextProvider, *, idea: str, media_type: str, pillar: str, variants: int = 3,
             has_affiliate_link: bool = False, test_notes: str | None = None, pricing: Pricing,
             monthly_cap_inr: float, max_output_tokens: int, actor: str) -> list[dict]:
    if media_type not in FORMAT_GUIDE:
        raise GenerationError(f"unsupported format {media_type}")
    if pillar not in PILLARS:
        raise GenerationError(f"unknown pillar {pillar}")
    if not 1 <= variants <= 4:
        raise GenerationError("variants must be 1-4")
    idea = idea.strip()
    if not 5 <= len(idea) <= 500:
        raise GenerationError("idea must be 5-500 characters")

    system, user = build_brief(idea, media_type, pillar, variants, has_affiliate_link, test_notes)
    worst_case = 0.0 if provider.name == "mock" else pricing.cost(len(system + user), max_output_tokens)
    spend = budget.reserve(db, "text_ai", worst_case, monthly_cap_inr, actor, note=f"{provider.name} generate (estimate)")

    try:
        result = provider.generate_json(system, user, max_output_tokens)
    except Exception:
        db.delete(spend)  # nothing was billed for a failed request we can't measure; keep the cap honest
        audit.record(db, actor, "generation_failed", None, provider=provider.name, format=media_type)
        raise

    actual = 0.0 if result.is_mock else pricing.cost(result.input_tokens, result.output_tokens)
    spend.amount_inr, spend.note = actual, f"{result.model}: {result.input_tokens} in / {result.output_tokens} out tokens"

    raw = result.data.get("variants")
    if not isinstance(raw, list) or not raw:
        raise GenerationError("provider returned no variants")

    out = []
    for v in raw[:variants]:
        if not isinstance(v, dict):
            continue
        report = quality.evaluate(v, media_type, has_affiliate_link)
        tags = " ".join(v.get("hashtags") or [])
        post = Post(media_type=MediaType(media_type), caption=f"{(v.get('caption') or '').strip()}\n\n{tags}".strip(),
                    pillar=pillar, has_affiliate_link=has_affiliate_link, ai_generated=True,
                    status=PostStatus.draft, content=v, quality=report.as_dict(),
                    generated_by=("MOCK" if result.is_mock else result.model))
        db.add(post)
        db.flush()
        out.append({"post_id": post.id, "variant": v, "quality": report.as_dict(), "is_mock": result.is_mock})
    out.sort(key=lambda x: (x["quality"]["blocked"], -x["quality"]["score"]))
    audit.record(db, actor if actor else SYSTEM_ACTOR, "content_generated", None, provider=provider.name,
                 format=media_type, pillar=pillar, drafts=[o["post_id"] for o in out], cost_inr=actual)
    return out
