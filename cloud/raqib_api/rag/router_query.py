"""Question → QueryPlan. Model first (strict JSON), deterministic EN/HI/AR parser as the fallback.

The model only normalises: it maps the question to an event kind, a target, an English time
phrase and a superlative. Turning the phrase into timestamps is deterministic here, so a model
that hallucinates a date cannot move the window.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ..llm import ProviderChain, get_provider, try_complete

KINDS = ("queue_over", "shelf_gap", "footfall", "checkout_served", "machine_stopped", "zone_breach", "ppe_violation")
TARGETS = ("events", "documents", "kpis", "any")
SUPERLATIVES = ("max", "min", None)

ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "enum": list(TARGETS)},
        "kind": {"type": ["string", "null"], "enum": [*KINDS, None]},
        "time_phrase": {"type": ["string", "null"], "description": "English, e.g. 'last friday evening', 'this week', 'yesterday', null"},
        "superlative": {"type": ["string", "null"], "enum": ["max", "min", None]},
        "till": {"type": ["integer", "null"]},
        "shelf": {"type": ["string", "null"]},
        "camera": {"type": ["string", "null"]},
        "keywords": {"type": "array", "items": {"type": "string"}, "maxItems": 6, "description": "English search terms"},
    },
    "required": ["target", "kind", "time_phrase", "superlative", "till", "shelf", "camera", "keywords"],
    "additionalProperties": False,
}

SYSTEM = (
    "You turn a store-operations question (English, Hindi or Arabic) into a JSON plan. "
    "kind: queue_over (queues, waiting), shelf_gap (empty shelves, restock), footfall (visitors, customers entering), "
    "checkout_served (checkout dwell, service time), machine_stopped, zone_breach, ppe_violation (helmets). "
    "target: documents when the question asks what an SOP, policy, manual or planogram says; kpis for footfall totals; "
    "events for incidents; any otherwise. time_phrase must be a short English phrase or null. Reply with JSON only.\n"
    "Examples: 'Which till had the longest queue last Friday evening?' -> {target: events, kind: queue_over, time_phrase: 'last friday evening', superlative: max}. "
    "'किस दिन सबसे ज़्यादा footfall था?' -> {target: kpis, kind: footfall, time_phrase: null, superlative: max}. "
    "'What does the SOP say about opening a third till?' -> {target: documents, kind: null, time_phrase: null, superlative: null}."
)


@dataclass
class QueryPlan:
    q: str
    lang: str = "en"
    mode: str = "hybrid"  # structured | semantic | hybrid
    target: str = "any"
    kind: str | None = None
    time_start: datetime | None = None
    time_end: datetime | None = None
    time_label: str | None = None
    superlative: str | None = None
    till: int | None = None
    shelf: str | None = None
    camera: str | None = None
    granularity: str | None = None  # day | hour, for KPI questions
    terms: list[str] = field(default_factory=list)
    source: str = "regex"  # model | regex
    legs: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("time_start", "time_end"):
            d[k] = d[k].isoformat() if d[k] else None
        return d


# ---- language ---------------------------------------------------------------------------

def detect_lang(text: str) -> str:
    if re.search(r"[ऀ-ॿ]", text):
        return "hi"
    if re.search(r"[؀-ۿ]", text):
        return "ar"
    return "en"


# ---- deterministic parser ---------------------------------------------------------------

KIND_WORDS: dict[str, tuple[str, ...]] = {
    "queue_over": ("queue", "queues", "waiting", "wait", "line", "कतार", "लाइन", "इंतज़ार", "इंतजार", "طابور", "انتظار", "صف"),
    "shelf_gap": ("shelf", "shelves", "gap", "gaps", "restock", "empty", "out of stock", "शेल्फ", "शेल्फ़", "गैप", "खाली", "الرف", "رفوف", "فجو", "فارغ"),
    "footfall": ("footfall", "visitors", "customers entered", "entered", "traffic", "busiest", "फुटफॉल", "ग्राहक", "आगंतुक", "زوار", "الزوار", "زائر", "عدد الزوار", "ازدحام", "دخل المتجر"),
    "checkout_served": ("checkout", "dwell", "service time", "served", "चेकआउट", "الدفع", "خدمة"),
    "machine_stopped": ("machine", "downtime", "stopped", "मशीन", "آلة", "توقف"),
    "zone_breach": ("breach", "exclusion", "restricted", "प्रतिबंधित", "منطقة محظورة", "اختراق"),
    "ppe_violation": ("helmet", "ppe", "vest", "हेलमेट", "خوذة", "سترة"),
}
DOC_WORDS = ("sop", "policy", "procedure", "manual", "planogram", "price list", "what does", "say about", "rule", "guideline",
             "retention", "kept", "privacy", "should", "when should", "दिशानिर्देश", "नीति", "प्रक्रिया", "कहता", "रखी जाती", "चाहिए",
             "دليل", "سياسة", "إجراء", "يقول", "الاحتفاظ", "يجب")
KPI_WORDS = ("footfall", "visitors", "customers", "busiest", "फुटफॉल", "ग्राहक", "आगंतुक", "زوار", "الزوار", "زائر")

# Deterministic HI/AR -> EN search hints so the BM25 leg over an English corpus works without a vector model.
# The multilingual embedder does the heavy lifting in production; this keeps CI and degraded mode honest.
TERM_HINTS: dict[str, str] = {
    "कतार": "queue", "लाइन": "queue", "इंतज़ार": "waiting", "टिल": "till", "शेल्फ़": "shelf", "शेल्फ": "shelf", "गैप": "gap", "खाली": "empty",
    "डेयरी": "dairy B3", "दूध": "dairy B3", "ब्रेड": "bread C2", "कन्फ़ेक्शनरी": "confectionery A1", "चॉकलेट": "confectionery A1",
    "फुटफॉल": "footfall", "ग्राहक": "customers footfall", "आगंतुक": "visitors footfall", "तीसरा": "third", "खोलने": "opening open",
    "खोलना": "opening open", "बंद": "closing close", "क्लिप": "clips clip", "रखी": "kept retention", "दिन": "days day", "मशीन": "machine",
    "हेलमेट": "helmet", "नीति": "policy", "दिशानिर्देश": "SOP procedure", "प्रक्रिया": "procedure SOP", "चेकआउट": "checkout",
    "طابور": "queue", "انتظار": "waiting queue", "صندوق": "till", "الدفع": "till checkout", "رف": "shelf", "الرف": "shelf", "رفوف": "shelves shelf",
    "فجوات": "gaps gap", "فجوة": "gap", "الألبان": "dairy B3", "ألبان": "dairy B3", "الخبز": "bread C2", "الحلويات": "confectionery A1",
    "زوار": "visitors footfall", "الزوار": "visitors footfall", "زائراً": "visitors footfall customers", "دخل": "entered",
    "ثالث": "third", "فتح": "opening open", "إغلاق": "closing close", "المقاطع": "clips clip", "الاحتفاظ": "kept retention",
    "يوماً": "days", "يوم": "day", "آلة": "machine", "خوذة": "helmet", "سياسة": "policy", "دليل": "SOP procedure", "الإجراءات": "SOP procedure",
}


def term_hints(q: str) -> list[str]:
    out: list[str] = []
    for w, en in TERM_HINTS.items():
        if w in q:
            out.extend(en.split())
    return out
MAX_WORDS = ("longest", "biggest", "highest", "most", "largest", "max", "peak", "busiest", "worst", "सबसे", "ज़्यादा", "ज्यादा", "लंबी", "अधिक",
             "أطول", "الأعلى", "أكبر", "أكثر", "الأكثر", "أسوأ")
DAY_WORDS = ("which day", "what day", "day had", "per day", "daily", "किस दिन", "कौन सा दिन", "أي يوم", "في أي يوم", "يومي")
HOUR_WORDS = ("which hour", "what hour", "hour had", "hourly", "peak hour", "किस घंटे", "कौन सा घंटा", "أي ساعة", "ساعة الذروة")
MIN_WORDS = ("shortest", "lowest", "least", "fewest", "quietest", "सबसे कम", "الأقل", "أقصر")

WEEKDAYS = {
    0: ("monday", "mon", "सोमवार", "الاثنين", "الإثنين"), 1: ("tuesday", "tue", "मंगलवार", "الثلاثاء"),
    2: ("wednesday", "wed", "बुधवार", "الأربعاء"), 3: ("thursday", "thu", "गुरुवार", "बृहस्पतिवार", "الخميس"),
    4: ("friday", "fri", "शुक्रवार", "الجمعة"), 5: ("saturday", "sat", "शनिवार", "السبت"), 6: ("sunday", "sun", "रविवार", "الأحد"),
}
PARTS = {
    "evening": ((17, 21), ("evening", "शाम", "مساء", "المساء")),
    "morning": ((8, 12), ("morning", "सुबह", "صباح", "الصباح")),
    "afternoon": ((12, 17), ("afternoon", "दोपहर", "ظهر", "بعد الظهر")),
    "night": ((21, 24), ("night", "रात", "ليل", "الليل")),
}
TODAY = ("today", "आज", "اليوم")
YESTERDAY = ("yesterday", "कल", "बीते कल", "أمس", "البارحة")
THIS_WEEK = ("this week", "इस हफ़्ते", "इस हफ्ते", "इस सप्ताह", "هذا الأسبوع")
LAST_WEEK = ("last week", "previous week", "पिछले हफ़्ते", "पिछले हफ्ते", "पिछले सप्ताह", "الأسبوع الماضي")
LAST = ("last", "previous", "पिछले", "पिछला", "बीते", "الماضي", "الماضية", "السابق")


def _day_bounds(d: datetime) -> tuple[datetime, datetime]:
    s = d.replace(hour=0, minute=0, second=0, microsecond=0)
    return s, s + timedelta(days=1)


def parse_time_phrase(text: str, now: datetime) -> tuple[datetime | None, datetime | None, str | None]:
    """Deterministic: relative phrases in EN/HI/AR, explicit ISO dates. Returns (start, end, label)."""
    t = text.lower()
    m = re.search(r"(20\d\d-\d\d-\d\d)", t)
    if m:
        d = datetime.fromisoformat(m.group(1)).replace(tzinfo=UTC)
        s, e = _day_bounds(d)
        return _narrow(s, e, t, m.group(1))
    if any(w in t for w in THIS_WEEK):
        return now - timedelta(days=7), now, "this week"
    if any(w in t for w in LAST_WEEK):
        return now - timedelta(days=14), now - timedelta(days=7), "last week"
    if any(w in t for w in TODAY):
        s, e = _day_bounds(now)
        return _narrow(s, min(e, now), t, "today")
    for wd, names in WEEKDAYS.items():
        if any(re.search(rf"(^|\W){re.escape(n)}(\W|$)", t) for n in names):
            back = (now.weekday() - wd) % 7 or 7
            s, e = _day_bounds(now - timedelta(days=back))
            return _narrow(s, e, t, f"last {names[0]}")
    if any(re.search(rf"(^|\W){re.escape(w)}(\W|$)", t) for w in YESTERDAY):
        s, e = _day_bounds(now - timedelta(days=1))
        return _narrow(s, e, t, "yesterday")
    for label, (hours, words) in PARTS.items():
        if any(w in t for w in words):
            s, e = _day_bounds(now)
            return s.replace(hour=hours[0]), min(now, s.replace(hour=hours[1]) if hours[1] < 24 else e), f"today {label}"
    return None, None, None


def _narrow(s: datetime, e: datetime, t: str, label: str) -> tuple[datetime, datetime, str]:
    for part, (hours, words) in PARTS.items():
        if any(w in t for w in words):
            day = s
            return day.replace(hour=hours[0]), (day.replace(hour=hours[1]) if hours[1] < 24 else e), f"{label} {part}"
    return s, e, label


def parse_regex(q: str, now: datetime) -> QueryPlan:
    t = q.lower()
    plan = QueryPlan(q=q, lang=detect_lang(q), source="regex")
    for kind, words in KIND_WORDS.items():
        if any(w in t for w in words):
            plan.kind = kind
            break
    if any(w in t for w in DOC_WORDS) and not (plan.kind and any(w in t for w in TODAY + YESTERDAY + THIS_WEEK + LAST_WEEK)):
        plan.target = "documents"
    elif plan.kind == "footfall" or any(w in t for w in KPI_WORDS):
        plan.target = "kpis"
        plan.kind = plan.kind or "footfall"
    elif plan.kind:
        plan.target = "events"
    if any(w in t for w in MIN_WORDS):
        plan.superlative = "min"
    elif any(w in t for w in MAX_WORDS):
        plan.superlative = "max"
    if any(w in t for w in DAY_WORDS):
        plan.granularity = "day"
    elif any(w in t for w in HOUR_WORDS):
        plan.granularity = "hour"
    m = re.search(r"(?:till|टिल|صندوق)\s*(?:no\.?|number|#)?\s*(\d{1,2})", t)
    if m:
        plan.till = int(m.group(1))
    m = re.search(r"\b([a-c]\d)\b", t)
    if m:
        plan.shelf = m.group(1).upper()
    m = re.search(r"\b(cam\d+)\b", t)
    if m:
        plan.camera = m.group(1)
    if plan.target != "documents":
        plan.time_start, plan.time_end, plan.time_label = parse_time_phrase(t, now)
    plan.terms = ([w for w in re.findall(r"\w+", t) if len(w) > 2] + term_hints(q))[:24]
    plan.mode = _mode(plan)
    return plan


def _mode(plan: QueryPlan) -> str:
    if plan.target == "documents":
        return "semantic"
    if plan.kind and (plan.time_start or plan.superlative or plan.till or plan.shelf):
        return "structured"
    return "hybrid"


def _shelf_id(v: Any) -> str | None:
    """Shelf ids look like A1 / B3 / C12; anything else (an aisle or product name) is not a filter."""
    if v in (None, ""):
        return None
    v = str(v).strip().upper()
    return v if re.fullmatch(r"[A-Z]\d{1,2}", v) else None


def _camera_id(v: Any) -> str | None:
    if v in (None, ""):
        return None
    v = str(v).strip().lower()
    return v if re.fullmatch(r"cam\d{1,3}", v) else None


# ---- model route --------------------------------------------------------------------------

def route_query(q: str, now: datetime | None = None, provider: ProviderChain | None = None) -> QueryPlan:
    now = now or datetime.now(UTC)
    fallback = parse_regex(q, now)
    provider = provider if provider is not None else get_provider("route")
    res = try_complete(provider, SYSTEM, f"Question: {q}", json_schema=ROUTE_SCHEMA, max_tokens=250)
    if res is None or res.parsed is None:
        return fallback
    p = res.parsed
    # The deterministic parser wins wherever it found a signal; the model only fills gaps. A model that
    # calls everything a "document question" or forgets the time phrase cannot move the window.
    ql = q.lower()

    def literal(v: Any) -> Any:  # a model may only name a till/shelf/camera that the question itself names
        return v if v not in (None, "") and str(v).lower() in ql else None

    plan = QueryPlan(q=q, lang=fallback.lang, source="model", kind=fallback.kind or p.get("kind"),
                     superlative=fallback.superlative or p.get("superlative"), till=fallback.till or literal(p.get("till")),
                     shelf=fallback.shelf or _shelf_id(literal(p.get("shelf"))),
                     camera=fallback.camera or _camera_id(literal(p.get("camera"))),
                     granularity=fallback.granularity, terms=[*fallback.terms, *(p.get("keywords") or [])][:12])
    if p.get("shelf") and not _shelf_id(p.get("shelf")):
        plan.terms.append(str(p["shelf"]).lower())  # a product or aisle name: let BM25 find "shelf B3 (dairy)"
    plan.target = fallback.target if fallback.target != "any" else (p.get("target") or "any")
    if plan.kind == "footfall" and plan.target == "events":
        plan.target = "kpis"
    if plan.target == "documents" and plan.kind and fallback.target != "documents":
        plan.target = "events" if plan.kind != "footfall" else "kpis"
    if plan.target != "documents":
        plan.time_start, plan.time_end, plan.time_label = fallback.time_start, fallback.time_end, fallback.time_label
        if plan.time_start is None and p.get("time_phrase"):
            plan.time_start, plan.time_end, plan.time_label = parse_time_phrase(str(p["time_phrase"]), now)
    plan.mode = _mode(plan)
    return plan
