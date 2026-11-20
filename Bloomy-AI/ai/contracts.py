"""Public, JSON-compatible RAG request and response contracts."""
from dataclasses import asdict, dataclass, field
from datetime import date


@dataclass(frozen=True)
class RecommendationRequest:
    age: int
    base_level: int
    start_date: str
    goal: str = "듣기"
    session_minutes: int = 10
    owned_materials: tuple[str, ...] = ()
    favorite_topics: tuple[str, ...] = ()
    top_k: int = 8
    exposure_months: int | None = None
    exposure: str | None = None

    def __post_init__(self):
        for name, low, high in (("age", 4, 7), ("base_level", 1, 5), ("top_k", 1, 100)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer in {low}..{high}")
        if type(self.session_minutes) is not int or self.session_minutes not in (10, 15, 20):
            raise ValueError("session_minutes must be 10, 15, or 20")
        if not isinstance(self.start_date, str) or date.fromisoformat(self.start_date).isoformat() != self.start_date:
            raise ValueError("start_date must be YYYY-MM-DD")
        if not isinstance(self.goal, str) or not self.goal.strip():
            raise ValueError("goal must be a nonempty string")
        if self.exposure_months is not None and (
                type(self.exposure_months) is not int or self.exposure_months < 0):
            raise ValueError("exposure_months must be a nonnegative integer")
        if self.exposure is not None and self.exposure not in ("none", "some", "much"):
            raise ValueError("exposure must be none, some, or much")
        for name in ("owned_materials", "favorite_topics"):
            values = getattr(self, name)
            if not isinstance(values, (list, tuple)) or any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValueError(f"{name} must contain nonempty strings")


@dataclass
class RecommendationResult:
    days: list[dict]
    explanation: str
    base_level: int
    evidence: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: str = "draft"
    engine_version: str = "bloomy-rag-local-v1"
    memory_context: dict = field(default_factory=dict)
    day_details: list[dict] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    def to_backend_payload(self):
        """Payload for POST /api/children/{id}/plans; caller handles approval."""
        fields = ("date", "content_id", "task", "minutes", "check_point")
        return {"days": [{key: day[key] for key in fields} for day in self.days], "explanation": self.explanation, "base_level": self.base_level}
