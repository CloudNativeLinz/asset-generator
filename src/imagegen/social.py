from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime

from .config import (
    AzureOpenAISettings,
    CTAVariants,
    Event,
    MeetupPostDraft,
    PostVariants,
    SocialContentBundle,
    TalkPostDraft,
)
from .llm import LLMError, azure_chat_completion

SHORT_FORM_LIMIT = 280


def _date_text(value: str | date | None) -> str:
    if isinstance(value, date):
        return value.strftime("%d %b %Y")

    text = str(value or "").strip()
    if not text:
        return "upcoming date"

    for candidate in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(text, candidate).replace(tzinfo=UTC)
            return parsed.strftime("%d %b %Y")
        except ValueError:
            continue

    return text


def _extract_json(text: str) -> dict:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?", "", candidate).strip()
        candidate = re.sub(r"```$", "", candidate).strip()

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("No JSON object found in model response")

    return json.loads(candidate[start : end + 1])


def _default_cta() -> CTAVariants:
    return CTAVariants(
        register_cta="Reserve your spot today.",
        attend="Join us at the meetup and bring your questions.",
        recap="Follow for recap highlights after the event.",
    )


def _apply_cta_defaults(
    bundle: SocialContentBundle, cta_defaults: CTAVariants | None
) -> SocialContentBundle:
    if cta_defaults is None:
        return bundle

    meetup = bundle.meetup.model_copy(update={"cta_variants": cta_defaults})
    talks = [talk.model_copy(update={"cta_variants": cta_defaults}) for talk in bundle.talks]

    return bundle.model_copy(update={"meetup": meetup, "talks": talks})


def _hashtags(event: Event) -> str:
    host = str(event.host or "Cloud Native Linz").replace(" ", "")
    return f"#CloudNativeLinz #Meetup #{host}"


def _short_hashtags(event: Event) -> str:
    host = str(event.host or "Cloud Native Linz").replace(" ", "")
    return f"#CloudNativeLinz #{host}"


def _short_form(post: str, event: Event) -> str:
    tags = _short_hashtags(event)
    body = re.sub(r"#\S+", "", post)
    body = re.sub(r"\s+", " ", body).strip()

    budget = SHORT_FORM_LIMIT - len(tags) - 1
    if len(body) > budget:
        truncated = body[:budget]
        sentence_cut = max(
            truncated.rfind(". "),
            truncated.rfind("! "),
            truncated.rfind("? "),
        )
        if sentence_cut > budget * 0.5:
            body = truncated[: sentence_cut + 1].strip()
        else:
            space = truncated.rfind(" ")
            clipped = truncated[:space] if space > 0 else truncated
            body = clipped.rstrip(",;:- ") + "\u2026"

    return f"{body} {tags}".strip()


def _meetup_variants(event: Event, announce: str) -> PostVariants:
    dt = _date_text(event.date)
    title = (event.title or "our next meetup").strip()
    tags = _hashtags(event)

    reminder = (
        f"Reminder: {title} is happening on {dt}. "
        f"There is still time to join us for the talks, networking, and good conversations. {tags}"
    )
    recap = (
        f"That's a wrap on {title} ({dt})! "
        f"Thank you to everyone who joined, asked questions, and shared ideas. "
        f"Recap highlights and photos are on the way. {tags}"
    )
    thank_you = (
        f"A big thank you to our speakers, sponsors, and the community for making {title} on {dt} "
        f"a great evening. We could not do it without you. See you at the next one! {tags}"
    )

    return PostVariants(announce=announce, reminder=reminder, recap=recap, thank_you=thank_you)


def _rules_meetup_post(event: Event) -> MeetupPostDraft:
    dt = _date_text(event.date)
    title = (event.title or "Next meetup edition").strip()
    talk_count = len(event.talks)
    talks_bit = ""
    if talk_count > 0:
        talks_bit = f" We are featuring {talk_count} talk{'s' if talk_count != 1 else ''} from the community."

    post = (
        f"Join us for our next meetup on {dt}: {title}."
        f"{talks_bit} Expect practical insights, great conversations, and a welcoming community."
        f" {_hashtags(event)}"
    )

    return MeetupPostDraft(
        post=post,
        cta_variants=_default_cta(),
        variants=_meetup_variants(event, post),
        short_form=_short_form(post, event),
    )


