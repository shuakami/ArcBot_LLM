import re
import asyncio
import aiohttp
from typing import List, Optional, Tuple, Dict, Any

from adapters.napcat.message_types import MessageSegment
from storage.notebook import notebook, DEFAULT_ROLE_KEY
from handlers.music_handler import fetch_music_data
from storage.emoji_storage import emoji_storage
import core.role_manager as role_manager
import core.event_manager as event_manager
from logger import log

# --- 预编译的正则表达式 ---

# 匹配所有静默标记，用于第一轮清理
SILENT_TAG_PATTERN = re.compile(
    r"\[(note|setrole|event|event_end|get_context):.*?\]", re.DOTALL
)

# 匹配所有可见的功能标记
VISIBLE_TAG_PATTERN = re.compile(
    r"\[(reply|@qq|CQ:at|music|poke|emoji|longtext):.*?\]", re.DOTALL
)

# --- 辅助函数 ---

def _clean_tag_content(content: Optional[str]) -> str:
    """清理标签内容中的多余空白。"""
    if content is None:
        return ""
    return re.sub(r'\s+', ' ', content.strip())

# --- 核心解析逻辑 ---

async def parse_ai_message_to_segments(
    text: str,
    message_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    chat_type: str = "private",
    active_role_name: Optional[str] = None,
    session: Optional[aiohttp.ClientSession] = None,
    self_id: Optional[str] = None
) -> List[MessageSegment]:
    """
    解析AI输出，将结构化标记转为MessageSegment。
    """
    log.debug(f"AI_Parser: 开始解析AI消息, 传入 active_role_name='{active_role_name}'")
    log.debug(f"AI_Parser: 原始文本: \"{text}\"")

    if not chat_id:
        log.warning("AI_Parser: chat_id 缺失, 部分功能将禁用。")
        return [{"type": "text", "data": {"text": text}}] if text else []

    # 步骤 1: 处理静默标记
    cleaned_text = await _handle_silent_tags(text, chat_id, chat_type, active_role_name, self_id)

    if not cleaned_text.strip():
        log.debug("AI_Parser: 清理静默标记后文本为空，解析结束。")
        return []

    # 步骤 2: 解析可见标记
    segments = await _parse_visible_tags(
        cleaned_text, message_id, chat_id, chat_type, session
    )
    log.debug(f"AI_Parser: 解析完成, 生成 {len(segments)} 个消息段。")
    return segments


async def _handle_silent_tags(text: str, chat_id: str, chat_type: str, active_role_name: Optional[str], self_id: Optional[str] = None) -> str:
    """
    查找并处理所有静默标记，返回一个移除了这些标记的干净文本。
    """
    # 优先使用传入的角色名，如果未传入，则回退到从 role_manager 获取
    role_for_processing = active_role_name or role_manager.get_active_role(chat_id, chat_type) or DEFAULT_ROLE_KEY
    log.debug(f"AI_Parser: _handle_silent_tags 使用的角色是: '{role_for_processing}'")

    for m in SILENT_TAG_PATTERN.finditer(text):
        full_tag = m.group(0)
        log.debug(f"AI_Parser: 发现静默标记: {full_tag}")
        try:
            tag_type, content = full_tag[1:-1].split(":", 1)
            
            if tag_type == "note":
                if ":" in content and content.endswith(":delete"):
                    note_id_str = content.rsplit(":", 1)[0]
                    notebook.delete_note(int(note_id_str), role=role_for_processing)
                    log.info(f"AI_Parser: 已为角色 '{role_for_processing}' 删除笔记 ID {note_id_str}。")
                else:
                    note_id = notebook.add_note(content, role=role_for_processing)
                    log.info(f"AI_Parser: 已为角色 '{role_for_processing}' 添加笔记，ID {note_id}。")

            elif tag_type == "setrole":
                new_role = content if content.lower() != "default" else None
                log.info(f"AI_Parser: 检测到角色切换指令，准备将 chat {chat_id} 的角色设置为 '{new_role}'。")
                role_manager.set_active_role(chat_id, chat_type, new_role)
                log.info(f"AI_Parser: 已将 chat {chat_id} 的激活角色设置为 '{new_role}'。")
            
            elif tag_type == "event":
                parts = content.split(":", 2)
                if len(parts) == 3:
                    evt_type, participants_str, prompt = parts
                    participants = [p.strip() for p in participants_str.split(',') if p.strip()]
                    event_manager.register_event(evt_type, participants, prompt, chat_id, chat_type)
                    log.info(f"Registered event '{evt_type}' for participants {participants}.")

            elif tag_type == "event_end":
                event_manager.remove_event(content)
                log.info(f"Removed event with ID '{content}'.")
            
            elif tag_type == "get_context":
                # get_context 工具调用已在 llm.py 中处理，这里只需要移除标记
                log.debug(f"AI_Parser: 发现 get_context 标记，已在LLM层处理: {content}")

        except Exception as e:
            log.error(f"Error processing silent tag '{full_tag}': {e}", exc_info=True)

    cleaned_text = SILENT_TAG_PATTERN.sub("", text).strip()
    if len(cleaned_text) < len(text):
        log.debug(f"AI_Parser: 移除静默标记后的文本: \"{cleaned_text}\"")
    return cleaned_text


