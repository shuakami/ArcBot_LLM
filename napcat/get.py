import json
import re
import time
from config import CONFIG
from napcat.chat_logic import handle_group_message, handle_private_message
from napcat.command_handler import process_command, user_add_role_state, send_reply
from napcat.message_sender import WebSocketSender
from utils.emoji_storage import emoji_storage
import utils.role_manager as role_manager
from utils.text import extract_text_from_message
import asyncio

# 全局字典，用于暂存待处理的好友请求
# key: flag (str), value: dict {user_id: str, comment: str, timestamp: int}
pending_friend_requests: dict[str, dict] = {}

def handle_incoming_message(message):
    try:
        msg = json.loads(message)
        print(f"[DEBUG] 收到消息: {msg}")
        post_type = msg.get("post_type")
        sender = WebSocketSender() # 实例化 Sender，后面可能需要
        
        # 好友请求处理
        if post_type == "request" and msg.get("request_type") == "friend":
            handle_friend_request(msg, sender) # 调用好友请求处理函数
            return # 请求消息不需要后续处理
        
        # 主人好友请求决策处理
        if post_type == "message" and msg.get("message_type") == "private":
            master_qq = str(CONFIG['qqbot'].get('master_qq')) # 获取主人QQ
            user_id = str(msg.get("sender", {}).get("user_id"))
            
            if master_qq and user_id == master_qq: # 确保配置了主人QQ且消息来自主人
                message_text = extract_text_from_message(msg).strip()
                match = re.match(r"^(同意|拒绝)好友\s+(\S+)$", message_text)
                if match:
                    action = match.group(1)
                    flag = match.group(2)
                    process_friend_request_decision(flag, action, sender)
                    return # 指令已被处理
        
        if post_type != "message": # 如果不是上面处理过的 request 或 主人指令，且不是 message，则忽略
            return
        
        # 角色添加状态处理
        sender_info = msg.get("sender", {})
        user_id = str(sender_info.get("user_id"))
        message_type = msg.get("message_type")
        # 确定消息来源ID (私聊是user_id, 群聊是group_id)
        chat_id = str(msg.get("group_id") if message_type == "group" else user_id)
        state_key = (user_id, chat_id)

        if state_key in user_add_role_state:
            current_state_data = user_add_role_state[state_key]
            current_state = current_state_data.get('state')
            message_text = extract_text_from_message(msg).strip()

            if current_state == 'awaiting_prompt':
                if not message_text:
                    reply_text = "Prompt 不能为空，请重新输入 Prompt："
                    send_reply(msg, reply_text, sender)
                else:
                    print(f"[DEBUG] Received prompt for role add from {user_id} in {chat_id}: {message_text[:50]}...")
                    current_state_data['prompt'] = message_text
                    current_state_data['state'] = 'awaiting_name'
                    reply_text = "请输入该模板的名字："
                    send_reply(msg, reply_text, sender)
                return # 消息已被状态机处理
            
            elif current_state == 'awaiting_name':
                if not message_text:
                    reply_text = "角色名称不能为空，请重新输入该模板的名字："
                    send_reply(msg, reply_text, sender)
                else:
                    role_name = message_text
                    prompt = current_state_data.get('prompt', '')
                    print(f"[DEBUG] Received name for role add from {user_id} in {chat_id}: {role_name}")
                    # 调用 stage_role_for_approval
                    pending_id = role_manager.stage_role_for_approval(
                        role_name, 
                        prompt, 
                        user_id, 
                        chat_id, 
                        message_type
                    )

                    if pending_id:
                        # 告知用户已提交审核
                        reply_text = f"角色 '{role_name}' 已提交审核，审核ID: {pending_id}\n请等待管理员批准喵。"
                        send_reply(msg, reply_text, sender)

                        # 向管理员发送审核请求
                        admin_qq_list = CONFIG["qqbot"].get("admin_qq", [])
                        if not admin_qq_list:
                            print("[WARN] 未配置管理员QQ (admin_qq)，无法发送角色审核请求。")
                        else:
                            approval_msg = (
                                f"收到新的角色模板审核请求：\n"
                                f"申请人QQ: {user_id}\n"
                                f"来源: {message_type} {chat_id}\n"
                                f"审核ID: {pending_id}\n"
                                f"角色名称: {role_name}\n"
                                f"-- Prompt --\n{prompt}\n-- Prompt End --\n"
                                f"请使用 /role approve {pending_id} 或 /role reject {pending_id} 进行操作。"
                            )
                            # 给每个管理员都发送私聊
                            for admin_qq in admin_qq_list:
                                try:
                                    sender.send_private_msg(int(admin_qq), approval_msg)
                                except Exception as send_err:
                                    print(f"[ERROR] 发送审核通知给管理员 {admin_qq} 失败: {send_err}")
                    else:
                        # stage 失败 (例如名称为空)
                        reply_text = f"提交角色 '{role_name}' 审核失败，请检查名称是否有效。"
                        send_reply(msg, reply_text, sender)
                    
                    # 清理状态
                    del user_add_role_state[state_key]
                return # 消息已被状态机处理
            
            elif current_state == 'awaiting_edit_prompt':
                if not message_text:
                    reply_text = "新 Prompt 不能为空，请重新输入新 Prompt："
                    send_reply(msg, reply_text, sender)
                else:
                    role_name_to_edit = current_state_data.get('role_name_to_edit', '')
                    new_prompt = message_text
                    print(f"[DEBUG] Received new prompt for role edit from {user_id} in {chat_id} for role '{role_name_to_edit}': {new_prompt[:50]}...")
                    if role_manager.edit_role(role_name_to_edit, new_prompt):
                        reply_text = f"角色模板 '{role_name_to_edit}' 更新成功！"
                    else:
                        reply_text = f"更新角色模板 '{role_name_to_edit}' 失败了（可能是角色在其间被删除了？）。"
                    send_reply(msg, reply_text, sender)
                    # 清理状态
                    del user_add_role_state[state_key]
                return # 消息已被状态机处理
        
        if CONFIG["debug"]: print("收到消息:", msg)
        
        # 检查并存储表情包
        emoji_storage.store_emoji(msg)
        
        # 优先处理命令类消息
        if process_command(msg, sender):
            return
        
        # 正常聊天逻辑分为私聊和群聊
        if msg.get("message_type") == "private":
            if CONFIG["debug"]: print("处理私聊消息")
            handle_private_message(msg, sender)
        elif msg.get("message_type") == "group":
            if CONFIG["debug"]: print("处理群聊消息")
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(handle_group_message(msg, sender))
            except RuntimeError:
                asyncio.run(handle_group_message(msg, sender))
    except Exception as e:
        print("处理ws消息异常:", e)

def handle_friend_request(data: dict, sender: WebSocketSender):
    """处理好友请求事件"""
    user_id = str(data.get("user_id"))
    comment = data.get("comment", "")
    flag = data.get("flag")
    master_qq = str(CONFIG['qqbot'].get('master_qq'))

    if not flag:
        print("[Error] 好友请求缺少 flag，无法处理。", data)
        return
    
    if not master_qq:
        print("[Error] 未配置主人 QQ (master_qq)，无法处理好友请求。")
        return

    # 暂存请求信息
    pending_friend_requests[flag] = {
        "user_id": user_id,
        "comment": comment,
        "timestamp": int(time.time())
    }
    print(f"[Info] 暂存好友请求: flag={flag}, user_id={user_id}")

    # 构建通知消息
    notification_message = (
        f"收到新的好友请求：\n"
        f"QQ: {user_id}\n"
        f"验证信息: {comment}\n"
        f"请求标识: {flag}\n"
        f"请回复 '同意好友 {flag}' 或 '拒绝好友 {flag}' 进行处理喵。"
    )

    # 发送通知给主人
    try:
        sender.send_private_msg(int(master_qq), notification_message)
        print(f"[Info] 已发送好友请求通知给主人 {master_qq}")
    except Exception as e:
        print(f"[Error] 发送好友请求通知给主人 {master_qq} 失败: {e}")

def process_friend_request_decision(flag: str, action: str, sender: WebSocketSender):
    """处理主人的好友请求决策"""
    master_qq = str(CONFIG['qqbot'].get('master_qq')) # 获取主人QQ用于回复
    
    if flag not in pending_friend_requests:
        print(f"[Warning] 收到未知或已处理的好友请求决策: flag={flag}")
        try:
            sender.send_private_msg(int(master_qq), f"未找到待处理的请求标记: {flag}，可能已被处理或标识错误。")
        except Exception as e:
            print(f"[Error] 回复主人未找到请求标记失败: {e}")
        return

    request_info = pending_friend_requests[flag]
    user_id = request_info["user_id"]
    approve = (action == "同意")
    remark = "" # 默认为空备注
    
    print(f"[Info] 处理好友请求决策: flag={flag}, action={action}, approve={approve}")

    try:
        # 处理好友请求
        sender.set_friend_add_request(flag=flag, approve=approve, remark=remark)
        
        print(f"[Info] 已通过 sender.set_friend_add_request 发送动作: flag={flag}, approve={approve}")
        
        # 从暂存中移除
        del pending_friend_requests[flag]
        
        # 回复主人确认
        sender.send_private_msg(int(master_qq), f"已 {action} 来自 {user_id} 的好友请求 (flag: {flag})。")
        
    except Exception as e:
        print(f"[Error] 处理好友请求 {flag} 时发生错误: {e}")
        try:
            sender.send_private_msg(int(master_qq), f"处理好友请求 {flag} 时发生错误: {e}")
        except Exception as e_reply:
            print(f"[Error] 回复主人处理错误信息失败: {e_reply}")
