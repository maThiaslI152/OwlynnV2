#!/usr/bin/env python3
"""
One-shot migration script: JSON flat files → PostgreSQL.

Run once after `alembic upgrade head` to move existing user data into the
new unified PostgreSQL schema. Safe to re-run (uses upsert/INSERT IGNORE).

Usage:
    source .venv/bin/activate
    python scripts/migrate_to_postgres.py

    # Dry-run (no writes):
    python scripts/migrate_to_postgres.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate")

DATA_DIR = ROOT / "data"
DRY_RUN = False


def _load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else []


def _counts(**kwargs) -> str:
    return "  ".join(f"{k}={v}" for k, v in kwargs.items())


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------


async def migrate_memories(session) -> int:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from src.memory.db_models import Memory

    rows = _load_json(DATA_DIR / "memories.json")
    if not rows:
        return 0
    count = 0
    for row in rows:
        fact = row.get("fact", "").strip()
        if not fact:
            continue
        if not DRY_RUN:
            await session.execute(
                pg_insert(Memory)
                .values(fact=fact)
                .on_conflict_do_nothing(index_elements=["fact"])
            )
        count += 1
    return count


async def migrate_topics(session) -> int:
    from datetime import datetime, timezone
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from src.memory.db_models import Topic

    data = _load_json(DATA_DIR / "topics.json", {})
    count = 0
    for category, items in data.items():
        if not isinstance(items, list):
            continue
        for item in items:
            name = item.get("name", "").strip()
            if not name:
                continue
            vals = dict(
                category=category,
                name=name,
                occurrences=item.get("occurrences", 1),
                first_mentioned=_parse_dt(item.get("first_mentioned")),
                last_mentioned=_parse_dt(item.get("last_mentioned")),
                strength=float(item.get("strength", 1.0)),
            )
            if not DRY_RUN:
                await session.execute(
                    pg_insert(Topic)
                    .values(**vals)
                    .on_conflict_do_update(
                        index_elements=["category", "name"],
                        set_={"occurrences": vals["occurrences"], "strength": vals["strength"]},
                    )
                )
            count += 1
    return count


async def migrate_interests(session) -> int:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from src.memory.db_models import Interest

    data = _load_json(DATA_DIR / "interests.json", {})
    count = 0
    for name, item in data.items():
        if not isinstance(item, dict):
            continue
        vals = dict(
            name=name,
            count=item.get("count", 1),
            first_observed=_parse_dt(item.get("first_observed")),
            last_observed=_parse_dt(item.get("last_observed")),
            strength=float(item.get("strength", 1.0)),
        )
        if not DRY_RUN:
            await session.execute(
                pg_insert(Interest)
                .values(**vals)
                .on_conflict_do_update(
                    index_elements=["name"],
                    set_={"count": vals["count"], "strength": vals["strength"]},
                )
            )
        count += 1
    return count


async def migrate_conversations(session) -> int:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from src.memory.db_models import Conversation

    rows = _load_json(DATA_DIR / "conversations.json")
    count = 0
    for row in rows:
        vals = dict(
            session_id=row.get("session_id", ""),
            message_count=row.get("message_count", 0),
            user_messages=row.get("user_messages", 0),
            topics=row.get("topics", {}),
            interests=row.get("interests", {}),
            key_questions=row.get("key_questions", []),
            summary_text=row.get("summary_text", ""),
        )
        if not DRY_RUN:
            await session.execute(pg_insert(Conversation).values(**vals).on_conflict_do_nothing())
        count += 1
    return count


async def migrate_user_profile(session) -> int:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from src.memory.db_models import UserProfile

    path = DATA_DIR / "user_profile.json"
    if not path.exists():
        return 0
    data = _load_json(path, {})
    if not DRY_RUN:
        await session.execute(
            pg_insert(UserProfile)
            .values(id=1, data=data)
            .on_conflict_do_update(index_elements=["id"], set_={"data": data})
        )
    return 1


async def migrate_persona(session) -> int:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from src.memory.db_models import Persona

    count = 0
    # Active persona
    active_path = DATA_DIR / "persona.json"
    if active_path.exists():
        data = _load_json(active_path, {})
        pid = data.get("id") or "default"
        if not DRY_RUN:
            await session.execute(
                pg_insert(Persona)
                .values(id=pid, data=data, is_active=True)
                .on_conflict_do_update(
                    index_elements=["id"], set_={"data": data, "is_active": True}
                )
            )
        count += 1

    # All other personas in data/personas/
    personas_dir = DATA_DIR / "personas"
    if personas_dir.exists():
        for f in personas_dir.glob("*.json"):
            pdata = _load_json(f, {})
            pid = pdata.get("id") or f.stem
            if not DRY_RUN:
                await session.execute(
                    pg_insert(Persona)
                    .values(id=pid, data=pdata, is_active=False)
                    .on_conflict_do_nothing(index_elements=["id"])
                )
            count += 1
    return count


async def migrate_courses(session) -> int:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from src.memory.db_models import Course

    rows = _load_json(DATA_DIR / "courses.json")
    if not isinstance(rows, list) or not rows:
        return 0
    count = 0
    for row in rows:
        cid = row.get("id") or row.get("course_id", "")
        if not cid:
            continue
        if not DRY_RUN:
            await session.execute(
                pg_insert(Course)
                .values(id=cid, data=row)
                .on_conflict_do_nothing(index_elements=["id"])
            )
        count += 1
    return count


async def migrate_quiz_sessions(session) -> int:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from src.memory.db_models import QuizSession

    quiz_dir = DATA_DIR / "quiz_sessions"
    if not quiz_dir.exists():
        return 0
    count = 0
    for f in quiz_dir.glob("*.json"):
        row = _load_json(f, {})
        qid = row.get("id") or f.stem
        vals = dict(
            id=qid,
            course_id=row.get("course_id"),
            status=row.get("status", "completed"),
            score=row.get("score"),
            questions=row.get("questions", []),
            answers=row.get("answers", []),
            started_at=_parse_dt(row.get("started_at")),
            completed_at=_parse_dt(row.get("completed_at")),
        )
        if not DRY_RUN:
            await session.execute(
                pg_insert(QuizSession)
                .values(**vals)
                .on_conflict_do_nothing(index_elements=["id"])
            )
        count += 1
    return count


async def migrate_pentest_engagements(session) -> int:
    """Migrate all engagement directories to PostgreSQL tables."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from src.memory.db_models import (
        PentestCredentials,
        PentestEngagement,
        PentestFinding,
        PentestScope,
        PentestTarget,
        PentestTimeline,
    )

    engagements_dir = DATA_DIR / "pentest_engagements"
    if not engagements_dir.exists():
        return 0

    eng_count = 0
    for eng_dir in sorted(engagements_dir.iterdir()):
        if not eng_dir.is_dir():
            continue

        eng = _load_json(eng_dir / "engagement.json", {})
        eid = eng.get("id") or eng_dir.name
        if not eid:
            continue

        notes_path = eng_dir / "notes.md"
        notes = notes_path.read_text(encoding="utf-8") if notes_path.exists() else ""
        task_graph = _load_json(eng_dir / "task_graph.json", {})
        engagement_data = _load_json(eng_dir / "engagement_data.json", {})

        if not DRY_RUN:
            await session.execute(
                pg_insert(PentestEngagement)
                .values(
                    id=eid,
                    name=eng.get("name", ""),
                    client=eng.get("client", ""),
                    phase=eng.get("phase", "scope"),
                    status=eng.get("status", "active"),
                    description=eng.get("description", ""),
                    assessor=eng.get("assessor", ""),
                    notes=notes,
                    engagement_data=engagement_data,
                    task_graph=task_graph,
                    created_at=_parse_dt(eng.get("created_at")),
                    updated_at=_parse_dt(eng.get("updated_at")),
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )

            # Scope
            scope = _load_json(eng_dir / "scope.json", {})
            await session.execute(
                pg_insert(PentestScope)
                .values(
                    engagement_id=eid,
                    targets=scope.get("targets", []),
                    exclusions=scope.get("exclusions", []),
                    rules_of_engagement=scope.get("rules_of_engagement", ""),
                )
                .on_conflict_do_nothing()
            )

            # Findings
            findings_data = _load_json(eng_dir / "findings.json", {})
            for f in findings_data.get("findings", []):
                fid = f.get("id", "")
                if not fid:
                    continue
                await session.execute(
                    pg_insert(PentestFinding)
                    .values(
                        id=fid,
                        engagement_id=eid,
                        title=f.get("title", ""),
                        severity=f.get("severity", "info"),
                        cvss=f.get("cvss"),
                        cwe=f.get("cwe", ""),
                        cve=f.get("cve", ""),
                        owasp_category=f.get("owasp_category", ""),
                        target=f.get("target", ""),
                        description=f.get("description", ""),
                        remediation=f.get("remediation", ""),
                        phase=f.get("phase", ""),
                        status=f.get("status", "suspected"),
                        tags=f.get("tags", []),
                        evidence_refs=f.get("evidence_refs", []),
                        discovered_at=_parse_dt(f.get("discovered_at")),
                        retested_at=_parse_dt(f.get("retested_at")),
                    )
                    .on_conflict_do_nothing(index_elements=["id"])
                )

            # Targets
            targets_data = _load_json(eng_dir / "targets.json", {})
            for t in targets_data.get("hosts", []):
                await session.execute(
                    pg_insert(PentestTarget)
                    .values(
                        engagement_id=eid,
                        ip=t.get("ip", ""),
                        hostname=t.get("hostname", ""),
                        ports=t.get("ports", []),
                        discovered_at=_parse_dt(t.get("discovered_at")),
                    )
                    .on_conflict_do_nothing()
                )

            # Timeline
            timeline_data = _load_json(eng_dir / "timeline.json", {})
            for evt in timeline_data.get("events", []):
                evid = evt.get("id", "")
                if not evid:
                    continue
                extra = {k: v for k, v in evt.items() if k not in ("id", "timestamp", "type", "summary")}
                await session.execute(
                    pg_insert(PentestTimeline)
                    .values(
                        id=evid,
                        engagement_id=eid,
                        event_type=evt.get("type", ""),
                        summary=evt.get("summary", ""),
                        extra=extra,
                        occurred_at=_parse_dt(evt.get("timestamp")),
                    )
                    .on_conflict_do_nothing(index_elements=["id"])
                )

            # Credentials (encrypted blob)
            creds_path = eng_dir / "credentials.enc"
            if creds_path.exists():
                blob = creds_path.read_bytes()
                await session.execute(
                    pg_insert(PentestCredentials)
                    .values(engagement_id=eid, data=blob)
                    .on_conflict_do_nothing()
                )

        eng_count += 1

    return eng_count


def _parse_dt(val):
    """Parse ISO datetime string to datetime object, or return None."""
    if not val:
        return None
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main(dry_run: bool) -> None:
    global DRY_RUN
    DRY_RUN = dry_run

    from src.models.db import AsyncSessionLocal

    if dry_run:
        logger.info("DRY-RUN mode — no data will be written.")

    async with AsyncSessionLocal() as session:
        logger.info("Migrating memories...")
        n = await migrate_memories(session)
        logger.info("  → %d facts", n)

        logger.info("Migrating topics...")
        n = await migrate_topics(session)
        logger.info("  → %d topics", n)

        logger.info("Migrating interests...")
        n = await migrate_interests(session)
        logger.info("  → %d interests", n)

        logger.info("Migrating conversations...")
        n = await migrate_conversations(session)
        logger.info("  → %d conversations", n)

        logger.info("Migrating user profile...")
        n = await migrate_user_profile(session)
        logger.info("  → %d rows", n)

        logger.info("Migrating personas...")
        n = await migrate_persona(session)
        logger.info("  → %d personas", n)

        logger.info("Migrating courses...")
        n = await migrate_courses(session)
        logger.info("  → %d courses", n)

        logger.info("Migrating quiz sessions...")
        n = await migrate_quiz_sessions(session)
        logger.info("  → %d quiz sessions", n)

        logger.info("Migrating pentest engagements...")
        n = await migrate_pentest_engagements(session)
        logger.info("  → %d engagements", n)

        if not dry_run:
            await session.commit()
            logger.info("✅ Migration committed successfully.")
        else:
            await session.rollback()
            logger.info("✅ Dry-run complete — all changes rolled back.")

    logger.info(
        "\n[NOTE] Qdrant LTM memories were NOT migrated (fresh start as configured).\n"
        "       New memories will be extracted and stored in PostgreSQL going forward.\n"
        "[NOTE] Evidence files in data/pentest_engagements/*/evidence/ remain on disk.\n"
        "       Their SHA-256 metadata is referenced via evidence_refs in pentest_findings."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate OwlynnV2 JSON data to PostgreSQL.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate migration without writes.")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
