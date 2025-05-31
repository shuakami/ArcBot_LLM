import os

from config import CONFIG, save_config
from utils.blacklist import add_blacklist, remove_blacklist
from utils.files import get_history_file
from utils.text import extract_text_from_message
from utils.whitelist import add_whitelist, remove_whitelist
from napcat.message_sender import IMessageSender
import utils.role_manager as role_manager
from typing import Dict, Any
from napcat.post import get_friend_list, FRIEND_LIST

# 角色添加状态跟踪
# key: (user_id: str, chat_id: str), value: Dict[str, Any] (e.g., {'state': 'awaiting_prompt', 'type': 'private'})
user_add_role_state: Dict[tuple[str, str], Dict[str, Any]] = {}

# /role 命令是否仅好友可用，默认为 False
ROLE_FRIENDS_ONLY = False

def send_reply(msg_dict, reply, sender: IMessageSender):
    """
    根据消息类型构造回复 payload 并发送回复消息。
    """
    if msg_dict.get("message_type") == "private":
        sender.send_private_msg(int(msg_dict["sender"]["user_id"]), reply)
    else:
        sender.send_group_msg(int(msg_dict.get("group_id")), reply)


def process_command(msg_dict, sender: IMessageSender):
    text = extract_text_from_message(msg_dict)
    sender_qq = str(msg_dict["sender"]["user_id"])
    admin_qq_list = CONFIG["qqbot"].get("admin_qq", [])

    if text.startswith("/arcreset"):
        return process_reset_command(msg_dict, sender)
    elif text.startswith("/archelp"):
        return process_help_command(msg_dict, sender)
    elif text.startswith("/arcblack") or text.startswith("/arcwhite"):
        return process_listmod_command(msg_dict, sender)
    elif text.startswith("/arcqqlist"):
        return process_msg_list_command(msg_dict, sender)
    elif text.startswith("/arcgrouplist"):
        return process_group_list_command(msg_dict, sender)
    elif text.startswith("/role"):
        # 在处理 /role 命令之前，确保好友列表已加载（如果功能开启）
        if ROLE_FRIENDS_ONLY and not FRIEND_LIST:
            # 尝试自动更新一次，如果管理员开启了这个功能但列表为空
            if sender_qq in admin_qq_list: # 仅管理员触发自动更新
                get_friend_list()
                send_reply(msg_dict, "检测到好友限制已开启但列表为空，已尝试自动更新好友列表。请稍后再试。", sender)
            else:
                send_reply(msg_dict, "好友列表尚未加载，请稍后重试或联系管理员使用 /updatefriends 更新列表。", sender)
            return True
        
        # 原有的 /role 路由逻辑
        tokens = text.split()
        sub_command = tokens[1].lower() if len(tokens) > 1 else "list"
        if sub_command in ["pending", "approve", "reject"]:
            return process_role_admin_command(msg_dict, sender)
        else:
            return process_role_command(msg_dict, sender) # 普通用户的 /role 命令
    elif text.startswith("/rolefriendonly"):
        return process_role_friend_only_command(msg_dict, sender)
    elif text.startswith("/updatefriends"):
        return process_update_friends_command(msg_dict, sender)
    return False


def process_help_command(msg_dict, sender: IMessageSender):
    """
    处理菜单指令 /archelp，显示管理员相关命令使用方法：
    """
    help_text = (
        "ArcBot - 命令菜单\n"
        "=====聊天记录重置=====\n"
        "| /arcreset - 重置记录（私聊）\n"
        "| /arcreset [群号] - 重置指定群号记录\n"
        "=====黑白名单管理=====\n"
        "| /arcblack add [QQ/Q群] [msg/group] - 将QQ或群加入黑名单\n"
        "| /arcblack remove [QQ/Q群] [msg/group] - 将QQ或群从黑名单中移除\n"
        "| /arcwhite add [QQ/Q群] [msg/group] - 将QQ或群加入白名单\n"
        "| /arcwhite remove [QQ/Q群] [msg/group] - 将QQ或群从白名单中移除\n"
        "=====名单模式切换=====\n"
        "| /arcqqlist [white/black] - 切换QQ名单模式\n"
        "| /arcgrouplist [white/black] - 切换群聊名单模式\n"
    )

    send_reply(msg_dict, help_text, sender)
    return True


def process_reset_command(msg_dict, sender: IMessageSender):
    """
    处理 /arcreset 命令：
      - 私聊：任何人发送 /arcreset 重置自己的对话记录
      - 群聊：必须以 "/arcreset [群号]" 形式，并且只有管理员（admin_qq）才能重置对应群组记录
    执行后回复提示信息，并返回 True；若不是 /arcreset 命令返回 False。
    """
    # 私聊消息中文本来自 message 数组；群聊直接取 raw_message
    if msg_dict.get("message_type") == "group":
        text = msg_dict.get("raw_message", "")
    else:
        text = "".join(
            seg.get("data", {}).get("text", "")
            for seg in msg_dict.get("message", [])
            if seg.get("type") == "text"
        )

    sender_qq = str(msg_dict["sender"]["user_id"])
    if msg_dict.get("message_type") == "group":
        tokens = text.split()
        if len(tokens) >= 2:
            target_group = tokens[1].strip()
            if sender_qq not in CONFIG["qqbot"].get("admin_qq", []):
                reply = "只有管理员才能重置群聊记录。"
            else:
                history_file = get_history_file(target_group, chat_type="group")
                if os.path.exists(history_file):
                    os.remove(history_file)
                    reply = f"群号 {target_group} 的聊天记录已重置。"
                else:
                    reply = f"群号 {target_group} 无聊天记录可重置。"
        else:
            reply = "命令格式错误，请使用：/arcreset [群号]"
    else:
        # 私聊重置自己的聊天记录
        history_file = get_history_file(sender_qq, chat_type="private")
        if os.path.exists(history_file):
            os.remove(history_file)
            reply = "你的聊天记录已重置。"
        else:
            reply = "你没有聊天记录。"

    send_reply(msg_dict, reply, sender)
    return True


