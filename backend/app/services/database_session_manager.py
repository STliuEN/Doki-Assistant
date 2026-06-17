import asyncio

from app.core.logger_handler import logger
from app.db.db_config import AsyncSessionLocal
from app.models.chat_history import ChatMessage, ChatSession


class DatabaseSessionManager:
    """基于数据库的会话管理器"""

    def __init__(self):
        """初始化会话管理器"""
        self._lock = asyncio.Lock()

    @staticmethod
    def _message_to_dict(message: ChatMessage) -> dict:
        return {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """粗略 token 估算：中文和混合文本按 2 字符约 1 token 处理。"""
        return max(1, len(text) // 2)

    def trim_history(self, history: list[tuple[str, str]], context_settings=None) -> list[tuple[str, str]]:
        """根据上下文设置裁剪历史轮次。"""
        if not history:
            return []

        mode = getattr(context_settings, "mode", "auto") if context_settings else "auto"
        recent_turns = getattr(context_settings, "recent_turns", None) if context_settings else None
        max_tokens = getattr(context_settings, "max_tokens", None) if context_settings else None

        if mode == "current_only":
            return []

        default_tokens = {
            "low": 2000,
            "medium": 4000,
            "high": 8000,
            "short": 2000,
            "standard": 4000,
            "long": 8000,
            "auto": 4000,
        }
        if mode == "custom":
            keep_turns = recent_turns if isinstance(recent_turns, int) and recent_turns > 0 else 6
            return history[-keep_turns:]

        token_budget = max_tokens if isinstance(max_tokens, int) and max_tokens > 0 else default_tokens.get(mode, 4000)
        min_recent_turns = recent_turns if isinstance(recent_turns, int) and recent_turns > 0 else 6

        selected: list[tuple[str, str]] = []
        used_tokens = 0
        for index, turn in enumerate(reversed(history)):
            user_msg, assistant_msg = turn
            turn_tokens = self.estimate_tokens(user_msg) + self.estimate_tokens(assistant_msg)
            must_keep = index < min_recent_turns
            if selected and not must_keep and used_tokens + turn_tokens > token_budget:
                break
            selected.append(turn)
            used_tokens += turn_tokens

        return list(reversed(selected))

    @classmethod
    async def create(cls) -> "DatabaseSessionManager":
        """
        异步创建并初始化 DatabaseSessionManager
        :return: 初始化完成的 DatabaseSessionManager 实例
        """
        instance = cls()
        logger.info("【数据库会话管理】初始化完成")
        return instance

    async def get_session(self, session_id: str, user_id: str) -> dict:
        """获取会话"""
        async with AsyncSessionLocal() as db:
            # 尝试查找会话，验证属于该用户
            result = await db.run_sync(
                lambda session: session.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == user_id).first()
            )

            if result:
                # 获取会话历史
                messages = await db.run_sync(
                    lambda session: session.query(ChatMessage).filter(ChatMessage.session_id == result.id).order_by(ChatMessage.created_at).all()
                )
                # 转换为 (user_message, assistant_message) 格式
                history = []
                i = 0
                while i < len(messages):
                    if messages[i].role == "user" and i + 1 < len(messages) and messages[i+1].role == "assistant":
                        history.append((messages[i].content, messages[i+1].content))
                        i += 2
                    else:
                        i += 1
                return {"history": history}
            else:
                # 检查会话id是否存在
                existing_session = await db.run_sync(
                    lambda session: session.query(ChatSession).filter(ChatSession.id == session_id).first()
                )

                if existing_session:
                    # 会话存在但不属于当前用户
                    logger.warning(f"【数据库会话管理】会话 {session_id} 不属于用户 {user_id}")
                    from fastapi import HTTPException, status
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="当前会话不属于你"
                    )
                else:
                    # 会话不存在，创建一个新的
                    new_session = ChatSession(
                        id=session_id,
                        user_id=user_id,
                        title="新的对话"
                    )
                    db.add(new_session)
                    await db.commit()
                    await db.refresh(new_session)
                    logger.info(f"【数据库会话管理】创建新会话: {session_id} 属于用户: {user_id}")
                    return {"history": []}

    async def add_message(self, session_id: str, user_id: str, user_message: str, assistant_message: str):
        """添加消息并保存到数据库"""
        async with AsyncSessionLocal() as db:
            # 检查会话id是否存在
            existing_session = await db.run_sync(
                lambda session: session.query(ChatSession).filter(ChatSession.id == session_id).first()
            )

            if existing_session:
                # 检查会话是否属于当前用户
                if existing_session.user_id != user_id:
                    # 会话存在但不属于当前用户，不添加消息
                    logger.warning(f"【数据库会话管理】会话 {session_id} 不属于用户 {user_id}，无法添加消息")
                    from fastapi import HTTPException, status
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="当前会话不属于你，无法添加消息"
                    )
                session = existing_session
            else:
                # 会话不存在，创建一个新的
                session = ChatSession(
                    id=session_id,
                    user_id=user_id,
                    title="新的对话"
                )
                db.add(session)
                await db.commit()
                await db.refresh(session)

            # 检查是否是新会话且标题为默认值，如果是则更新为用户的第一个问题
            if session.title == "新的对话":
                # 生成用户问题的摘要作为标题（截取前30个字符）
                title_summary = user_message[:30].strip()
                if len(user_message) > 30:
                    title_summary += "..."
                session.title = title_summary

            # 添加用户消息
            user_msg = ChatMessage(
                session_id=session.id,
                role="user",
                content=user_message
            )
            db.add(user_msg)

            # 添加助手消息
            assistant_msg = ChatMessage(
                session_id=session.id,
                role="assistant",
                content=assistant_message
            )
            db.add(assistant_msg)

            await db.commit()
            logger.info(f"【数据库会话管理】添加消息到会话: {session_id} 属于用户: {user_id}")

    async def get_history(self, session_id: str, user_id: str) -> list[tuple[str, str]]:
        """获取会话历史"""
        session_data = await self.get_session(session_id, user_id)
        return session_data.get("history", [])

    async def get_context(self, session_id: str, user_id: str, context_settings=None) -> list[tuple[str, str]]:
        """获取按上下文设置裁剪后的会话历史。"""
        history = await self.get_history(session_id, user_id)
        return self.trim_history(history, context_settings)

    async def get_messages(self, session_id: str, user_id: str) -> list[dict]:
        """获取会话的原始消息列表（带消息 ID）。"""
        async with AsyncSessionLocal() as db:
            session = await db.run_sync(
                lambda s: s.query(ChatSession)
                .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
                .first()
            )
            if not session:
                existing_session = await db.run_sync(
                    lambda s: s.query(ChatSession).filter(ChatSession.id == session_id).first()
                )
                if existing_session:
                    logger.warning(f"【数据库会话管理】会话 {session_id} 不属于用户 {user_id}")
                    from fastapi import HTTPException, status
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="当前会话不属于你"
                    )
                return []

            messages = await db.run_sync(
                lambda s: s.query(ChatMessage)
                .filter(ChatMessage.session_id == session.id)
                .order_by(ChatMessage.created_at, ChatMessage.id)
                .all()
            )
            return [self._message_to_dict(message) for message in messages]

    async def delete_message(
        self,
        session_id: str,
        user_id: str,
        message_id: int,
        mode: str = "single",
    ) -> dict:
        """删除单条消息或相关消息。mode: single / pair / after。"""
        if mode not in {"single", "pair", "after"}:
            mode = "single"

        async with AsyncSessionLocal() as db:
            session = await db.run_sync(
                lambda s: s.query(ChatSession)
                .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
                .first()
            )
            if not session:
                existing_session = await db.run_sync(
                    lambda s: s.query(ChatSession).filter(ChatSession.id == session_id).first()
                )
                if existing_session:
                    logger.warning(f"【数据库会话管理】会话 {session_id} 不属于用户 {user_id}")
                    from fastapi import HTTPException, status
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="当前会话不属于你"
                    )
                return {"session_id": session_id, "deleted_ids": []}

            messages = await db.run_sync(
                lambda s: s.query(ChatMessage)
                .filter(ChatMessage.session_id == session.id)
                .order_by(ChatMessage.created_at, ChatMessage.id)
                .all()
            )
            target_index = next((i for i, message in enumerate(messages) if message.id == message_id), None)
            if target_index is None:
                return {"session_id": session_id, "deleted_ids": []}

            target = messages[target_index]
            to_delete: list[ChatMessage] = [target]
            if mode == "pair" and target.role == "user":
                if target_index + 1 < len(messages) and messages[target_index + 1].role == "assistant":
                    to_delete.append(messages[target_index + 1])
            elif mode == "after":
                to_delete = messages[target_index:]

            deleted_ids = [message.id for message in to_delete]
            for message in to_delete:
                await db.delete(message)
            await db.commit()
            logger.info(f"【数据库会话管理】删除会话 {session_id} 消息: {deleted_ids}")
            return {"session_id": session_id, "deleted_ids": deleted_ids}

    async def get_regenerate_payload(self, session_id: str, user_id: str, assistant_message_id: int) -> dict:
        """获取重新生成所需的上一条用户消息和历史。"""
        async with AsyncSessionLocal() as db:
            session = await db.run_sync(
                lambda s: s.query(ChatSession)
                .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
                .first()
            )
            if not session:
                existing_session = await db.run_sync(
                    lambda s: s.query(ChatSession).filter(ChatSession.id == session_id).first()
                )
                if existing_session:
                    logger.warning(f"【数据库会话管理】会话 {session_id} 不属于用户 {user_id}")
                    from fastapi import HTTPException, status
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="当前会话不属于你"
                    )
                from fastapi import HTTPException, status
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

            messages = await db.run_sync(
                lambda s: s.query(ChatMessage)
                .filter(ChatMessage.session_id == session.id)
                .order_by(ChatMessage.created_at, ChatMessage.id)
                .all()
            )
            target_index = next((i for i, message in enumerate(messages) if message.id == assistant_message_id), None)
            if target_index is None:
                from fastapi import HTTPException, status
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="message not found")

            target = messages[target_index]
            if target.role != "assistant":
                from fastapi import HTTPException, status
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target message must be assistant")

            user_index = target_index - 1
            while user_index >= 0 and messages[user_index].role != "user":
                user_index -= 1
            if user_index < 0:
                from fastapi import HTTPException, status
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="previous user message not found")

            history_messages = messages[:user_index]
            history: list[tuple[str, str]] = []
            i = 0
            while i < len(history_messages):
                if (
                    history_messages[i].role == "user"
                    and i + 1 < len(history_messages)
                    and history_messages[i + 1].role == "assistant"
                ):
                    history.append((history_messages[i].content, history_messages[i + 1].content))
                    i += 2
                else:
                    i += 1

            return {
                "query": messages[user_index].content,
                "history": history,
                "message_id": assistant_message_id,
            }

    async def update_message_content(self, session_id: str, user_id: str, message_id: int, content: str) -> dict:
        """更新单条消息内容。"""
        async with AsyncSessionLocal() as db:
            session = await db.run_sync(
                lambda s: s.query(ChatSession)
                .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
                .first()
            )
            if not session:
                from fastapi import HTTPException, status
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

            message = await db.run_sync(
                lambda s: s.query(ChatMessage)
                .filter(ChatMessage.id == message_id, ChatMessage.session_id == session.id)
                .first()
            )
            if not message:
                from fastapi import HTTPException, status
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="message not found")

            message.content = content
            await db.commit()
            await db.refresh(message)
            return self._message_to_dict(message)

    async def clear_session(self, session_id: str, user_id: str):
        """清除会话"""
        async with AsyncSessionLocal() as db:
            # 查找会话，验证属于该用户
            session = await db.run_sync(
                lambda session: session.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == user_id).first()
            )

            if session:
                # 删除会话（级联删除消息）
                await db.delete(session)
                await db.commit()
                logger.info(f"【数据库会话管理】会话 {session_id} 已清除，属于用户: {user_id}")

    async def get_all_session_ids(self, user_id: str | None = None) -> list[str]:
        """获取所有会话 ID，如果提供了 user_id，则只返回该用户的会话"""
        async with AsyncSessionLocal() as db:
            if user_id:
                sessions = await db.run_sync(
                    lambda session: session.query(ChatSession).filter(ChatSession.user_id == user_id).all()
                )
            else:
                sessions = await db.run_sync(
                    lambda session: session.query(ChatSession).all()
                )
            return [session.id for session in sessions]

    async def get_user_sessions(self, user_id: str) -> list[dict]:
        """获取用户所有会话详细信息，按更新时间降序排列"""
        async with AsyncSessionLocal() as db:
            sessions = await db.run_sync(
                lambda session: session.query(ChatSession)
                .filter(ChatSession.user_id == user_id)
                .order_by(ChatSession.updated_at.desc())
                .all()
            )
            return [
                {
                    "id": session.id,
                    "title": session.title,
                    "created_at": session.created_at.isoformat() if session.created_at else None,
                    "updated_at": session.updated_at.isoformat() if session.updated_at else None
                }
                for session in sessions
            ]


# 全局数据库会话管理器实例
database_session_manager = None

# 初始化数据库会话管理器
async def init_database_session_manager():
    """
    初始化数据库会话管理器
    :return: 初始化完成的 DatabaseSessionManager 实例
    """
    global database_session_manager
    database_session_manager = await DatabaseSessionManager.create()
    return database_session_manager
