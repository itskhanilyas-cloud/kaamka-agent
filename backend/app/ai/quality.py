"""Quality checklist applied to every generated variant before you see it.

Each check returns pass/fail and a reason. The score is the share of checks passed (0-100);
any 'blocking' failure means the variant cannot be saved as a draft without editing.
"""
from dataclasses import dataclass, field

from .brand import BANNED_PHRASES


@dataclass
class Check:
    name: str
    passed: bool
    reason: str = ""
    blocking: bool = False


@dataclass
class QualityReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def score(self) -> int:
        return round(100 * sum(c.passed for c in self.checks) / len(self.checks)) if self.checks else 0

    @property
    def blocked(self) -> bool:
        return any(c.blocking and not c.passed for c in self.checks)

    def as_dict(self) -> dict:
        return {"score": self.score, "blocked": self.blocked,
                "checks": [{"name": c.name, "passed": c.passed, "reason": c.reason, "blocking": c.blocking} for c in self.checks]}


def evaluate(variant: dict, media_type: str, has_affiliate_link: bool) -> QualityReport:
    r = QualityReport()
    hook = (variant.get("hook") or "").strip()
    caption = (variant.get("caption") or "").strip()
    tags = variant.get("hashtags") or []
    text_all = " ".join([hook, caption, " ".join(str(s) for s in variant.get("slides", []))]).lower()

    r.checks.append(Check("hook_present", bool(hook), "hook is empty", blocking=True))
    r.checks.append(Check("hook_short", 0 < len(hook.split()) <= 12, f"hook is {len(hook.split())} words; keep it to 12 or fewer"))
    r.checks.append(Check("caption_length", 80 <= len(caption) <= 2200, f"caption is {len(caption)} characters (80-2,200)", blocking=len(caption) > 2200))
    r.checks.append(Check("cta_present", bool((variant.get("cta") or "").strip()), "no call to action"))
    r.checks.append(Check("hashtag_count", 3 <= len(tags) <= 8, f"{len(tags)} hashtags; use 3-8"))
    r.checks.append(Check("hashtags_wellformed", all(isinstance(t, str) and t.startswith("#") and " " not in t for t in tags),
                          "every hashtag must start with # and have no spaces"))
    non_latin = any("\u0900" <= ch <= "\u097F" for ch in text_all)  # Devanagari
    r.checks.append(Check("roman_script_only", not non_latin, "write Hinglish in Roman letters (found Devanagari)"))
    banned = [p for p in BANNED_PHRASES if p in text_all]
    r.checks.append(Check("no_overclaiming", not banned, f"remove: {', '.join(banned)}", blocking=True))
    if has_affiliate_link:
        r.checks.append(Check("affiliate_disclosure", caption[:150].lower().startswith(("#affiliate", "#ad")),
                              "affiliate caption must start with #Affiliate or #Ad", blocking=True))
    if media_type == "CAROUSEL":
        slides = variant.get("slides") or []
        r.checks.append(Check("carousel_slide_count", 3 <= len(slides) <= 10, f"{len(slides)} slides; use 3-10", blocking=not slides))
        long = [i + 1 for i, s in enumerate(slides) if len(str(s.get("body", "")).split()) > 30]
        r.checks.append(Check("carousel_slides_readable", not long, f"slides {long} have more than 30 words"))
    if media_type == "REELS":
        script = variant.get("script") or []
        r.checks.append(Check("reel_script_present", bool(script), "no scene-by-scene script", blocking=True))
        first = script[0] if script else {}
        r.checks.append(Check("reel_opens_fast", str(first.get("seconds", "")).startswith(("0-1", "0-2", "0-3")),
                              "first scene must land the hook in the first 1-3 seconds"))
    r.checks.append(Check("alt_text_present", bool((variant.get("alt_text") or "").strip()) or media_type == "REELS",
                          "add alt text for accessibility"))
    return r
