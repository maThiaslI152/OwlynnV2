import logging
from typing import Optional
import uuid

from datetime import datetime, timedelta, timezone
from sqlalchemy import select, delete
from src.models.db import AsyncSessionLocal
from src.models.ui_template import UITemplate

logger = logging.getLogger(__name__)


async def create_ui_template(type_: str, payload: dict) -> str:
    """Store a UI template payload and return its unique ID."""
    template_id = f"tpl-{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as session:
        tpl = UITemplate(id=template_id, type=type_, payload=payload)
        session.add(tpl)
        await session.commit()
    return template_id


async def get_ui_template(template_id: str) -> Optional[dict]:
    """Retrieve a UI template by ID."""
    async with AsyncSessionLocal() as session:
        stmt = select(UITemplate).filter_by(id=template_id)
        result = await session.execute(stmt)
        tpl = result.scalars().first()
        if tpl:
            return {"id": tpl.id, "type": tpl.type, "payload": tpl.payload}
        return None


async def cleanup_old_templates(days: int = 30) -> int:
    """Delete UI templates older than the specified number of days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    # The cutoff needs to be naive UTC for SQLite compatibility in some setups,
    # or just use standard datetime comparison.
    cutoff_naive = cutoff.replace(tzinfo=None)

    async with AsyncSessionLocal() as session:
        stmt = delete(UITemplate).where(UITemplate.created_at < cutoff_naive)
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount
