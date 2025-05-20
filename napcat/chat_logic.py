import time
import threading
import random
import re
import asyncio
from typing import List
from collections import deque

from config import CONFIG
from llm import process_conversation
from logger import get_logger # Import the new logger
# Assuming log_message is from a different logger (e.g., db_logger)
# If it's from the same logger.py and was a custom function, it might need adjustment.
# For now, assuming it's distinct. If logger.py was the DB logger, this is fine.
# If logger.py is now the new logging setup, then log_message needs to be addressed.
# Given the previous step overwrote logger.py, log_message is likely from utils.db_logger now.
from utils.db_logger import log_message 

from utils.blacklist import is_blacklisted
from utils.text import extract_text_from_message
from utils.whitelist import is_whitelisted
from napcat.message_sender import IMessageSender
from napcat.message_types import MessageSegment
from utils.message_content import parse_group_message_content
from utils.ai_message_parser import parse_ai_message_to_segments
from utils.group_activity import group_activity_manager
from . import post
from utils.dragon_handler import update_message_history, handle_dragon_logic


def check_access(sender_id, is_group=False):
    """
    根据配置的名单模式过滤消息：
      - 黑名单模式：如果目标在黑名单中，则返回 False
      - 白名单模式：如果目标不在白名单中，则返回 False
      - 其它情况返回 True
    参数 is_group 为 True 时，表示检查群聊名单，False 时为用户消息名单
    """
    logger = get_logger(__name__) # Get logger instance for this function if needed, or use module level
    mode_key = "group_list_mode" if is_group else "qq_list_mode"
    if CONFIG.get("debug", False): logger.debug(f"检查 {mode_key} 模式")
    mode = CONFIG["qqbot"].get(mode_key, "black").lower()
    if CONFIG.get("debug", False): logger.debug(f"当前模式: {mode}")
    if mode == "black":
        return not is_blacklisted(sender_id, is_group)
    elif mode == "white":
        return is_whitelisted(sender_id, is_group)
    return True

def handle_private_message(msg_dict, sender: IMessageSender):
    """
    处理私聊消息：
      - 记录消息日志
      - 异步生成回复，达到流式发送的效果
    """
    logger = get_logger(__name__) # Get logger instance
    try:
        sender_info = msg_dict["sender"]
        user_id = str(sender_info["user_id"])
        if CONFIG.get("debug", False): logger.debug(f"收到私聊消息: {user_id} - {sender_info.get('nickname', '')}")

        # 检查是否允许处理该消息
        if not check_access(user_id): # check_access now uses logging internally for its debugs
            return

        username = sender_info.get("nickname", "")
        message_id = str(msg_dict.get("message_id", ""))
        content = extract_text_from_message(msg_dict)
        timestamp = msg_dict.get("time", int(time.time()))
        # 格式化时间戳前缀
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        content_with_time = f"[用户:{username}(QQ号：{user_id})] [时间:{time_str}] {content}"

        # 记录消息日志 (log_message is assumed to be the DB logger)
        log_message(user_id, username, message_id, content_with_time, timestamp)
        logger.info(f"Q: {username}[{user_id}] | MsgId: {message_id} | TS: {timestamp} | Content: {content_with_time}")

        # 异步处理回复消息，实现流式发送效果
        async def process_and_send():
            logger_async = get_logger(f"{__name__}.process_and_send_private") # Specific logger for async task
            for segment in process_conversation(user_id, content_with_time, chat_type="private"):
                sender.set_input_status(user_id)
                time.sleep(random.uniform(1.0, 3.0))
                msg_segments = await parse_ai_message_to_segments(
                    segment,
                    message_id,
                    chat_id=user_id,
                    chat_type="private"
                )
                if msg_segments: # Only send if there's something to send
                    sender.send_private_msg(int(user_id), msg_segments)
                else:
                    logger_async.debug(f"No segments to send for segment: {segment[:50]}...")


        # 在新的事件循环中运行异步函数
        def run_async():
            logger_run_async = get_logger(f"{__name__}.run_async_private")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                logger_run_async.debug("Starting new event loop for private message processing.")
                loop.run_until_complete(process_and_send())
            except Exception as e_async:
                logger_run_async.error(f"Error in private message async task: {e_async}", exc_info=True)
            finally:
                loop.close()
                logger_run_async.debug("Closed event loop for private message processing.")

        threading.Thread(target=run_async, daemon=True).start()

    except Exception as e:
        logger.error(f"处理私聊消息异常: {e}", exc_info=True)