def _rules_talk_post(event: Event, talk_index: int) -> TalkPostDraft:
    talk = event.talks[talk_index]
    dt = _date_text(event.date)
    title = (talk.title or "Community lightning talk").strip()
    speaker = (talk.speaker or "Guest speaker").strip()

    post = (
        f'Speaker spotlight for {dt}: {speaker} will present "{title}" at our meetup. '
        f"If this topic is on your radar, this is a great session to attend. {_hashtags(event)}"
    )

    return TalkPostDraft(
        talk_index=talk_index,
        title=talk.title or "",
        speaker=talk.speaker or "",
        post=post,
        cta_variants=_default_cta(),
        short_form=_short_form(post, event),
    )


def _build_prompt(event: Event) -> tuple[str, str]:
    dt = _date_text(event.date)
    talks = [
        {
            "talk_index": index,
            "title": talk.title or "",
            "speaker": talk.speaker or "",
        }
        for index, talk in enumerate(event.talks)
    ]

    system_prompt = (
        "You write LinkedIn copy for meetup promotions. "
        "Tone is professional and friendly. "
        "Always return valid JSON only, no markdown."
    )
    user_prompt = json.dumps(
        {
            "task": "Generate one meetup announcement post and one post per talk with CTA variants.",
            "requirements": {
                "platform": "linkedin",
                "tone": "professional and friendly",
                "include_date_in_meetup_post": True,
                "cta_variants": ["register", "attend", "recap"],
                "max_length_per_post": 650,
            },
            "event": {
                "title": event.title or "",
                "date": dt,
                "host": event.host or "",
                "talks": talks,
            },
            "output_schema": {
                "meetup": {
                    "post": "string",
                    "cta_variants": {
                        "register": "string",
                        "attend": "string",
                        "recap": "string",
                    },
                },
                "talks": [
                    {
                        "talk_index": 0,
                        "title": "string",
                        "speaker": "string",
                        "post": "string",
                        "cta_variants": {
                            "register": "string",
                            "attend": "string",
                            "recap": "string",
                        },
                    }
                ],
            },
        },
        ensure_ascii=False,
    )
    return system_prompt, user_prompt


def _rules_bundle(event: Event) -> SocialContentBundle:
    talks = [_rules_talk_post(event, index) for index in range(len(event.talks))]
    return SocialContentBundle(meetup=_rules_meetup_post(event), talks=talks)


def _llm_bundle(event: Event, settings: AzureOpenAISettings) -> SocialContentBundle:
    system_prompt, user_prompt = _build_prompt(event)
    response = azure_chat_completion(settings, system_prompt=system_prompt, user_prompt=user_prompt)
    payload = _extract_json(response)

    model = SocialContentBundle.model_validate(
        {
            "platform": "linkedin",
            "tone": "professional and friendly",
            "generated_with": "azure-openai",
            "meetup": payload["meetup"],
            "talks": payload.get("talks", []),
        }
    )

    return model


def _ensure_derived(bundle: SocialContentBundle, event: Event) -> SocialContentBundle:
    meetup = bundle.meetup
    meetup_updates: dict = {}
    if meetup.variants is None:
        meetup_updates["variants"] = _meetup_variants(event, meetup.post)
    if not meetup.short_form:
        meetup_updates["short_form"] = _short_form(meetup.post, event)
    if meetup_updates:
        meetup = meetup.model_copy(update=meetup_updates)

    talks = [
        (
            talk
            if talk.short_form
            else talk.model_copy(update={"short_form": _short_form(talk.post, event)})
        )
        for talk in bundle.talks
    ]

    return bundle.model_copy(update={"meetup": meetup, "talks": talks})


def generate_social_bundle(
    event: Event,
    *,
    prefer_azure: bool = True,
    cta_defaults: CTAVariants | None = None,
) -> SocialContentBundle:
    settings = AzureOpenAISettings.from_env()

    if prefer_azure and settings is not None:
        try:
            bundle = _apply_cta_defaults(_llm_bundle(event, settings), cta_defaults)
            return _ensure_derived(bundle, event)
        except (LLMError, KeyError, ValueError, TypeError, json.JSONDecodeError):
            pass

    return _ensure_derived(_apply_cta_defaults(_rules_bundle(event), cta_defaults), event)
