import re
import asyncio
import aiohttp
import urllib.parse
import time
from datetime import datetime
from typing import List, Optional, Dict, Any
from napcat.message_types import MessageSegment
from utils.notebook import notebook, DEFAULT_ROLE_KEY
from utils.files import load_conversation_history
from utils.music_handler import fetch_music_data
from utils.emoji_storage import emoji_storage
import utils.role_manager as role_manager


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
      - [note:内容] 或 [note:内容:context]：静默记录笔记（不会发送任何消息）
        如果带有:context参数，会自动保存最近5条对话作为上下文
      - [note:笔记ID:delete]：删除指定ID的笔记
      - [poke:QQ号]：群聊中戳一戳某人（仅限群聊）
      - [emoji:表情包ID]：发送表情包
      - [setrole:角色]：设置角色
    其余内容作为text消息段。
    """
    print(f"[Debug] AI Parser: Received raw text: {text}")
    
    # 如果消息只包含[reply]标记，直接返回空列表
    if text.strip() == "[reply]":
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
        r"|(?P<setrole>\[setrole\s*:\s*(?P<setrole_target>[^\]]+?)\s*\])",
        re.DOTALL
    )

    def clean_matched_group(group: Optional[str]) -> Optional[str]:
        """清理匹配组的文本，移除多余空格"""
        if group is None:
            return None
        return re.sub(r'\s+', ' ', group.strip())

    # 1) 先处理静默标记（note, setrole）
    silent_tags_processed = False
    # 在循环外获取一次当前角色，避免重复查询
    current_role_name = None
    # 直接使用导入的常量 DEFAULT_ROLE_KEY
    role_key_for_notes = DEFAULT_ROLE_KEY
    if chat_id and chat_type:
        current_role_name = role_manager.get_active_role(chat_id, chat_type)
        if current_role_name:
            role_key_for_notes = current_role_name # 如果有激活角色，使用角色名作为key
        print(f"[Debug] Current role for notes in chat ({chat_id}, {chat_type}): {role_key_for_notes}")
        
    for m in pattern.finditer(text):
        if m.group("note"):
            note_content = clean_matched_group(m.group("note_content"))
            note_action = clean_matched_group(m.group("note_action"))
            
            # 如果 chat_id 或 chat_type 不存在，无法确定角色，强制使用全局笔记
            if not chat_id or not chat_type:
                # 直接使用导入的常量 DEFAULT_ROLE_KEY
                current_role_key = DEFAULT_ROLE_KEY
                print(f"[Warning] chat_id or chat_type missing, forcing notes to {current_role_key}")
            else:
                 current_role_key = role_key_for_notes # 使用循环外获取的角色key

            if note_content:
                if note_action == "delete":
                    try:
                        note_id = int(note_content)
                        if notebook.delete_note(note_id, role=current_role_key):
                            print(f"[Debug] Note deleted for role '{current_role_key}': ID {note_id}")
                        else:
                            print(f"[Debug] Failed to delete note for role '{current_role_key}': ID {note_id} not found")
                    except ValueError:
                        print(f"[Debug] Invalid note ID for deletion: {note_content}")
                else:
                    new_note_id = notebook.add_note(note_content, role=current_role_key)
                    if new_note_id != -1:
                        print(f"[Debug] Note added for role '{current_role_key}': {note_content} with ID {new_note_id}")
                    else:
                        print(f"[Error] Failed to add note for role '{current_role_key}'")
                        
            silent_tags_processed = True
        elif m.group("setrole"):
            target_role = clean_matched_group(m.group("setrole_target"))
            if target_role and chat_id and chat_type: 
                print(f"[DEBUG] AI requested role change via tag: [setrole:{target_role}] for chat {chat_id} ({chat_type})")
                role_to_set = target_role if target_role.lower() != "default" else None
                role_manager.set_active_role(chat_id, chat_type, role_to_set)
                # 更新当前循环后续可能用到的 role_key_for_notes 
                # 直接使用导入的常量 DEFAULT_ROLE_KEY
                role_key_for_notes = role_to_set if role_to_set else DEFAULT_ROLE_KEY
            silent_tags_processed = True

    # 2) 移除所有静默标记 (note, setrole)
    cleaned_text = pattern.sub(
        lambda m: "" if m.group("note") or m.group("setrole") else m.group(0),
        text
    )
    if silent_tags_processed:
        print(f"[Debug] Cleaned text after removing silent tags: {cleaned_text}")

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
                    segments_placeholders.append({
                        "type": "text", "data": {"text": seg_text}
                    })

            if m.group("at1") or m.group("at2"):
                qq = m.group("at_qq1") or m.group("at_qq2")
                segments_placeholders.append({
                    "type": "at", "data": {"qq": qq}
                })
            elif m.group("music"):
                query = clean_matched_group(m.group("music_query"))
                if query:
                    placeholder_index = len(segments_placeholders)
                    segments_placeholders.append(None)
                    task_index = len(music_tasks)
                    music_tasks.append(fetch_music_data(session, query))
                    music_indices[task_index] = placeholder_index
                else:
                    segments_placeholders.append({
                        "type": "text", "data": {"text": "[music:] 标签内容为空"}
                    })
            elif m.group("poke"):
                if chat_type != "group":
                    segments_placeholders.append({
                        "type": "text", "data": {"text": "[poke] 标签仅支持在群聊中使用"}
                    })
                else:
                    segments_placeholders.append({
                        "type": "poke", "data": {"qq": m.group("poke_qq")}
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
                    print(f"[Debug] 音乐任务异常: {result}")
                    segments_placeholders[placeholder_index] = {
                        "type": "text",
                        "data": {"text": "处理音乐请求时发生内部错误，请上报管理员喵"}
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
