import time
import random
import asyncio
from collections import deque
from typing import Dict

from llm import process_conversation
from messaging.ai_parser import parse_ai_message_to_segments
from adapters.napcat.message_sender import IMessageSender
from logger import log

# 存储每个群组最近消息历史
group_message_history: Dict[str, deque] = {}
DRAGON_HISTORY_LENGTH = 5

def update_message_history(group_id: str, user_id: str, text_content: str):
    """更新指定群组的消息历史记录"""
    if group_id not in group_message_history:
        group_message_history[group_id] = deque(maxlen=DRAGON_HISTORY_LENGTH)
    if text_content:
        group_message_history[group_id].append((user_id, text_content))

async def handle_dragon_logic(group_id: str, self_id: str, sender: IMessageSender) -> bool:
    """检查并处理群聊中的接龙行为。"""
    history = group_message_history.get(group_id)
    if not history or len(history) < 3:
        return False

    last_user_id, last_text = history[-1]
    prev_user_id, prev_text = history[-2]
    prev_prev_user_id, prev_prev_text = history[-3]

    is_dragon = (
        last_text and last_text == prev_text and last_text == prev_prev_text and
        len({last_user_id, prev_user_id, prev_prev_user_id, self_id}) == 4 # 确保四个ID都不同
    )

    if is_dragon:
        log.debug(f"检测到群 {group_id} 接龙: '{last_text}'")
        if random.random() < 0.5:
            # 方式 A: 直接接龙
            try:
                log.debug(f"机器人决定接龙: +1 '{last_text}'")
                dragon_segment = [{"type": "text", "data": {"text": last_text}}]
                sender.send_group_msg(int(group_id), dragon_segment)
                update_message_history(group_id, self_id, last_text)
                return True
            except Exception as e:
                log.error(f"机器人接龙失败: {e}")
                return False
        else:
            # 方式 B: 调用 AI 打乱接龙
            try:
                log.debug(f"机器人决定调用 AI 打乱接龙: '{last_text}'")
                disrupt_prompt = f'群里现在好多人在复读刷屏这条消息："{last_text}"。请你回复一句与众不同或者看似接龙但是有错别字的话，来打断或者终结这个无聊的刷屏行为。'
                
                message_id = str(int(time.time()))
                for segment_text in process_conversation(group_id, disrupt_prompt, chat_type="group"):
                    try:
                        log.debug(f"AI 打乱回复片段: {segment_text}")
                        msg_segments = await parse_ai_message_to_segments(
                            segment_text, int(message_id), chat_id=group_id, chat_type="group"
                        )
                        if msg_segments:
                            sender.send_group_msg(int(group_id), msg_segments)
                            await asyncio.sleep(random.uniform(0.5, 1.5))
                    except Exception as parse_err:
                        log.error(f"解析 AI 打乱回复时出错: {parse_err}")
                        continue
                return True
            except Exception as ai_err:
                log.error(f"调用 AI 打乱接龙时出错: {ai_err}")
                return False
    return False
