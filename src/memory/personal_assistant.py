"""
Enhanced Memory Extraction & Management for Personal Assistant Behavior
========================================================================

Provides intelligent memory extraction, topic identification,
and interest tracking with natural time decay.

Features:
- Automatic conversation summarization
- Topic and interest extraction with TIME DECAY
- Dynamic "current focus" detection from recent activity
- Cross-conversation memory enrichment
"""

import asyncio
import logging
import math
import re
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

from sqlalchemy import delete, select

from src.config.audit_log import audit_debug, audit_info
from src.config.config_loader import config
from src.memory.db_models import Conversation, Interest, Topic
from src.models.db import AsyncSessionLocal

# Decay constants (sourced from centralized config)
TOPIC_HALF_LIFE_DAYS = int(config.get("memory.decay.topic_half_life_days", 14))
INTEREST_HALF_LIFE_DAYS = int(config.get("memory.decay.interest_half_life_days", 21))
FOCUS_WINDOW_DAYS = int(config.get("memory.decay.focus_window_days", 3))
RELEVANCE_FLOOR = float(config.get("memory.decay.relevance_floor", 0.05))


# ── Helpers ──────────────────────────────────────────────────────────────────


def _time_decay(last_active_iso: str, half_life_days: float) -> float:
    """Exponential decay based on time since last activity. Returns 0.0–1.0."""
    try:
        last_active = datetime.fromisoformat(last_active_iso)
    except (ValueError, TypeError):
        return RELEVANCE_FLOOR
    # Handle both naive and aware datetimes
    now = datetime.now(tz=last_active.tzinfo)
    age_days = max((now - last_active).total_seconds() / 86400, 0)
    return max(0.5 ** (age_days / half_life_days), RELEVANCE_FLOOR)


# ── Topic & Interest Extraction ─────────────────────────────────────────────


class TopicExtractor:
    """Extract topics and interests from conversations."""

    TOPIC_PATTERNS = {
        "programming_languages": [
            r"\b(python|javascript|typescript|java|cpp|c\+\+|go|rust|ruby|php|swift|kotlin)\b",
            r"\b(js|ts|c#|csharp|perl|haskell|scala|elixir)\b",
        ],
        "frameworks": [
            r"\b(django|flask|fastapi|react|vue|angular|spring|spring-boot)\b",
            r"\b(next\.js|nuxt|express|rails|laravel|phoenix|actix)\b",
        ],
        "databases": [
            r"\b(postgres|postgresql|mysql|mongodb|redis|cassandra|dynamodb)\b",
            r"\b(elasticsearch|sqlite|mariadb|oracle|sql\s*server|cockroachdb)\b",
        ],
        "cloud_platforms": [
            r"\b(aws|azure|gcp|google\s*cloud|heroku|digitalocean)\b",
            r"\b(cloud|kubernetes|docker|container)\b",
        ],
        "devops_infra": [
            r"\b(kubernetes|k8s|docker|podman|terraform|ansible|jenkins|gitlab)\b",
            r"\b(ci\/cd|devops|infrastructure|deployment|container)\b",
        ],
        "ai_ml": [
            r"\b(llm|machine\s*learning|deep\s*learning|neural|transformers)\b",
            r"\b(tensorflow|pytorch|keras|huggingface|langchain|rag)\b",
        ],
        "frontend": [
            r"\b(html|css|responsive|ui|ux|design|accessibility|a11y)\b",
            r"\b(react|vue|angular|web\s*components)\b",
        ],
        "backend": [
            r"\b(backend|api|rest|graphql|microservices|scaling|performance)\b",
            r"\b(database|cache|async|concurrency)\b",
        ],
        "data": [
            r"\b(data|analytics|pipeline|etl|warehouse|lake)\b",
            r"\b(tableau|looker|jupyter)\b",
        ],
        "security": [
            r"\b(security|encryption|authentication|oauth|jwt|authorization)\b",
            r"\b(ssl|tls|https|penetration|vulnerability)\b",
        ],
    }

    INTEREST_PATTERNS = {
        "learning": r"\b(learning|studying|course|tutorial|guide|documentation)\b",
        "debugging": r"\b(debug|troubleshoot|issue|error|bug|fix|problem|not working)\b",
        "optimization": r"\b(optimi[zs]e|performance|speed|efficient|fast|slow)\b",
        "architecture": r"\b(architect|design|pattern|scalable|scale|modular)\b",
        "testing": r"\b(test|unit\s*test|integration|test-driven|tdd|pytest|jest)\b",
        "documentation": r"\b(document|readme|docstring|comment|explain)\b",
        "refactoring": r"\b(refactor|clean|improve|code\s*quality|simplify)\b",
        "deployment": r"\b(deploy|production|staging|release|ci\/cd|automation)\b",
    }

    @staticmethod
    def extract_topics(text: str) -> dict[str, list[str]]:
        topics: dict[str, list[str]] = {}
        text_lower = text.lower()
        for category, patterns in TopicExtractor.TOPIC_PATTERNS.items():
            matches: set[str] = set()
            for pattern in patterns:
                found = re.findall(pattern, text_lower, re.IGNORECASE)
                matches.update(m.lower() for m in found if m)
            if matches:
                topics[category] = sorted(matches)
        return topics

    @staticmethod
    def extract_interests(text: str) -> dict[str, bool]:
        text_lower = text.lower()
        return {
            interest: True
            for interest, pattern in TopicExtractor.INTEREST_PATTERNS.items()
            if re.search(pattern, text_lower)
        }


# ── Conversation Summarization ───────────────────────────────────────────────


class ConversationSummary:
    @staticmethod
    def create_summary(messages: list[dict], _user_name: str = "User") -> dict:
        if not messages:
            return {}
        user_msgs = [m["content"] for m in messages if m.get("role") == "user"]
        ai_msgs = [m["content"] for m in messages if m.get("role") == "assistant"]
        all_text = " ".join(user_msgs + ai_msgs)
        topics = TopicExtractor.extract_topics(all_text)
        interests = TopicExtractor.extract_interests(all_text)
        return {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "message_count": len(messages),
            "user_messages": len(user_msgs),
            "topics": topics,
            "interests": interests,
            "key_questions": user_msgs[:3],
            "summary_text": ConversationSummary._generate_text_summary(
                user_msgs, ai_msgs
            ),
        }

    @staticmethod
    def _generate_text_summary(user_msgs: list[str], ai_msgs: list[str]) -> str:
        if not user_msgs:
            return ""
        first_q = user_msgs[0][:100]
        summary = f"Discussed: {first_q}"
        if len(user_msgs) > 1:
            summary += f" (and {len(user_msgs) - 1} follow-up questions)"
        return summary


# ── Memory Enrichment ────────────────────────────────────────────────────────


class MemoryEnricher:
    @staticmethod
    def enrich_memory(
        fact: str, topics: dict[str, list[str]], interests: dict[str, bool]
    ) -> dict:
        return {
            "fact": fact,
            "created_at": datetime.now(tz=UTC).isoformat(),
            "topics": topics,
            "interests": interests,
            "relevance_score": 1.0,
            "reference_count": 0,
            "related_facts": [],
        }

    @staticmethod
    def calculate_relevance(memory: dict) -> float:
        created = memory.get("created_at", datetime.now(tz=UTC).isoformat())
        base_decay = _time_decay(created, TOPIC_HALF_LIFE_DAYS)
        ref_boost = 1 + (memory.get("reference_count", 0) * 0.15)
        return base_decay * ref_boost


# ── Topic & Interest Tracking ────────────────────────────────────────────────


async def load_topics() -> dict[str, list[dict]]:
    """Load all topics from the database, grouped by category."""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Topic))
            rows = result.scalars().all()

        grouped: dict[str, list[dict]] = {}
        for t in rows:
            entry = {
                "name": t.name,
                "occurrences": t.occurrences,
                "first_mentioned": t.first_mentioned.isoformat()
                if t.first_mentioned
                else "",
                "last_mentioned": t.last_mentioned.isoformat()
                if t.last_mentioned
                else "",
                "strength": t.strength,
            }
            grouped.setdefault(t.category, []).append(entry)
        return grouped
    except Exception as e:
        logger.warning("[personal_assistant] Failed to load topics from DB: %s", e)
        return {}


_topic_lock = asyncio.Lock()


