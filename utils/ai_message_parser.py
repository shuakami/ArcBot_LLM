import re
import asyncio
import aiohttp
import urllib.parse
import time
from datetime import datetime
from typing import List, Optional, Dict, Any
from napcat.message_types import MessageSegment
from utils.notebook import notebook, DEFAULT_ROLE_KEY
from utils.files import load_conversation_history # Not used directly, consider removal if not planned.
from utils.music_handler import fetch_music_data
from utils.emoji_storage import emoji_storage
import utils.role_manager as role_manager
import utils.event_manager as event_manager
import re # Ensure re is imported for validation helpers
from logger import get_logger # Import the new logger

# --- Validation Constants ---
QQ_REGEX_PATTERN = r"^[1-9][0-9]{4,14}$" # QQ号码正则: 5-15位，首位不为0
MAX_EVENT_TYPE_LENGTH = 50
MAX_EVENT_PARTICIPANTS = 10
MAX_EVENT_PROMPT_LENGTH = 2000
MAX_MUSIC_QUERY_LENGTH = 100
MAX_ROLE_NAME_LENGTH = 50 # 与 role_manager.py 中的 MAX_ROLE_NAME_LENGTH (如果存在) 或一个合理值对应

# --- Validation Helper Functions ---
def is_valid_qq(qq_str: str) -> bool:
    """Checks if the given string is a valid QQ number."""
    if not qq_str:
        return False
    return bool(re.fullmatch(QQ_REGEX_PATTERN, qq_str))

