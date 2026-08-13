from __future__ import annotations

from datetime import date
from os import getenv
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, HttpUrl


class Talk(BaseModel):
    title: str = ""
    speaker: str = ""
    image: str | HttpUrl | None = None
    images: list[str | HttpUrl] = Field(default_factory=list)
    cutout: str | None = None
    social: str | HttpUrl | None = None


class Sponsor(BaseModel):
    name: str = ""
    logo: str | None = None
    tier: str = ""


class Event(BaseModel):
    id: int
    title: str = ""
    date: str | date | None = None
    time: str = Field(default="", validation_alias=AliasChoices("time", "doors_open"))
    venue: str = ""
    address: str = ""
    host: str = ""
    event_link: str | HttpUrl | None = None
    registrations: str | int | None = None
    participants: str | int | None = None
    sponsor_logo: str | None = None
    sponsors: list[Sponsor] = Field(default_factory=list)
    talks: list[Talk] = Field(default_factory=list)


class Box(BaseModel):
    x: int
    y: int
    w: int
    h: int


class TemplateDefaults(BaseModel):
    font: str | None = None
    color: str = "#FFFFFF"
    size: int = 28


class BaseElement(BaseModel):
    id: str
    box: Box
    type: str


class TextElement(BaseElement):
    type: Literal["text"] = "text"
    value: str
    font: str | None = None
    color: str | None = None
    size: int | None = None
    align: Literal["left", "center", "right"] = "left"
    valign: Literal["top", "middle", "bottom"] = "top"
    wrap: bool = False
    fit: Literal["none", "shrink"] = "none"
    line_spacing: float = 1.15


class ImageElement(BaseElement):
    type: Literal["image"] = "image"
    source: str
    fit: Literal["cover", "contain", "contain-bottom", "fill"] = "cover"
    shape: Literal["rect", "rounded", "circle", "parallelogram", "parallelogram-pair"] = "rect"
    corner_radius: int = 24


class RectangleElement(BaseElement):
    type: Literal["rectangle"] = "rectangle"
    color: str = "#000000"


TemplateElement = Annotated[
    TextElement | ImageElement | RectangleElement, Field(discriminator="type")
]


class CanvasSize(BaseModel):
    width: int
    height: int


class Template(BaseModel):
    name: str
    background: str
    size: CanvasSize | None = None
    defaults: TemplateDefaults = Field(default_factory=TemplateDefaults)
    elements: list[TemplateElement]


class RenderRequest(BaseModel):
    template_path: str
    output_dir: str = "artifacts"
    events_file: str = "_data/events.yml"
    event_id: int | None = None
    width: int | None = None
    output_format: Literal["jpg", "png"] = "jpg"


class AzureOpenAISettings(BaseModel):
    endpoint: str
    api_key: str
    deployment: str
    api_version: str = "2024-06-01"
    temperature: float = 0.7
    max_tokens: int = 900

    @classmethod
    def from_env(cls) -> AzureOpenAISettings | None:
        endpoint = getenv("AZURE_OPENAI_ENDPOINT", "").strip()
        api_key = getenv("AZURE_OPENAI_API_KEY", "").strip()
        deployment = getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()

        if not endpoint or not api_key or not deployment:
            return None

        return cls(
            endpoint=endpoint,
            api_key=api_key,
            deployment=deployment,
            api_version=getenv("AZURE_OPENAI_API_VERSION", "2024-06-01").strip() or "2024-06-01",
            temperature=float(getenv("IMAGEGEN_LLM_TEMPERATURE", "0.7")),
            max_tokens=int(getenv("IMAGEGEN_LLM_MAX_TOKENS", "900")),
        )


class CTAVariants(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    register_cta: str = Field(validation_alias="register", serialization_alias="register")
    attend: str
    recap: str


class PostVariants(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    announce: str
    reminder: str
    recap: str
    thank_you: str = Field(
        validation_alias=AliasChoices("thank_you", "thank-you"),
        serialization_alias="thank-you",
    )


class MeetupPostDraft(BaseModel):
    post: str
    cta_variants: CTAVariants
    variants: PostVariants | None = None
    short_form: str = ""


class TalkPostDraft(BaseModel):
    talk_index: int
    title: str
    speaker: str
    post: str
    cta_variants: CTAVariants
    short_form: str = ""


class SocialContentBundle(BaseModel):
    platform: Literal["linkedin"] = "linkedin"
    tone: str = "professional and friendly"
    generated_with: Literal["azure-openai", "rules"] = "rules"
    meetup: MeetupPostDraft
    talks: list[TalkPostDraft] = Field(default_factory=list)


class ImageBundle(BaseModel):
    meetup_image: str | None = None
    meetup_diamond_image: str | None = None
    speaker_images: list[str] = Field(default_factory=list)


class SlideDeck(BaseModel):
    event_id: int
    slides: list[str] = Field(default_factory=list)
    pdf: str | None = None


class GoogleSlideDeck(BaseModel):
    event_id: int
    presentation_id: str
    name: str
    url: str
    embed_url: str = ""


class AnimationClip(BaseModel):
    name: str
    mp4: str | None = None
    gif: str | None = None


class AnimationBundle(BaseModel):
    preset: str
    clips: list[AnimationClip] = Field(default_factory=list)


class GeneratedBundle(BaseModel):
    event_id: int
    output_dir: str
    images: ImageBundle
    social: SocialContentBundle | None = None
    slides: SlideDeck | None = None
    animations: list[AnimationBundle] = Field(default_factory=list)


ContextDict = dict[str, Any]
