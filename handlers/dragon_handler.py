import time
import random
import asyncio
from collections import deque
from typing import Dict

from llm import process_conversation
from utils.ai_message_parser import parse_ai_message_to_segments
from napcat.message_sender import IMessageSender

# 存储每个群组最近消息历史 (group_id -> deque of (user_id, text_content))
group_message_history: Dict[str, deque] = {}
DRAGON_HISTORY_LENGTH = 5 # 存储最近5条消息用于检测

def update_message_history(group_id: str, user_id: str, text_content: str):
    """更新指定群组的消息历史记录"""
    if group_id not in group_message_history:
        group_message_history[group_id] = deque(maxlen=DRAGON_HISTORY_LENGTH)
    # 只记录非空文本消息
    if text_content:
        group_message_history[group_id].append((user_id, text_content))

async def handle_dragon_logic(group_id: str, self_id: str, sender: IMessageSender) -> bool:
    """
    检查并处理群聊中的接龙行为。完全处理接龙情况（+1 或 AI 打乱）。
    返回 True 表示已处理接龙，False 表示未检测到或未处理。
    """
    if group_id not in group_message_history:
        return False

    history = group_message_history[group_id]
    if len(history) < 3:
        return False # 消息不足三条，无法判断接龙

    # 获取最后三条消息
    last_user_id, last_text = history[-1]
    prev_user_id, prev_text = history[-2]
    prev_prev_user_id, prev_prev_text = history[-3]

    # 接龙条件判断 (确保内容非空)
    is_dragon = (
        last_text == prev_text and last_text == prev_prev_text and # 内容相同
        last_text and
        last_user_id != prev_user_id and last_user_id != prev_prev_user_id and prev_user_id != prev_prev_user_id and # 三个发送者都不同
        last_user_id != self_id and
        prev_user_id != self_id and
        prev_prev_user_id != self_id # 三个发送者都不是机器人
    )

    if is_dragon:
        print(f"[DEBUG] 检测到群 {group_id} 接龙: '{last_text}' by {prev_user_id} -> {last_user_id}")
        # 50%概率接龙，50%概率打乱
        if random.random() < 0.5:
            # --- 方式 A: 直接接龙 (+1) ---
            try:
                print(f"[DEBUG] 机器人决定接龙: +1 '{last_text}'")
                dragon_segment = [{"type": "text", "data": {"text": last_text}}]
                sender.send_group_msg(int(group_id), dragon_segment)
                # 更新历史记录机器人接龙
                update_message_history(group_id, self_id, last_text)
                return True # 已处理
            except Exception as e:
                print(f"[ERROR] 机器人接龙失败: {e}")
                return False # 未处理
        else:
            # --- 方式 B: 调用 AI 打乱接龙 ---
            try:
                print(f"[DEBUG] 机器人决定调用 AI 打乱接龙: '{last_text}'")
                disrupt_prompt = f'群里现在好多人在复读刷屏这条消息："{last_text}"。请你回复一句与众不同或者看似接龙但是有错别字的话，来打断或者终结这个无聊的刷屏行为。'

                # 直接在此处处理 AI 调用和发送
                message_id = str(int(time.time()))
                for segment_text in process_conversation(group_id, disrupt_prompt, chat_type="group"):
                    try:
                        print(f"[DEBUG] AI 打乱回复片段: {segment_text}")
                        msg_segments = await parse_ai_message_to_segments(
                            segment_text,
                            message_id,
                            chat_id=group_id,
                            chat_type="group"
                        )
                        if msg_segments:
                            sender.send_group_msg(int(group_id), msg_segments)
                            await asyncio.sleep(random.uniform(0.5, 1.5)) # 短暂延迟
                    except Exception as parse_err:
                        print(f"[ERROR] 解析 AI 打乱回复时出错: {parse_err}")
                        continue
                return True # AI 打乱流程完成（无论是否成功发送）
            except Exception as ai_err:
                print(f"[ERROR] 调用 AI 打乱接龙时出错: {ai_err}")
                return False # AI 处理失败

    return False # 未检测到接龙 