async def handle_group_message(msg_dict, sender: IMessageSender):
    """
    处理群聊消息：
      - 记录消息日志
      - 异步生成回复，达到流式发送的效果
    """
    logger = get_logger(__name__) # Get logger instance
    group_id = str(msg_dict.get("group_id")) # Ensure group_id is always available for logging
    try:
        sender_info = msg_dict["sender"]
        user_id = str(sender_info["user_id"])
        
        # 获取机器人自身ID 和 消息段
        self_id = str(msg_dict.get('self_id'))
        message_segments = msg_dict.get("message", [])
        
        # 提取纯文本内容
        current_message_text = extract_text_from_message(msg_dict).strip()

        # 如果是机器人自己发的消息，或者纯文本内容为空，则跳过接龙检测和大部分处理
        if user_id == self_id:
            logger.debug(f"机器人自身消息 in group {group_id}，不处理。")
            return
        if not current_message_text:
            logger.debug(f"空消息 in group {group_id} from user {user_id}，跳过特定处理。")
            # Might still want to log activity or other non-text interactions if any.
            # For now, returning if no text.
            return

        # 更新消息历史 (调用新模块函数)
        update_message_history(group_id, user_id, current_message_text)

        logger.debug(f"开始处理群 {group_id} 的消息 from user {user_id}")
        
        # 更新群活跃度（无论是否是命令消息）
        group_activity_manager.update_group_activity(group_id)
        
        # 检查是否允许处理该消息
        if not check_access(group_id, is_group=True): # check_access uses logging
            logger.debug(f"群 {group_id} 在黑名单中或不在白名单中，跳过处理")
            return
            
        # 检查并处理接龙
        dragon_handled = await handle_dragon_logic(group_id, self_id, sender)
        if dragon_handled:
            logger.debug(f"接龙已被 handle_dragon_logic 处理 in group {group_id}，结束当前消息流程。")
            return # 如果接龙被处理了，则不再继续下面的 @ 或 前缀 逻辑

        # 检查是否 @机器人
        is_mentioned = any(
            seg.get("type") == "at" and seg.get("data", {}).get("qq") == self_id
            for seg in message_segments
        )
        
        # 解析消息内容
        user_content = parse_group_message_content(msg_dict) # This function also uses print internally that needs update
        logger.debug(f"解析后的消息内容 for group {group_id}: {user_content[:100]}...")
        
        # 检查是否以前缀开头
        reply_prefix = CONFIG["qqbot"].get("group_prefix", "#")
        has_prefix = user_content.startswith(reply_prefix)
        
        # 如果既没有 @机器人，也没有以前缀开头，则跳过
        if not is_mentioned and not has_prefix:
            logger.debug(f"消息 in group {group_id}既不以 '{reply_prefix}' 开头，也没有 @机器人 ({self_id})，跳过处理")
            return
            
        # 如果是以触发前缀开头，则去除前缀
        if has_prefix:
            user_content = user_content[len(reply_prefix):].strip()
        
        if not user_content: # After stripping prefix or if only @ mention with no other text
            logger.debug(f"去除前缀或处理 @ 消息后内容为空 in group {group_id}，跳过处理")
            return
            
        username = sender_info.get("nickname", "")
        message_id = str(msg_dict.get("message_id", ""))
        timestamp = msg_dict.get("time", int(time.time()))
        
        # 格式化用户输入内容
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        ai_input_content = f"[用户:{username}({user_id})] [群:{group_id}] [时间:{time_str}] {user_content}"
        
        # 记录普通消息日志 (log_message is assumed to be DB logger)
        log_message(user_id, username, message_id, ai_input_content, timestamp, group_id=group_id)
        logger.info(f"Q: {username}[{user_id}] in G[{group_id}] | MsgId: {message_id} | Content: {ai_input_content}")

        logger.debug(f"开始调用AI处理消息 for group {group_id} (Input: {ai_input_content[:100]}...)")
        
        # 异步处理回复消息，实现流式发送效果
        try:
            # 使用 ai_input_content 作为 AI 输入
            for segment_text in process_conversation(group_id, ai_input_content, chat_type="group"):
                try:
                    logger.debug(f"收到AI回复片段 for group {group_id}: {segment_text[:100]}...")
                    msg_segments = await parse_ai_message_to_segments(
                        segment_text,
                        message_id,
                        chat_id=group_id,
                        chat_type="group"
                    )

                    non_poke_segments = []
                    poke_actions = []
                    for seg in msg_segments:
                        if seg["type"] == "poke":
                            poke_user_id = seg["data"]["qq"]
                            poke_actions.append((group_id, poke_user_id))
                        else:
                            non_poke_segments.append(seg)

                    for poke_group_id_act, poke_user_id_act in poke_actions:
                        try:
                            logger.info(f"Executing poke to {poke_user_id_act} in group {poke_group_id_act}")
                            post.send_poke(poke_group_id_act, poke_user_id_act)
                        except Exception as poke_err:
                            logger.error(f"发送戳一戳失败 to {poke_user_id_act} in group {poke_group_id_act}: {poke_err}", exc_info=True)

                    if non_poke_segments:
                        logger.debug(f"发送非戳一戳消息片段到群 {group_id}")
                        sender.send_group_msg(int(group_id), non_poke_segments)
                        await asyncio.sleep(random.uniform(1.0, 3.0)) 

                except Exception as e_seg:
                    logger.error(f"处理群消息段时出错 in group {group_id}: {e_seg}", exc_info=True)
                    # continue # Continue processing other segments from AI if possible

        except Exception as e_ai:
            logger.error(f"AI处理消息时出错 for group {group_id}: {e_ai}", exc_info=True)
            error_msg_seg = {"type": "text", "data": {"text": f"抱歉，处理您的消息时遇到了一些内部问题，请稍后再试或联系管理员。"}}
            try:
                sender.send_group_msg(int(group_id), [error_msg_seg])
            except Exception as e_send_err:
                logger.error(f"发送错误通知到群 {group_id} 失败: {e_send_err}", exc_info=True)

    except Exception as e_main:
        logger.error(f"处理群聊消息 {msg_dict.get('message_id', 'N/A')} in group {group_id} 时发生未捕获的异常: {e_main}", exc_info=True)
        try:
            # Generic error message to the group
            error_msg_seg = {"type": "text", "data": {"text": "哎呀，我在处理消息的时候好像迷路了...稍等一下再试试吧！"}}
            if group_id: # Ensure group_id is valid before trying to send
                 sender.send_group_msg(int(group_id), [error_msg_seg])
        except Exception as e_send_final_err:
            logger.error(f"发送最终错误通知到群 {group_id} 失败: {e_send_final_err}", exc_info=True)