async def _parse_visible_tags(
    text: str,
    message_id: Optional[str],
    chat_id: str,
    chat_type: str,
    session: Optional[aiohttp.ClientSession]
) -> List[MessageSegment]:
    """
    解析文本中的所有可见标记，并返回最终的消息段列表。
    """
    # 提前处理 [reply] 标记
    reply_match = re.search(r"\[reply(?:\s*:\s*(\d+))?\]", text)
    should_reply = bool(reply_match)
    # 如果 [reply] 标签中指定了 ID，则使用它；否则，使用传入的 message_id
    reply_to_id = reply_match.group(1) if reply_match and reply_match.group(1) else message_id
    text = re.sub(r"\[reply(?:\s*:\s*\d+)?\]", "", text) # 移除 reply 标签

    segments_placeholders: List[Optional[MessageSegment]] = []
    music_tasks = []
    music_indices: Dict[int, int] = {}
    last_idx = 0

    session_manager = session if session else aiohttp.ClientSession()
    
    try:
        for i, m in enumerate(VISIBLE_TAG_PATTERN.finditer(text)):
            if m.start() > last_idx:
                segments_placeholders.append({"type": "text", "data": {"text": text[last_idx:m.start()]}})

            tag_full = m.group(0)
            # 使用更安全的分割方式
            parts = tag_full[1:-1].split(":", 1)
            tag_type = parts[0]
            content = parts[1] if len(parts) > 1 else ""
            
            if tag_type == "reply": # 跳过已处理的 reply 标签
                continue

            if tag_type in ("@qq", "CQ:at,qq="):
                qq = re.search(r'\d+', content).group(0)
                segments_placeholders.append({"type": "at", "data": {"qq": qq}})
            
            elif tag_type == "poke":
                qq = re.search(r'\d+', content).group(0)
                segments_placeholders.append({"type": "poke", "data": {"qq": qq}})
                
            elif tag_type == "emoji":
                emoji_id = _clean_tag_content(content)
                emoji = emoji_storage.find_emoji_by_id(emoji_id)
                if emoji:
                    segments_placeholders.append({"type": "image", "data": {"file": emoji["file"], "url": emoji["url"]}})
                else:
                    segments_placeholders.append({"type": "text", "data": {"text": f"[emoji not found: {emoji_id}]"}})

            elif tag_type == "music":
                query = _clean_tag_content(content)
                placeholder_idx = len(segments_placeholders)
                segments_placeholders.append(None) # 占位
                task_idx = len(music_tasks)
                music_tasks.append(fetch_music_data(session_manager, query))
                music_indices[task_idx] = placeholder_idx

            elif tag_type == "longtext":
                # 直接提取内容，保留换行符
                long_text_content = content 
                segments_placeholders.append({"type": "text", "data": {"text": long_text_content}})


            last_idx = m.end()

        if last_idx < len(text):
            segments_placeholders.append({"type": "text", "data": {"text": text[last_idx:]}})

        if music_tasks:
            music_results = await asyncio.gather(*music_tasks, return_exceptions=True)
            for idx, result in enumerate(music_results):
                placeholder_idx = music_indices[idx]
                if isinstance(result, Exception):
                    log.error(f"Music task failed: {result}")
                    segments_placeholders[placeholder_idx] = {"type": "text", "data": {"text": "[Music search failed]"}}
                else:
                    segments_placeholders[placeholder_idx] = result
    finally:
        if not session:
            await session_manager.close()

    final_segments = [seg for seg in segments_placeholders if seg and seg.get("data", {}).get("text", True)]

    processed_segments: List[MessageSegment] = []
    for i, seg in enumerate(final_segments):
        processed_segments.append(seg)
        if seg["type"] == "at" and i + 1 < len(final_segments) and final_segments[i+1]["type"] == "text":
            next_text_seg = final_segments[i+1]["data"]
            if not next_text_seg.get("text", "").startswith(" "):
                next_text_seg["text"] = " " + next_text_seg.get("text", "")
    
    if should_reply and reply_to_id:
        processed_segments.insert(0, {"type": "reply", "data": {"id": str(reply_to_id)}})
        
    return processed_segments
