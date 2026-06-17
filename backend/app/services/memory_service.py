import json
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger_handler import logger
from app.models.memory_item import MemoryItem
from app.models.note import Note
from app.schemas.memory import MemoryCreate, MemoryUpdate

INTERVALS = [1, 2, 4, 7, 15, 30]
VALID_TYPES = {"review", "todo", "reminder", "long_term", "memo"}
VALID_STATUSES = {"active", "done", "archived"}
VALID_PRIORITIES = {"low", "medium", "high"}


def get_next_review_interval(review_count: int) -> int:
    if review_count < len(INTERVALS):
        return INTERVALS[review_count]
    return INTERVALS[-1]


class MemoryService:
    def _normalize_type(self, value: str | None) -> str:
        item_type = (value or "memo").strip()
        return item_type if item_type in VALID_TYPES else "memo"

    def _normalize_status(self, value: str | None) -> str:
        status = (value or "active").strip()
        return status if status in VALID_STATUSES else "active"

    def _normalize_priority(self, value: str | None) -> str:
        priority = (value or "medium").strip()
        return priority if priority in VALID_PRIORITIES else "medium"

    def _to_dict(self, item: MemoryItem) -> dict:
        return {
            "id": item.id,
            "user_id": item.user_id,
            "source_type": item.source_type,
            "source_id": item.source_id,
            "type": item.type,
            "title": item.title,
            "content": item.content or "",
            "status": item.status,
            "priority": item.priority,
            "due_at": str(item.due_at) if item.due_at else None,
            "remind_at": str(item.remind_at) if item.remind_at else None,
            "completed_at": str(item.completed_at) if item.completed_at else None,
            "archived_at": str(item.archived_at) if item.archived_at else None,
            "review_count": item.review_count or 0,
            "interval_days": item.interval_days or 1,
            "metadata_json": item.metadata_json,
            "created_at": str(item.created_at) if item.created_at else None,
            "updated_at": str(item.updated_at) if item.updated_at else None,
        }

    async def create_memory(self, db: AsyncSession, user_id: str, payload: MemoryCreate) -> dict:
        now = datetime.now()
        item_type = self._normalize_type(payload.type)
        priority = self._normalize_priority(payload.priority)
        due_at = payload.due_at
        remind_at = payload.remind_at or due_at
        review_count = 0
        interval_days = 1

        if item_type == "review":
            due_at = due_at or now + timedelta(days=1)
            remind_at = remind_at or due_at

        item = MemoryItem(
            id=str(uuid.uuid4()),
            user_id=user_id,
            source_type=payload.source_type or "manual",
            source_id=payload.source_id,
            type=item_type,
            title=payload.title,
            content=payload.content or "",
            status="active",
            priority=priority,
            due_at=due_at,
            remind_at=remind_at,
            review_count=review_count,
            interval_days=interval_days,
            metadata_json=payload.metadata_json,
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return self._to_dict(item)

    async def create_review_for_note(
        self,
        db: AsyncSession,
        user_id: str,
        note_id: str,
        title: str,
        content_preview: str,
    ) -> dict:
        now = datetime.now()
        item = MemoryItem(
            id=str(uuid.uuid4()),
            user_id=user_id,
            source_type="note",
            source_id=note_id,
            type="review",
            title=title or "未命名笔记",
            content=content_preview or "",
            status="active",
            priority="medium",
            due_at=now + timedelta(days=1),
            remind_at=now + timedelta(days=1),
            review_count=0,
            interval_days=1,
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return self._to_dict(item)

    async def list_memories(
        self,
        db: AsyncSession,
        user_id: str,
        type: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        conditions = [MemoryItem.user_id == user_id]
        if type:
            conditions.append(MemoryItem.type == type)
        if status:
            conditions.append(MemoryItem.status == status)

        stmt = (
            select(MemoryItem)
            .where(*conditions)
            .order_by(MemoryItem.status.asc(), MemoryItem.due_at.asc(), MemoryItem.created_at.desc())
        )
        result = await db.execute(stmt)
        return [self._to_dict(item) for item in result.scalars().all()]

    async def get_today_memories(self, db: AsyncSession, user_id: str) -> list[dict]:
        now = datetime.now()
        end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        stmt = (
            select(MemoryItem)
            .where(
                MemoryItem.user_id == user_id,
                MemoryItem.status == "active",
                or_(
                    MemoryItem.due_at <= end_of_today,
                    MemoryItem.remind_at <= end_of_today,
                ),
            )
            .order_by(MemoryItem.priority.desc(), MemoryItem.due_at.asc(), MemoryItem.created_at.desc())
        )
        result = await db.execute(stmt)
        return [self._to_dict(item) for item in result.scalars().all()]

    async def get_memory(self, db: AsyncSession, user_id: str, memory_id: str) -> MemoryItem | None:
        stmt = select(MemoryItem).where(MemoryItem.id == memory_id, MemoryItem.user_id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_memory_dict(self, db: AsyncSession, user_id: str, memory_id: str) -> dict | None:
        item = await self.get_memory(db, user_id, memory_id)
        return self._to_dict(item) if item else None

    async def update_memory(
        self,
        db: AsyncSession,
        user_id: str,
        memory_id: str,
        payload: MemoryUpdate,
    ) -> dict | None:
        item = await self.get_memory(db, user_id, memory_id)
        if not item:
            return None

        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            if key == "type" and value is not None:
                value = self._normalize_type(value)
            if key == "status" and value is not None:
                value = self._normalize_status(value)
            if key == "priority" and value is not None:
                value = self._normalize_priority(value)
            setattr(item, key, value)

        await db.commit()
        await db.refresh(item)
        return self._to_dict(item)

    async def complete_memory(self, db: AsyncSession, user_id: str, memory_id: str) -> dict:
        item = await self.get_memory(db, user_id, memory_id)
        if not item:
            return {"success": False, "message": "记忆事项不存在"}
        if item.type == "review":
            return {"success": False, "message": "复习事项请使用标记已复习操作"}

        item.status = "done"
        item.completed_at = datetime.now()
        await db.commit()
        await db.refresh(item)
        return {"success": True, "message": "事项已完成", "memory": self._to_dict(item)}

    async def postpone_memory(self, db: AsyncSession, user_id: str, memory_id: str, days: int) -> dict:
        item = await self.get_memory(db, user_id, memory_id)
        if not item:
            return {"success": False, "message": "记忆事项不存在"}

        days = max(1, days)
        next_at = datetime.now() + timedelta(days=days)
        item.due_at = next_at
        item.remind_at = next_at
        item.status = "active"
        await db.commit()
        await db.refresh(item)
        return {"success": True, "message": f"已延期 {days} 天", "memory": self._to_dict(item)}

    async def archive_memory(self, db: AsyncSession, user_id: str, memory_id: str) -> dict:
        item = await self.get_memory(db, user_id, memory_id)
        if not item:
            return {"success": False, "message": "记忆事项不存在"}

        item.status = "archived"
        item.archived_at = datetime.now()
        await db.commit()
        await db.refresh(item)
        return {"success": True, "message": "事项已归档", "memory": self._to_dict(item)}

    async def delete_memory(self, db: AsyncSession, user_id: str, memory_id: str) -> bool:
        result = await db.execute(
            delete(MemoryItem).where(MemoryItem.id == memory_id, MemoryItem.user_id == user_id)
        )
        await db.commit()
        return bool(result.rowcount)

    async def delete_note_memories(self, db: AsyncSession, user_id: str, note_id: str) -> None:
        await db.execute(
            delete(MemoryItem).where(
                MemoryItem.user_id == user_id,
                MemoryItem.source_type == "note",
                MemoryItem.source_id == note_id,
                MemoryItem.type == "review",
            )
        )
        await db.commit()

    async def mark_reviewed(self, db: AsyncSession, user_id: str, memory_id: str) -> dict:
        item = await self.get_memory(db, user_id, memory_id)
        if not item:
            return {"success": False, "message": "复习事项不存在"}
        if item.type != "review":
            return {"success": False, "message": "该事项不是复习类型"}

        now = datetime.now()
        item.review_count = (item.review_count or 0) + 1
        item.interval_days = get_next_review_interval(item.review_count)
        next_at = now + timedelta(days=item.interval_days)
        item.due_at = next_at
        item.remind_at = next_at
        item.status = "active"
        await db.commit()
        await db.refresh(item)
        return {"success": True, "message": "已标记复习完成", "memory": self._to_dict(item)}

    async def generate_review_question(self, db: AsyncSession, user_id: str, memory_id: str) -> dict:
        raw = ""
        try:
            item = await self.get_memory(db, user_id, memory_id)
            if not item or item.type != "review":
                return {"question": "复习事项不存在", "choices": [], "answer": ""}

            content = item.content or ""
            if item.source_type == "note" and item.source_id:
                stmt = select(Note).where(Note.id == item.source_id, Note.user_id == user_id)
                result = await db.execute(stmt)
                note = result.scalar_one_or_none()
                if note and note.content:
                    content = note.content

            from langchain_core.messages import HumanMessage

            from app.core.background_init import init_manager
            from app.utils.prompt_loader import load_prompt

            prompt_template = load_prompt("review_question_prompt")
            prompt = prompt_template.format(content=content[:2000])
            response = await init_manager.chat_model.ainvoke([HumanMessage(content=prompt)])
            raw = response.content.strip()

            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            brace_start = raw.find("{")
            if brace_start > 0:
                raw = raw[brace_start:]

            data = json.loads(raw)
            return {
                "question": data["question"],
                "choices": data["choices"],
                "answer": data["answer"],
            }
        except Exception as e:
            logger.error(f"生成记忆复习题失败 memory_id={memory_id}: {e} | raw={raw[:300]}")
            return {
                "question": "请回顾这条记忆事项的主要内容",
                "choices": ["不太确定", "需要复习", "基本掌握", "完全理解"],
                "answer": "基本掌握",
            }


memory_service = MemoryService()


def get_memory_service() -> MemoryService:
    return memory_service