def process_listmod_command(msg_dict, sender: IMessageSender):
    """
    处理黑白名单管理相关指令：
      命令格式统一支持两类对象：QQ 或 群
      
      命令格式：
        - /arcblack add [QQ/Q群] [msg/group]
        - /arcblack remove [QQ/Q群] [msg/group]
        - /arcwhite add [QQ/Q群] [msg/group]
        - /arcwhite remove [QQ/Q群] [msg/group]
      
      "msg" 表示用户消息黑白名单，
      "group" 表示群聊黑白名单。
      
      仅允许配置中的 admin_qq 执行相关命令。命令处理完毕后直接回复提示信息，并返回 True；
      如果不是名单管理命令，则返回 False。
    """
    text = extract_text_from_message(msg_dict)
    sender_qq = str(msg_dict["sender"]["user_id"])
    reply = None
    admin_list = CONFIG["qqbot"].get("admin_qq", [])

    # 判断管理员权限
    if sender_qq not in admin_list:
        reply = "无权限执行该命令。"
        send_reply(msg_dict, reply, sender)
        return True

    tokens = text.split()
    if len(tokens) < 4:
        reply = "命令格式错误，请使用：/arcblack add/remove [QQ/Q群] [msg/group] 或 /arcwhite add/remove [QQ/Q群] [msg/group]"
        send_reply(msg_dict, reply, sender)
        return True
    # tokens[0] 为命令，如 /arcblack 或 /arcwhite
    # tokens[1] 为 add 或 remove
    # tokens[2] 为目标号码
    # tokens[3] 为类型标识，要求为 msg 或 group
    target_id = tokens[2].strip()
    list_type = tokens[3].lower()

    # 根据命令分支和名单类型选择处理逻辑：
    if text.startswith("/arcblack"):
        if tokens[1].lower() == "add":
            if list_type == "msg":
                if add_blacklist(target_id, is_group=False):
                    reply = f"QQ号 {target_id} 已成功加入用户黑名单。"
                else:
                    reply = f"QQ号 {target_id} 已在用户黑名单中。"
            elif list_type == "group":
                if add_blacklist(target_id, is_group=True):
                    reply = f"群号 {target_id} 已成功加入群聊黑名单。"
                else:
                    reply = f"群号 {target_id} 已在群聊黑名单中。"
            else:
                reply = "名单类型错误，请使用 msg 或 group。"
        elif tokens[1].lower() == "remove":
            if list_type == "msg":
                if remove_blacklist(target_id, is_group=False):
                    reply = f"QQ号 {target_id} 已从用户黑名单中移除。"
                else:
                    reply = f"QQ号 {target_id} 不在用户黑名单中。"
            elif list_type == "group":
                if remove_blacklist(target_id, is_group=True):
                    reply = f"群号 {target_id} 已从群聊黑名单中移除。"
                else:
                    reply = f"群号 {target_id} 不在群聊黑名单中。"
            else:
                reply = "名单类型错误，请使用 msg 或 group。"
        else:
            reply = "无效的命令操作，请使用 add 或 remove。"

    elif text.startswith("/arcwhite"):
        if tokens[1].lower() == "add":
            if list_type == "msg":
                if add_whitelist(target_id, is_group=False):
                    reply = f"QQ号 {target_id} 已成功加入用户白名单。"
                else:
                    reply = f"QQ号 {target_id} 已在用户白名单中。"
            elif list_type == "group":
                if add_whitelist(target_id, is_group=True):
                    reply = f"群号 {target_id} 已成功加入群聊白名单。"
                else:
                    reply = f"群号 {target_id} 已在群聊白名单中。"
            else:
                reply = "名单类型错误，请使用 msg 或 group。"
        elif tokens[1].lower() == "remove":
            if list_type == "msg":
                if remove_whitelist(target_id, is_group=False):
                    reply = f"QQ号 {target_id} 已从用户白名单中移除。"
                else:
                    reply = f"QQ号 {target_id} 不在用户白名单中。"
            elif list_type == "group":
                if remove_whitelist(target_id, is_group=True):
                    reply = f"群号 {target_id} 已从群聊白名单中移除。"
                else:
                    reply = f"群号 {target_id} 不在群聊白名单中。"
            else:
                reply = "名单类型错误，请使用 msg 或 group。"
        else:
            reply = "无效的命令操作，请使用 add 或 remove。"
    else:
        reply = "无效的命令。"

    send_reply(msg_dict, reply, sender)
    return True


def process_msg_list_command(msg_dict, sender: IMessageSender):
    """
    处理修改用户消息名单模式指令：
      - /arcqqlist [white/black]
      
    仅允许管理员执行，命令处理后直接回复提示信息，并返回 True；
    如果不是该命令，则返回 False。
    """
    text = extract_text_from_message(msg_dict)
    tokens = text.split()
    if len(tokens) < 2 or tokens[1].lower() not in ("white", "black"):
        reply = "命令格式错误，请使用：/arcqqlist [white/black]"
    else:
        new_mode = tokens[1].lower()
        # 修改用户消息名单模式配置，并保存到配置文件
        CONFIG["qqbot"]["qq_list_mode"] = new_mode
        save_config()
        reply = f"私聊名单模式已切换为 {new_mode}。"
    
    send_reply(msg_dict, reply, sender)
    return True

