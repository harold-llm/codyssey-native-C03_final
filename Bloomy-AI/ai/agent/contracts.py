"""Validated coach contracts. Dates and identity are supplied by the caller."""
from dataclasses import asdict, dataclass, field
from datetime import date


def iso_date(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("date must be YYYY-MM-DD")
    return date.fromisoformat(value)


def child_identity(value):
    if type(value) is not int or value < 1:
        raise ValueError("child_id must be a positive integer")


@dataclass(frozen=True)
class Feedback:
    child_id: int
    date: str
    completion: str | None = None
    satisfaction: int | None = None
    interest: int | None = None
    comprehension: int | None = None
    memo: str = ""
    rest_day: bool = False

    def __post_init__(self):
        child_identity(self.child_id)
        iso_date(self.date)
        if type(self.rest_day) is not bool:
            raise ValueError("rest_day must be boolean")
        if self.rest_day:
            return  # Scores and memo are deliberately ignored for rest days.
        if self.completion not in ("full", "partial", "none"):
            raise ValueError("invalid completion")
        for name in ("satisfaction", "interest", "comprehension"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 5:
                raise ValueError(f"{name} must be an integer in 1..5")
        if not isinstance(self.memo, str) or len(self.memo) > 500:
            raise ValueError("memo must be a string of at most 500 characters")


@dataclass(frozen=True)
class LearningCard:
    child_id: int
    date: str
    content_id: str
    task: str
    minutes: int
    check_point: str

    def __post_init__(self):
        child_identity(self.child_id)
        iso_date(self.date)
        for name in ("content_id", "task", "check_point"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a nonempty string")
        if type(self.minutes) is not int or not 5 <= self.minutes <= 20:
            raise ValueError("card minutes must be an integer in 5..20")


@dataclass(frozen=True)
class CoachRequest:
    child_id: int
    age: int
    base_level: int
    feedback: Feedback
    today_card: LearningCard | None = None
    next_card: LearningCard | None = None
    history: tuple[Feedback, ...] = ()
    plan_status: str = "draft"
    session_minutes: int = 10
    goal: str = "듣기"
    owned_materials: tuple[str, ...] = ()
    favorite_topics: tuple[str, ...] = ()

    def __post_init__(self):
        from ai.contracts import RecommendationRequest
        child_identity(self.child_id)
        if not isinstance(self.feedback, Feedback):
            raise ValueError("feedback must be Feedback")
        RecommendationRequest(self.age, self.base_level, self.feedback.date, self.goal,
                              self.session_minutes, self.owned_materials, self.favorite_topics)
        if self.plan_status not in ("draft", "approved", "done", "superseded"):
            raise ValueError("invalid plan_status")
        if not isinstance(self.history, (list, tuple)) or any(not isinstance(r, Feedback) for r in self.history):
            raise ValueError("history must contain Feedback objects")
        records = [self.feedback, *self.history]
        if any(r.child_id != self.child_id for r in records):
            raise ValueError("feedback must belong to the same child")
        if len({r.date for r in records}) != len(records):
            raise ValueError("duplicate feedback date")
        if any(r.date >= self.feedback.date for r in self.history):
            raise ValueError("history must precede feedback date")
        for card in (self.today_card, self.next_card):
            if card is not None:
                if not isinstance(card, LearningCard) or card.child_id != self.child_id:
                    raise ValueError("cards must belong to the same child")
                if card.minutes > self.session_minutes:
                    raise ValueError("card exceeds session limit")
        if self.today_card and self.today_card.date != self.feedback.date:
            raise ValueError("today card date must equal feedback date")
        if self.next_card and self.next_card.date <= self.feedback.date:
            raise ValueError("next card must be after feedback date")


@dataclass
class CoachResult:
    case: str
    memo_intent: str
    intent_reason: str
    flags: dict
    reasons: list[str]
    message: str | None
    adjust: dict
    tomorrow: dict | None
    evidence: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence_sentence: str = ""
    is_ai_generated: bool = True
    model: str = "local-rules"
    prompt_version: str = "bloomy-coach-local-v1"
    intent_version: str = "bloomy-intent-keywords-v1"
    low_interest_streak: int = 0
    memory_context: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)