async def parse_ai_message_to_segments(
    text: str,
    current_msg_id: Optional[int] = None,
    chat_id: Optional[str] = None,
    chat_type: str = "private"
) -> List[MessageSegment]:
    """
    解析AI输出，将结构化标记转为MessageSegment。
    支持：
      - [reply] 或 [reply:消息ID]：回复消息
      - [@qq:QQ号] 或 [CQ:at,qq=QQ号]：@某人
      - [music:歌曲名] 或 [music:歌曲名-歌手]：自动搜索并发送音乐卡片 (并行处理)
      - [note:内容]：静默记录笔记。内容参数会作为笔记的完整内容被记录。
        (注意: 旧格式中提及的 [note:内容:context] 中的 :context 部分，实际并未作为独立参数处理，而是成为笔记内容的一部分。)
      - [note:笔记ID:delete]：删除指定ID的笔记。
      - [poke:QQ号]：群聊中戳一戳某人（仅限群聊）
      - [emoji:表情包ID]：发送表情包
      - [setrole:角色]：设置角色
      - [event:事件类型:参与者QQ号列表:事件Prompt内容]：触发事件
      - [event_end:事件ID]：结束事件 (暂时取消这个，主要依赖超时)
    其余内容作为text消息段。
    """
    logger = get_logger(__name__) # Get logger instance
    logger.debug(f"AI Parser: Received raw text: {text[:200]}...") # Log only beginning of long texts
    
    # 如果消息只包含[reply]标记，直接返回空列表
    if text.strip() == "[reply]":
        logger.debug("Received [reply] only tag, returning empty segments.")
        return []
        
    segments_placeholders: List[Optional[MessageSegment]] = []
    pattern = re.compile(
        r"(?P<reply>\[reply(?:\s*:\s*(?P<reply_id>\d+))?\])"
        r"|(?P<at1>\[@qq\s*:\s*(?P<at_qq1>\d+)\])"
        r"|(?P<at2>\[CQ:at,qq=(?P<at_qq2>\d+)\])"
        r"|(?P<music>\[music\s*:\s*(?P<music_query>[^\]]+?)\s*\])"
        r"|(?P<note>\[note\s*:\s*(?P<note_content>.*?)(?:\\s*:\\s*(?P<note_action>delete))?\\s*\])"
        r"|(?P<poke>\[poke\s*:\s*(?P<poke_qq>\d+)\])"
        r"|(?P<emoji>\[emoji\s*:\s*(?P<emoji_id>[^\]]+?)\s*\])"
        r"|(?P<setrole>\[setrole\s*:\s*(?P<setrole_target>[^\]]+?)\s*\])"
        r"|(?P<event>\[event\s*:\s*(?P<event_type>[^:]+?)\s*:\s*(?P<participants>[^:]*?)\s*:\s*(?P<event_prompt>.*?)\s*\\])"
        r"|(?P<event_end>\[event_end\s*:\s*(?P<event_end_id>[^\]]+?)\])",
        re.DOTALL
    )

    def clean_matched_group(group: Optional[str]) -> Optional[str]:
        """清理匹配组的文本，移除多余空格"""
        if group is None:
            return None
        return re.sub(r'\s+', ' ', group.strip())

    # 1) 先处理静默标记（note, setrole, event, event_end）
    silent_tags_processed = False
    # 在循环外获取一次当前角色，避免重复查询
    current_role_name = None
    # 直接使用导入的常量 DEFAULT_ROLE_KEY
    role_key_for_notes = DEFAULT_ROLE_KEY
    if chat_id and chat_type:
        current_role_name = role_manager.get_active_role(chat_id, chat_type)
        if current_role_name:
            role_key_for_notes = current_role_name # 如果有激活角色，使用角色名作为key
        logger.debug(f"Current role for notes in chat ({chat_id}, {chat_type}): {role_key_for_notes}")
        
    for m in pattern.finditer(text):
        if m.group("note"):
            note_content = clean_matched_group(m.group("note_content"))
            note_action = clean_matched_group(m.group("note_action"))
            
            current_role_key_for_this_note = role_key_for_notes # Default to pre-fetched
            if not chat_id or not chat_type: # Should not happen if called from chat_logic normally
                current_role_key_for_this_note = DEFAULT_ROLE_KEY
                logger.warning(f"chat_id or chat_type missing for [note] tag, forcing notes to {current_role_key_for_this_note}. Original tag: {m.group(0)}")
            
            if note_content:
                if note_action == "delete":
                    try:
                        note_id = int(note_content)
                        if notebook.delete_note(note_id, role=current_role_key_for_this_note): # notebook methods use print, will need update
                            logger.debug(f"Note deleted for role '{current_role_key_for_this_note}': ID {note_id}")
                        else:
                            logger.warning(f"Failed to delete note for role '{current_role_key_for_this_note}': ID {note_id} not found or error in delete_note.")
                    except ValueError:
                        logger.warning(f"Invalid note ID for deletion: {note_content}. Original tag: {m.group(0)}")
                else:
                    # notebook.add_note uses print, will need update. It also does its own length validation.
                    new_note_id = notebook.add_note(note_content, role=current_role_key_for_this_note) 
                    if new_note_id != -1:
                        logger.debug(f"Note added for role '{current_role_key_for_this_note}': '{note_content[:50]}...' with ID {new_note_id}")
                    else:
                        logger.error(f"Failed to add note for role '{current_role_key_for_this_note}'. Content: '{note_content[:50]}...'. Original tag: {m.group(0)}")
            silent_tags_processed = True
        elif m.group("setrole"):
            original_tag_text = m.group(0)
            target_role = clean_matched_group(m.group("setrole_target"))
            validation_error_msg = None

            if not target_role:
                validation_error_msg = "[角色名称不能为空]"
            elif len(target_role) > MAX_ROLE_NAME_LENGTH:
                validation_error_msg = f"[角色名称过长，最大长度: {MAX_ROLE_NAME_LENGTH}]"
            
            if validation_error_msg:
                logger.warning(f"Invalid setrole tag: {validation_error_msg}. Original: {original_tag_text} for chat {chat_id} ({chat_type}).")
                text = text.replace(original_tag_text, validation_error_msg, 1)
            elif chat_id and chat_type:
                logger.debug(f"AI requested role change via tag: [setrole:{target_role}] for chat {chat_id} ({chat_type})")
                role_to_set = target_role if target_role.lower() != "default" else None
                if role_manager.set_active_role(chat_id, chat_type, role_to_set): # role_manager uses print, will need update
                    role_key_for_notes = role_to_set if role_to_set else DEFAULT_ROLE_KEY # Update for subsequent notes in same AI msg
                    logger.info(f"Role successfully set to '{role_key_for_notes}' for chat {chat_id} ({chat_type}).")
                else:
                    logger.warning(f"Failed to set role '{target_role}' via role_manager for chat {chat_id} ({chat_type}). Role might not exist. Tag: {original_tag_text}")
                    text = text.replace(original_tag_text, f"[设置角色 '{target_role}' 失败，角色可能不存在或设置出错]", 1)
            silent_tags_processed = True
        elif m.group("event"):
            original_tag_text = m.group(0)
            event_type = clean_matched_group(m.group("event_type"))
            participants_str = clean_matched_group(m.group("participants"))
            event_prompt = clean_matched_group(m.group("event_prompt"))
            event_error_reason = None

            if not event_type:  event_error_reason = "事件类型为空"
            elif len(event_type) > MAX_EVENT_TYPE_LENGTH: event_error_reason = f"事件类型过长 (最大 {MAX_EVENT_TYPE_LENGTH} 字符)"
            elif not event_prompt: event_error_reason = "事件 Prompt 为空"
            elif len(event_prompt) > MAX_EVENT_PROMPT_LENGTH: event_error_reason = f"事件 Prompt 过长 (最大 {MAX_EVENT_PROMPT_LENGTH} 字符)"
            
            parsed_participants = []
            if not event_error_reason:
                if participants_str:
                    temp_participants = [p.strip() for p in participants_str.split(',') if p.strip()]
                    if len(temp_participants) > MAX_EVENT_PARTICIPANTS: event_error_reason = f"参与者数量过多 (最大 {MAX_EVENT_PARTICIPANTS} 人)"
                    else:
                        for p_qq in temp_participants:
                            if not is_valid_qq(p_qq):
                                event_error_reason = f"参与者QQ号 '{p_qq}' 格式无效"; break
                        if not event_error_reason: parsed_participants = temp_participants
                
                if not event_error_reason and not parsed_participants:
                    if chat_type == "private" and chat_id and is_valid_qq(chat_id):
                        parsed_participants = [chat_id]
                        logger.debug(f"私聊事件，自动将当前用户 {chat_id} 作为参与者。Event: {event_type}")
                    elif chat_type == "group":
                        logger.debug(f"群聊事件 '{event_type}' 未指定有效参与者。将由event_manager决定如何处理。")

            if event_error_reason:
                logger.warning(f"无效的事件触发标记: {event_error_reason}. 原标记: {original_tag_text}")
                text = text.replace(original_tag_text, f"[事件指令参数错误: {event_error_reason}]", 1)
            elif chat_id and chat_type:
                # event_manager uses print, will need update
                registered_event_id = event_manager.register_event(event_type, parsed_participants, event_prompt, chat_id, chat_type)
                if registered_event_id:
                    logger.info(f"已触发并注册事件: ID {registered_event_id}, Type {event_type}, Participants {parsed_participants}, Chat {chat_id} ({chat_type})")
                else:
                    logger.warning(f"事件注册失败 (可能已有同聊天/参与者的活动事件或内部错误). 原标记: {original_tag_text}")
                    text = text.replace(original_tag_text, "[事件注册失败，请检查日志或联系管理员]", 1)
            else: 
                logger.warning(f"接收到事件触发标记但缺乏 chat_id 或 chat_type，无法注册事件: {original_tag_text}")
                text = text.replace(original_tag_text, "[事件指令错误: 缺少必要的会话信息]", 1)
            silent_tags_processed = True
        elif m.group("event_end"):
            event_id_to_remove = clean_matched_group(m.group("event_end_id"))
            if event_id_to_remove:
                # event_manager uses print, will need update
                if event_manager.remove_event(event_id_to_remove):
                    logger.info(f"已通过标记结束事件: ID {event_id_to_remove}")
                else:
                    logger.warning(f"尝试通过标记结束不存在或无法移除的事件: ID {event_id_to_remove}. Tag: {m.group(0)}")
            else:
                logger.warning(f"接收到无效的事件结束标记，事件 ID 为空: {m.group(0)}")
            silent_tags_processed = True

    # 2) 移除所有 *成功处理的* 或 *不需要反馈错误的* 静默标记 
    # Note: Tags that failed validation and were replaced by error messages should NOT be removed here.
    # The current lambda removes based on original tag type, which is fine as failed ones are now different text.
    cleaned_text = pattern.sub(
        lambda m_sub: "" if m_sub.group("note") or \
                             (m_sub.group("setrole") and validation_error_msg is None and not text.startswith("[设置角色", m_sub.start())) or \
                             (m_sub.group("event") and event_error_reason is None and not text.startswith("[事件指令参数错误", m_sub.start()) and not text.startswith("[事件注册失败", m_sub.start())) or \
                             m_sub.group("event_end") \
                      else m_sub.group(0),
        text 
    )
    # Simpler lambda might be: (if tag was replaced, it won't match original pattern group anymore)
    # cleaned_text = pattern.sub(lambda m_sub: "" if m_sub.group("note") or m_sub.group("setrole") or m_sub.group("event") or m_sub.group("event_end") else m_sub.group(0), text)

    if silent_tags_processed: # This log might be confusing if text was modified with error messages.
        logger.debug(f"Text after attempting to process/remove silent tags: {cleaned_text[:200]}...")


    # 3) 查找并移除第一个 reply 标记
    should_reply = False
    reply_id = None
    reply_match = re.search(r"\[reply(?:\s*:\s*(\d+))?\]", cleaned_text)
    if reply_match:
        should_reply = True
        reply_id = reply_match.group(1)
        cleaned_text = re.sub(r"\[reply(?:\s*:\s*\d+)?\]", "", cleaned_text)

    # 4) 处理剩余标签（at、music、poke、emoji）并构建段
    matches = list(pattern.finditer(cleaned_text))
    last_idx = 0
    music_tasks = []
    music_indices = {}

    async with aiohttp.ClientSession() as session:
        for i, m in enumerate(matches):
            if m.start() > last_idx:
                seg_text = cleaned_text[last_idx:m.start()].strip()
                if seg_text:
                    logger.debug(f"Found text segment: '{seg_text[:100]}...'")
                    segments_placeholders.append({
                        "type": "text", "data": {"text": seg_text}
                    })

            if m.group("at1") or m.group("at2"):
                qq_at = m.group("at_qq1") or m.group("at_qq2")
                if is_valid_qq(qq_at):
                    logger.debug(f"Found @qq tag: {qq_at}")
                    segments_placeholders.append({
                        "type": "at", "data": {"qq": qq_at}
                    })
                else:
                    logger.warning(f"Invalid QQ in @ tag: {qq_at}. Original tag: {m.group(0)}")
                    segments_placeholders.append({
                        "type": "text", "data": {"text": f"[at指令QQ号 {qq_at} 格式错误]"}
                    })
            elif m.group("music"):
                query = clean_matched_group(m.group("music_query"))
                if not query:
                    logger.warning(f"Music tag with empty query. Original tag: {m.group(0)}")
                    segments_placeholders.append({
                        "type": "text", "data": {"text": "[music指令内容为空]"}
                    })
                elif len(query) > MAX_MUSIC_QUERY_LENGTH:
                    logger.warning(f"Music query too long: '{query[:100]}...'. Max length {MAX_MUSIC_QUERY_LENGTH}. Original tag: {m.group(0)}")
                    segments_placeholders.append({
                        "type": "text", "data": {"text": f"[音乐搜索内容过长，最大长度: {MAX_MUSIC_QUERY_LENGTH}]"}
                    })
                else:
                    logger.debug(f"Found music tag, query: {query}")
                    placeholder_index = len(segments_placeholders)
                    segments_placeholders.append(None) 
                    task_index = len(music_tasks)
                    music_tasks.append(fetch_music_data(session, query)) # fetch_music_data should handle its own logging
                    music_indices[task_index] = placeholder_index
            elif m.group("poke"):
                poke_qq_str = clean_matched_group(m.group("poke_qq"))
                if chat_type != "group":
                    logger.warning(f"Poke tag used outside group chat. Original tag: {m.group(0)}")
                    segments_placeholders.append({
                        "type": "text", "data": {"text": "[poke指令仅支持在群聊中使用]"}
                    })
                elif not is_valid_qq(poke_qq_str):
                    logger.warning(f"Invalid QQ for poke: {poke_qq_str}. Original tag: {m.group(0)}")
                    segments_placeholders.append({
                        "type": "text", "data": {"text": f"[poke指令QQ号 {poke_qq_str} 格式错误]"}
                    })
                else:
                    logger.debug(f"Found poke tag, QQ: {poke_qq_str}")
                    segments_placeholders.append({
                        "type": "poke", "data": {"qq": poke_qq_str}
                    })
            elif m.group("emoji"):
                emoji_id = clean_matched_group(m.group("emoji_id"))
                if emoji_id:
                    emoji = emoji_storage.find_emoji_by_id(emoji_id)
                    if emoji:
                        segments_placeholders.append({
                            "type": "image",
                            "data": {
                                "file": emoji["file"],
                                "url": emoji["url"],
                                "emoji_id": emoji["emoji_id"],
                                "emoji_package_id": emoji["emoji_package_id"]
                            }
                        })
                    else:
                        segments_placeholders.append({
                            "type": "text",
                            "data": {"text": f"[未找到该表情包喵: {emoji_id}]"}
                        })
                else:
                    segments_placeholders.append({
                        "type": "text",
                        "data": {"text": "[emoji:] 标签内容为空喵"}
                    })

            last_idx = m.end()

        # 收尾的文本
        if last_idx < len(cleaned_text):
            seg_text = cleaned_text[last_idx:].strip()
            if seg_text:
                segments_placeholders.append({
                    "type": "text", "data": {"text": seg_text}
                })

        # 并行执行音乐查询
        if music_tasks:
            music_results = await asyncio.gather(*music_tasks, return_exceptions=True)
            for idx, result in enumerate(music_results):
                placeholder_index = music_indices[idx]
                if isinstance(result, Exception):
                    logger.error(f"Music task (index {idx}) failed with exception: {result}", exc_info=True)
                    segments_placeholders[placeholder_index] = {
                        "type": "text",
                        "data": {"text": "[音乐处理时发生内部错误，已通知管理员]"}
                    }
                else:
                    segments_placeholders[placeholder_index] = result

    # 过滤掉 None
    final_segments: List[MessageSegment] = [
        seg for seg in segments_placeholders if seg is not None
    ]
    
    # 5) 如果需要回复，插入 reply 段
    if final_segments and should_reply:
        reply_data: Dict[str, Any] = {}
        if reply_id:
            reply_data["id"] = int(reply_id)
        elif current_msg_id is not None:
            reply_data["id"] = current_msg_id
        final_segments.insert(0, {"type": "reply", "data": reply_data})

    return final_segments