def process_group_list_command(msg_dict, sender: IMessageSender):
    """
    处理修改群聊名单模式指令：
      - /arcgrouplist [white/black]
      
    仅允许管理员执行，命令处理后直接回复提示信息，并返回 True；
    如果不是该命令，则返回 False。
    """
    text = extract_text_from_message(msg_dict)
    tokens = text.split()
    if len(tokens) < 2 or tokens[1].lower() not in ("white", "black"):
        reply = "命令格式错误，请使用：/arcgrouplist [white/black]"
    else:
        new_mode = tokens[1].lower()
        # 修改群聊名单模式配置，并保存到配置文件
        CONFIG["qqbot"]["group_list_mode"] = new_mode
        save_config()
        reply = f"群聊名单模式已切换为 {new_mode}。"
    
    send_reply(msg_dict, reply, sender)
    return True

def process_role_command(msg_dict, sender: IMessageSender):
    """
    处理用户 /role 相关命令 (非管理员)
    """
    global ROLE_FRIENDS_ONLY, FRIEND_LIST, user_add_role_state
    sender_qq = str(msg_dict["sender"]["user_id"])

    # 好友校验逻辑放在最前面
    if ROLE_FRIENDS_ONLY and sender_qq not in FRIEND_LIST:
        if sender_qq not in CONFIG["qqbot"].get("whitelist", []):
             send_reply(msg_dict, "这个功能只对已经添加我好友的人开放喵。", sender)
             return True
    
    text = extract_text_from_message(msg_dict).strip() # 获取纯文本命令
    sender_info = msg_dict["sender"]
    user_id = str(sender_info["user_id"])
    message_type = msg_dict.get("message_type")
    chat_id = str(msg_dict.get("group_id") if message_type == "group" else user_id)

    tokens = text.split()
    # 第一个 token 应该是 /role, 第二个是子命令 (如果存在)
    sub_command = tokens[1].lower() if len(tokens) > 1 else "list" # 默认为 list

    reply = ""

    if sub_command == "add":
        # 开始添加角色流程
        state_key = (user_id, chat_id)
        user_add_role_state[state_key] = {
            'state': 'awaiting_prompt',
            'type': message_type, # 记录消息类型，以便后续正确回复
            'chat_id': chat_id # 记录chat_id
        }
        reply = "请输入角色 Prompt喵："
        print(f"[DEBUG] User {user_id} in chat {chat_id} (type: {message_type}) started adding role. State: {user_add_role_state[state_key]}")

    elif sub_command == "edit":
        if len(tokens) < 3:
            reply = "请指定要编辑的角色名称：/role edit <角色名称>"
        else:
            role_name_to_edit = " ".join(tokens[2:]).strip() # 支持带空格的角色名
            existing_roles = role_manager.load_roles()
            if role_name_to_edit not in existing_roles:
                reply = f"错误：角色模板 '{role_name_to_edit}' 不存在。"
            else:
                state_key = (user_id, chat_id)
                user_add_role_state[state_key] = {
                    'state': 'awaiting_edit_prompt',
                    'type': message_type,
                    'chat_id': chat_id,
                    'role_name_to_edit': role_name_to_edit
                }
                reply = f"请输入 '{role_name_to_edit}' 的新 Prompt喵："
                print(f"[DEBUG] User {user_id} in chat {chat_id} (type: {message_type}) started editing role '{role_name_to_edit}'. State: {user_add_role_state[state_key]}")

    elif sub_command == "delete":
        if len(tokens) < 3:
            reply = "请指定要删除的角色名称：/role delete <角色名称>"
        else:
            role_name_to_delete = " ".join(tokens[2:]).strip()
            if role_manager.delete_role(role_name_to_delete):
                reply = f"角色模板 '{role_name_to_delete}' 已删除喵...（请注意，删除后无法恢复喵）"
            else:
                reply = f"删除角色模板 '{role_name_to_delete}' 失败（可能是名称不存在喵？）。"

    elif sub_command == "list":
        role_names = role_manager.get_role_names()
        if not role_names:
            reply = "当前还没有任何角色模板喵。使用 /role add 开始添加吧~"
        else:
            reply = "当前可用角色模板：\\n - " + "\\n - ".join(role_names)
            reply += "\\n\\n使用 /role add|edit|delete <名称> 进行管理。\\n使用 /role <角色名称> <你的对话...> - 使用角色"

    else:
        if len(tokens) > 1 and sub_command not in ["add", "edit", "delete", "list"]:
             reply = f"无效的 /role 子命令 '{sub_command}' 喵。\\n"
             reply += "用法: \\n"
             reply += "  /role list (或 /role) - 查看可用角色\\n"
             reply += "  /role add          - 添加新角色 (提交审核)\\n"
             reply += "  /role edit <名称> - 编辑现有角色\\n"
             reply += "  /role delete <名称> - 删除指定角色\\n"
             reply += "  /role <角色名称> <你的对话...> - 使用角色"

    if reply:
        send_reply(msg_dict, reply, sender)

    return True # 表示命令已被处理

