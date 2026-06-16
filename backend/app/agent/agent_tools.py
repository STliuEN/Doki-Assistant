"""Legacy exports for the modular agent tool system.

Tool implementations live under ``app.agent.tools.<tool_id>``. This module
keeps old import paths working while the registry loads tools from modules.
"""

from app.agent.tool_context import (
    get_current_user_id_from_context,
    get_thinking_callback_from_context,
    set_current_user_id,
    set_thinking_callback,
)
from app.agent.tools.create_note.tool import create_note_tool
from app.agent.tools.current_time.tool import current_time_tool as what_time_is_now
from app.agent.tools.mark_reviewed.tool import mark_reviewed_tool
from app.agent.tools.note_stats.tool import note_stats_tool as get_note_stats_tool
from app.agent.tools.rag_summary.tool import rag_summary_tool as rag_summary_tools
from app.agent.tools.related_notes.tool import related_notes_tool as get_related_notes_tool
from app.agent.tools.search_notes.tool import search_notes_tool
from app.agent.tools.today_reviews.tool import today_reviews_tool as get_today_reviews_tool
from app.agent.tools.user_info.tool import user_info_tool as get_user_info_tools

__all__ = [
    "create_note_tool",
    "get_current_user_id_from_context",
    "get_note_stats_tool",
    "get_related_notes_tool",
    "get_thinking_callback_from_context",
    "get_today_reviews_tool",
    "get_user_info_tools",
    "mark_reviewed_tool",
    "rag_summary_tools",
    "search_notes_tool",
    "set_current_user_id",
    "set_thinking_callback",
    "what_time_is_now",
]