async def track_topic(category: str, topic: str, strength: float = 1.0) -> None:
    """Upsert a topic observation into the database with concurrency retry."""
    now = datetime.now(tz=UTC)
    from sqlalchemy.exc import IntegrityError

    async with _topic_lock:
        for attempt in range(5):
            async with AsyncSessionLocal() as session:
                try:
                    result = await session.execute(
                        select(Topic)
                        .where(Topic.category == category, Topic.name == topic)
                        .with_for_update()
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        existing.occurrences += 1
                        existing.last_mentioned = now
                        existing.strength = min(existing.strength + 0.1, 5.0)
                        session.add(existing)
                        audit_debug(
                            "memory.topics",
                            "topic_updated",
                            topic=topic,
                            category=category,
                            occurrence=existing.occurrences,
                            strength=round(existing.strength, 2),
                        )
                    else:
                        session.add(
                            Topic(
                                category=category,
                                name=topic,
                                occurrences=1,
                                first_mentioned=now,
                                last_mentioned=now,
                                strength=strength,
                            )
                        )
                        audit_info(
                            "memory.topics",
                            "topic_extracted",
                            topic=topic,
                            category=category,
                            occurrence=1,
                            decay_score=1.0,
                        )
                    await session.commit()
                    break
                except IntegrityError:
                    await session.rollback()
                    if attempt == 4:
                        raise
                    await asyncio.sleep(0.01 * (attempt + 1))


async def load_interests() -> dict[str, dict]:
    """Load all interests from the database."""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Interest))
            rows = result.scalars().all()

        return {
            i.name: {
                "count": i.count,
                "first_observed": i.first_observed.isoformat()
                if i.first_observed
                else "",
                "last_observed": i.last_observed.isoformat() if i.last_observed else "",
                "strength": i.strength,
            }
            for i in rows
        }
    except Exception as e:
        logger.warning("[personal_assistant] Failed to load interests from DB: %s", e)
        return {}


_interest_lock = asyncio.Lock()


async def update_interests(extracted_interests: dict[str, bool]) -> None:
    """Upsert interest observations into the database with concurrency retry."""
    now = datetime.now(tz=UTC)
    from sqlalchemy.exc import IntegrityError

    async with _interest_lock:
        for interest_name, present in extracted_interests.items():
            if not present:
                continue

            for attempt in range(5):
                async with AsyncSessionLocal() as session:
                    try:
                        result = await session.execute(
                            select(Interest)
                            .where(Interest.name == interest_name)
                            .with_for_update()
                        )
                        existing = result.scalar_one_or_none()

                        if existing is None:
                            session.add(
                                Interest(
                                    name=interest_name,
                                    count=1,
                                    first_observed=now,
                                    last_observed=now,
                                    strength=1.0,
                                )
                            )
                            audit_debug(
                                "memory.topics",
                                "interest_extracted",
                                interest=interest_name,
                                count=1,
                            )
                        else:
                            existing.count += 1
                            existing.last_observed = now
                            existing.strength = min(existing.strength + 0.2, 5.0)
                            session.add(existing)
                            audit_debug(
                                "memory.topics",
                                "interest_updated",
                                interest=interest_name,
                                count=existing.count,
                                decay_score=round(existing.strength, 2),
                            )
                        await session.commit()
                        break
                    except IntegrityError:
                        await session.rollback()
                        if attempt == 4:
                            raise
                        await asyncio.sleep(0.01 * (attempt + 1))


# ── Conversation Tracking ────────────────────────────────────────────────────


async def load_conversations_history(limit: int | None = None) -> list[dict]:
    """Load conversation records from the database, ordered oldest-first."""
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Conversation).order_by(Conversation.recorded_at)
            if limit and limit > 0:
                # Fetch last N by ordering desc then reversing in Python
                stmt = (
                    select(Conversation)
                    .order_by(Conversation.recorded_at.desc())
                    .limit(limit)
                )
                result = await session.execute(stmt)
                rows = list(reversed(result.scalars().all()))
            else:
                result = await session.execute(stmt)
                rows = result.scalars().all()

        return [_conv_to_dict(c) for c in rows]
    except Exception as e:
        logger.warning(
            "[personal_assistant] Failed to load conversation history from DB: %s", e
        )
        return []


