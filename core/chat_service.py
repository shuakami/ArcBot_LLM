import asyncio
import time
from typing import List, Any, Dict
from adapters.base import AbstractAdapter
from core.event_bus import event_bus
from llm import process_conversation
from messaging.ai_parser import parse_ai_message_to_segments

from logger import log
from config import config
import core.role_manager as role_manager

def _render_message_for_ai(message_segments: List[Dict[str, Any]], self_id: str) -> str:
    """
    从消息段中渲染出供 AI 使用的纯文本内容。
    - 将指向机器人自己的 @ 信息替换为 '@你'。
    - 将指向其他人的 @ 信息替换为 '@QQ号'。
    - 拼接所有文本信息。
    """
    parts = []
    for seg in message_segments:
        if seg.get("type") == "at":
            at_qq = str(seg.get("data", {}).get("qq"))
            if at_qq == self_id:
                parts.append("@你 ")
            else:
                parts.append(f"@{at_qq} ")
        elif seg.get("type") == "text":
            text_content = seg.get("data", {}).get("text")
            if text_content:
                parts.append(text_content)
    return "".join(parts).strip()

class ChatService:
    def __init__(self, adapter: AbstractAdapter):
        self._adapter = adapter
        self._is_running = False

    def start(self):
        """订阅事件并开始监听。"""
        if not self._is_running:
            event_bus.subscribe("MessageReceivedEvent", self.handle_message_received)
            self._is_running = True
            log.info("ChatService 已启动并订阅 MessageReceivedEvent。")

    def stop(self):
        """停止服务（未来可能需要取消订阅）。"""
        self._is_running = False
        log.info("ChatService 已停止。")

    async def handle_message_received(self, event_data: dict):
        """处理接收到的消息事件。"""
        chat_type = event_data.get("chat_type")
        chat_id = event_data.get("chat_id")
        user_id = event_data.get("user_id")
        self_id = event_data.get("self_id")
        username = event_data.get("username")
        message_id = event_data.get("message_id")
        message_segments = event_data.get("message", [])
        raw_content = event_data.get("content", "")
        timestamp = event_data.get("timestamp", int(time.time()))

        content_for_ai = _render_message_for_ai(message_segments, self_id)

        if chat_type == 'group':
            is_mentioned = any(
                seg.get("type") == "at" and str(seg.get("data", {}).get("qq")) == self_id
                for seg in message_segments
            )
            
            reply_prefix = config["qqbot"].get("group_prefix", "#")
            has_prefix = raw_content.strip().startswith(reply_prefix)

            if not is_mentioned and not has_prefix:
                return
            
            if has_prefix:
                content_for_ai = raw_content.strip().lstrip(reply_prefix).strip()

        if not content_for_ai:
            log.debug(f"消息在渲染和移除前缀后内容为空，跳过AI处理。原始消息: {raw_content}")
            return
            
        log.info(f"ChatService 收到有效消息:  来自 {username}({user_id}): {raw_content}")

        active_role = role_manager.get_active_role(chat_id, chat_type)
        log.debug(f"ChatService: 获取到当前激活角色: '{active_role}'")

        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        if chat_type == 'group':
            ai_input = f"[用户:{username}({user_id})] [群:{chat_id}] [时间:{time_str}] {content_for_ai}"
        else:
            ai_input = f"[用户:{username}({user_id})] [时间:{time_str}] {content_for_ai}"
        
        log.debug(f"ChatService: 准备传入 process_conversation 的参数 - chat_id: {chat_id}, chat_type: {chat_type}, active_role_name: '{active_role}'")
        try:
            # 将 active_role 传递给 process_conversation
            for segment_text in process_conversation(chat_id, ai_input, chat_type=chat_type, active_role_name=active_role, self_id=self_id):
                log.debug(f"ChatService: 从 process_conversation 接收到 AI segment: \"{segment_text}\"")
                log.debug(f"ChatService: 准备传入 parse_ai_message_to_segments 的参数 - active_role_name: '{active_role}'")
                parsed_segments = await parse_ai_message_to_segments(
                    segment_text,
                    message_id=message_id,
                    chat_id=chat_id,
                    chat_type=chat_type,
                    active_role_name=active_role,
                    self_id=self_id
                )
                
                if parsed_segments:
                    # --- 分块发送消息 ---
                    message_batch = []
                    special_segments = ["poke", "music"]

                    for segment in parsed_segments:
                        seg_type = segment.get("type")

                        if seg_type in special_segments:
                            # 1. 发送当前批次的普通消息
                            if message_batch:
                                await self._adapter.send_message(chat_type, chat_id, message_batch)
                                message_batch = []
                                await asyncio.sleep(0.5)

                            # 2. 独立发送特殊消息
                            if seg_type == "poke":
                                poke_user_id = segment.get("data", {}).get("qq")
                                if poke_user_id:
                                    await self._adapter.send_poke(chat_type, chat_id, poke_user_id)
                            elif seg_type == "music":
                                await self._adapter.send_message(chat_type, chat_id, [segment])
                            
                            await asyncio.sleep(1)
                        else:
                            # 收集普通消息段
                            message_batch.append(segment)
                    
                    # 3. 发送最后一批普通消息
                    if message_batch:
                        await self._adapter.send_message(chat_type, chat_id, message_batch)

        except Exception as e:
            log.error(f"处理对话时发生错误 (chat_id: {chat_id}): {e}", exc_info=True)
            error_message = [{"type": "text", "data": {"text": "抱歉，处理您的请求时发生了一个内部错误。"}}]
            await self._adapter.send_message(
                chat_type=chat_type,
                target_id=chat_id,
                message=error_message
            )