# +++ 新增管理员审核处理函数 +++
def process_role_admin_command(msg_dict, sender: IMessageSender):
    """处理 /role pending, approve, reject 命令"""
    text = extract_text_from_message(msg_dict).strip()
    sender_info = msg_dict["sender"]
    user_id = str(sender_info["user_id"])
    message_type = msg_dict.get("message_type")
    chat_id = str(msg_dict.get("group_id") if message_type == "group" else user_id)

    # 检查管理员权限
    admin_qq_list = CONFIG["qqbot"].get("admin_qq", [])
    if user_id not in admin_qq_list:
        send_reply(msg_dict, "抱歉，只有管理员才能执行此操作喵。", sender)
        return True # 明确拒绝

    tokens = text.split()
    if len(tokens) < 2:
        send_reply(msg_dict, "无效的管理命令。请使用 /role pending, /role approve <ID>, 或 /role reject <ID>", sender)
        return True

    admin_sub_command = tokens[1].lower()
    reply = ""

    if admin_sub_command == "pending":
        pending_roles = role_manager.list_pending_roles()
        if not pending_roles:
            reply = "当前没有待审核的角色模板。"
        else:
            reply = "待审核的角色列表：\n"
            for pid, info in pending_roles.items():
                reply += f"- ID: {pid}\n  名称: {info.get('name', '?')}\n  申请人: {info.get('requester_user_id', '?')}\n  来源: {info.get('requester_chat_type', '?')} {info.get('requester_chat_id', '?')}\n  (Prompt 预览: {info.get('prompt', '')[:30]}...)\n"
            reply += "\n使用 /role approve <ID> 或 /role reject <ID> 处理。"

    elif admin_sub_command == "approve":
        if len(tokens) < 3:
            reply = "请提供要批准的审核 ID: /role approve <审核ID>"
        else:
            pending_id_to_approve = tokens[2].strip()
            success, approved_info = role_manager.approve_pending_role(pending_id_to_approve)
            if success and approved_info:
                reply = f"角色 '{approved_info['name']}' (ID: {pending_id_to_approve}) 已批准并添加。"
                # 通知原申请人
                try:
                    notify_msg = f"好耶！你提交的角色模板 '{approved_info['name']}' 已通过审核喵。"
                    requester_chat_type = approved_info.get("requester_chat_type")
                    requester_chat_id = approved_info.get("requester_chat_id")
                    if requester_chat_type == "private":
                        sender.send_private_msg(int(requester_chat_id), notify_msg)
                    elif requester_chat_type == "group":
                        sender.send_group_msg(int(requester_chat_id), notify_msg)
                except Exception as notify_err:
                    print(f"[WARN] 批准角色后通知申请人失败: {notify_err}")
            elif approved_info:
                reply = f"批准角色 '{approved_info['name']}' (ID: {pending_id_to_approve}) 失败，角色未能添加到主列表（可能重名？）。请检查日志。"
            else:
                reply = f"批准失败：找不到审核 ID '{pending_id_to_approve}' 或处理出错。"

    elif admin_sub_command == "reject":
        if len(tokens) < 3:
            reply = "请提供要拒绝的审核 ID: /role reject <审核ID>"
        else:
            pending_id_to_reject = tokens[2].strip()
            success, rejected_info = role_manager.reject_pending_role(pending_id_to_reject)
            if success and rejected_info:
                reply = f"角色 '{rejected_info['name']}' (ID: {pending_id_to_reject}) 的审核请求已拒绝。"
                # 通知原申请人
                try:
                    notify_msg = f"抱歉，你提交的角色模板 '{rejected_info['name']}' 未通过审核。"
                    requester_chat_type = rejected_info.get("requester_chat_type")
                    requester_chat_id = rejected_info.get("requester_chat_id")
                    if requester_chat_type == "private":
                        sender.send_private_msg(int(requester_chat_id), notify_msg)
                    elif requester_chat_type == "group":
                         # 在群里通知有点奇怪，可以选择私聊通知申请人
                         sender.send_private_msg(int(rejected_info.get("requester_user_id")), notify_msg)
                except Exception as notify_err:
                    print(f"[WARN] 拒绝角色后通知申请人失败: {notify_err}")
            else:
                reply = f"拒绝失败：找不到审核 ID '{pending_id_to_reject}' 或处理出错。"
    else:
        reply = "无效的管理命令。请使用 /role pending, /role approve <ID>, 或 /role reject <ID>"

    if reply:
        send_reply(msg_dict, reply, sender)

    return True # 表示命令已被处理