async def record_conversation(messages: list[dict], session_id: str = None) -> dict:
    """Summarise and persist a completed conversation. Returns the summary dict."""
    summary = ConversationSummary.create_summary(messages)
    summary["session_id"] = session_id or f"session_{datetime.now(tz=UTC).timestamp()}"

    async with AsyncSessionLocal() as db_session:
        # Keep only last 100 conversations — delete oldest if over limit
        count_result = await db_session.execute(
            select(Conversation).order_by(Conversation.recorded_at)
        )
        all_convs = count_result.scalars().all()
        if len(all_convs) >= 100:
            excess_ids = [c.id for c in all_convs[: len(all_convs) - 99]]
            await db_session.execute(
                delete(Conversation).where(Conversation.id.in_(excess_ids))
            )

        db_session.add(
            Conversation(
                session_id=summary["session_id"],
                message_count=summary.get("message_count", 0),
                user_messages=summary.get("user_messages", 0),
                topics=summary.get("topics", {}),
                interests=summary.get("interests", {}),
                key_questions=summary.get("key_questions", []),
                summary_text=summary.get("summary_text", ""),
                recorded_at=datetime.now(tz=UTC),
            )
        )
        await db_session.commit()

    for category, items in summary.get("topics", {}).items():
        for item in items:
            await track_topic(category, item)
    await update_interests(summary.get("interests", {}))

    audit_info(
        "memory.topics",
        "conversation_recorded",
        session_id=summary["session_id"],
        message_count=summary.get("message_count", 0),
    )
    return summary


# ── Dynamic Memory Retrieval (with time decay) ──────────────────────────────


def _score_topic(topic: dict) -> float:
    base_strength = topic.get("strength", 1.0)
    occurrences = topic.get("occurrences", 1)
    last_mentioned = topic.get("last_mentioned", topic.get("first_mentioned", ""))
    recency = _time_decay(last_mentioned, TOPIC_HALF_LIFE_DAYS)
    occurrence_factor = 1 + math.log1p(occurrences) * 0.3
    return base_strength * recency * occurrence_factor


def _score_interest(data: dict) -> float:
    base_strength = data.get("strength", 1.0)
    count = data.get("count", 1)
    last_observed = data.get("last_observed", data.get("first_observed", ""))
    recency = _time_decay(last_observed, INTEREST_HALF_LIFE_DAYS)
    count_factor = 1 + math.log1p(count) * 0.2
    return base_strength * recency * count_factor


async def get_current_focus(limit: int = 3) -> list[tuple[str, str, float]]:
    """Detect what the user is CURRENTLY focused on (last FOCUS_WINDOW_DAYS)."""
    topics = await load_topics()
    cutoff = datetime.now(tz=UTC) - timedelta(days=FOCUS_WINDOW_DAYS)
    focus_items = []
    for category, topic_list in topics.items():
        for topic in topic_list:
            try:
                last_dt = datetime.fromisoformat(topic.get("last_mentioned", ""))
                # Normalise to UTC-aware for comparison
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=UTC)
            except (ValueError, TypeError):
                continue
            if last_dt >= cutoff:
                focus_items.append((category, topic["name"], _score_topic(topic)))
    focus_items.sort(key=lambda x: -x[2])
    return focus_items[:limit]


async def get_relevant_topics(limit: int = 5) -> list[tuple[str, str]]:
    """Get most relevant topics with time decay applied."""
    topics = await load_topics()
    all_topics = []
    for category, topic_list in topics.items():
        for topic in topic_list:
            score = _score_topic(topic)
            if score >= RELEVANCE_FLOOR:
                all_topics.append((category, topic["name"], score))
    all_topics.sort(key=lambda x: -x[2])
    return [(cat, name) for cat, name, _ in all_topics[:limit]]


async def get_fading_topics(limit: int = 3) -> list[tuple[str, str, int]]:
    """Get topics that used to be active but are fading."""
    topics = await load_topics()
    cutoff_recent = datetime.now(tz=UTC) - timedelta(days=FOCUS_WINDOW_DAYS)
    cutoff_old = datetime.now(tz=UTC) - timedelta(days=60)
    fading = []
    for category, topic_list in topics.items():
        for topic in topic_list:
            try:
                last_dt = datetime.fromisoformat(topic.get("last_mentioned", ""))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=UTC)
            except (ValueError, TypeError):
                continue
            if (
                cutoff_old <= last_dt < cutoff_recent
                and topic.get("occurrences", 0) >= 3
            ):
                fading.append(
                    (
                        category,
                        topic["name"],
                        (datetime.now(tz=UTC) - last_dt).days,
                    )
                )
    fading.sort(key=lambda x: x[2])
    return fading[:limit]


async def get_user_interests_summary() -> str:
    """Get summary of user interests with time decay."""
    interests = await load_interests()
    scored = []
    for interest, data in interests.items():
        score = _score_interest(data)
        if score >= RELEVANCE_FLOOR:
            scored.append((interest, data, score))
    scored.sort(key=lambda x: -x[2])

    parts = []
    for interest, _data, score in scored[:5]:
        label = interest.replace("_", " ")
        if score > 2.0:
            parts.append(f"- {label} (very active)")
        elif score > 0.8:
            parts.append(f"- {label} (active)")
        elif score > 0.3:
            parts.append(f"- {label} (occasional)")
        else:
            parts.append(f"- {label} (fading)")
    return "\n".join(parts)


async def get_recent_conversation_summary(days: int = 7) -> str:
    """Get tiered summary of recent conversations."""
    history = await load_conversations_history()
    now = datetime.now(tz=UTC)
    today_cutoff = now - timedelta(days=1)
    week_cutoff = now - timedelta(days=days)

    today_summaries: list[str] = []
    week_summaries: list[str] = []

    for conv in reversed(history):
        try:
            conv_time = datetime.fromisoformat(conv.get("timestamp", ""))
            if conv_time.tzinfo is None:
                conv_time = conv_time.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            continue
        if conv_time < week_cutoff:
            break
        summary_text = conv.get("summary_text", "")
        if not summary_text:
            continue
        if conv_time >= today_cutoff:
            questions = conv.get("key_questions", [])
            detail = summary_text
            if questions:
                detail += f" — asked about: {questions[0][:80]}"
            today_summaries.append(detail)
        else:
            week_summaries.append(summary_text)

    parts = []
    if today_summaries:
        parts.append("Today:")
        parts.extend(f"  - {s}" for s in today_summaries[:3])
    if week_summaries:
        parts.append("Earlier this week:")
        parts.extend(f"  - {s}" for s in week_summaries[:3])
    return "\n".join(parts)


# ── Context Builder ──────────────────────────────────────────────────────────


async def get_memory_context_for_prompt() -> str:
    """Build comprehensive, time-aware memory context for system prompt injection."""
    parts = []

    focus = await get_current_focus(3)
    if focus:
        parts.append("## Currently Focused On:")
        for category, topic, _score in focus:
            parts.append(f"- {topic} ({category.replace('_', ' ')})")

    topics = await get_relevant_topics(5)
    focus_names = {t[1] for t in focus} if focus else set()
    filtered = [(c, n) for c, n in topics if n not in focus_names]
    if filtered:
        parts.append("\n## Also Interested In:")
        for category, topic in filtered:
            parts.append(f"- {topic} ({category.replace('_', ' ')})")

    interests = await get_user_interests_summary()
    if interests:
        parts.append("\n## User Activity Patterns:")
        parts.append(interests)

    recent = await get_recent_conversation_summary(7)
    if recent:
        parts.append("\n## Recent Conversations:")
        parts.append(recent)

    fading = await get_fading_topics(3)
    if fading:
        parts.append("\n## Previously Active (not recently mentioned):")
        for _category, topic, days_ago in fading:
            parts.append(f"- {topic} (last mentioned {days_ago} days ago)")

    return "\n".join(parts)


# ── Internal helpers ─────────────────────────────────────────────────────────


def _conv_to_dict(c: Conversation) -> dict:
    """Convert a Conversation ORM row to the legacy summary dict format."""
    return {
        "session_id": c.session_id,
        "timestamp": c.recorded_at.isoformat() if c.recorded_at else "",
        "message_count": c.message_count,
        "user_messages": c.user_messages,
        "topics": c.topics or {},
        "interests": c.interests or {},
        "key_questions": c.key_questions or [],
        "summary_text": c.summary_text or "",
    }