def process_role_friend_only_command(msg_dict, sender: IMessageSender):
    """
    处理 /rolefriendonly [on/off] 命令，切换 /role 命令是否仅好友可用。
    仅限管理员。
    """
    global ROLE_FRIENDS_ONLY
    text = extract_text_from_message(msg_dict).strip()
    sender_qq = str(msg_dict["sender"]["user_id"])
    admin_qq_list = CONFIG["qqbot"].get("admin_qq", [])

    if sender_qq not in admin_qq_list:
        send_reply(msg_dict, "抱歉，您没有权限执行此命令。", sender)
        return True

    tokens = text.split()
    reply_text = ""

    if len(tokens) == 2:
        mode = tokens[1].lower()
        if mode == "on":
            ROLE_FRIENDS_ONLY = True
            reply_text = "`/role` 命令已设置为仅好友可用喵。"
            # 如果开启，尝试获取一次好友列表
            if not FRIEND_LIST:
                get_friend_list() # 发起获取好友列表的请求
                reply_text += "\n正在尝试获取好友列表，请稍后检查 `/updatefriends` 的输出或直接使用 `/role`。"
        elif mode == "off":
            ROLE_FRIENDS_ONLY = False
            reply_text = "`/role` 命令已设置为对所有用户开放。"
        else:
            reply_text = "命令格式错误。请使用 `/rolefriendonly on` 或 `/rolefriendonly off`。"
    else:
        current_status = "开启" if ROLE_FRIENDS_ONLY else "关闭"
        reply_text = f"当前 `/role` 命令好友限制状态：{current_status}。\n使用 `/rolefriendonly on` 或 `/rolefriendonly off` 进行更改。"

    send_reply(msg_dict, reply_text, sender)
    return True

def process_update_friends_command(msg_dict, sender: IMessageSender):
    """
    处理 /updatefriends 命令，手动触发更新好友列表。
    """
    sender_qq = str(msg_dict["sender"]["user_id"])
    admin_qq_list = CONFIG["qqbot"].get("admin_qq", [])
        
    get_friend_list() # 调用 post.py 中的函数
    reply_text = "更新好了喵。"
    if FRIEND_LIST:
        reply_text += f"\n当前已缓存 {len(FRIEND_LIST)} 个好友。"
    send_reply(msg_dict, reply_text, sender)
    return True