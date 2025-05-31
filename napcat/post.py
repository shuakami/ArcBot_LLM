import json
import websocket
import threading
import time # 新增 time
import random # 新增 random
from queue import Queue # 可以考虑用Queue传递结果，或简单的list
from config import CONFIG
from napcat.get import handle_incoming_message
from typing import Optional

ws_app = None
FRIEND_LIST = [] # 全局好友列表缓存，仍会更新

# 用于管理特定请求的响应
# key: echo (str), value: (threading.Event, list_for_result)
pending_friend_list_requests: dict[str, tuple[threading.Event, list]] = {}

def on_message(ws, message):
    """处理收到的WebSocket消息"""
    print(f"[DEBUG] WebSocket收到消息: {message[:200]}...")
    try:
        msg_data = json.loads(message)
        echo = msg_data.get("echo")

        # 检查是否为待处理的好友列表请求的响应
        if echo and echo in pending_friend_list_requests and msg_data.get("status") == "ok":
            event, result_holder = pending_friend_list_requests.get(echo)
            if event and result_holder is not None: # 确保 event 和 result_holder 都有效
                friend_data = msg_data.get("data", [])
                parsed_friends = [str(friend.get("user_id", friend.get("qid"))) 
                                  for friend in friend_data if friend.get("user_id") or friend.get("qid")]
                result_holder.append(parsed_friends) # 将结果放入共享列表
                event.set() # 通知等待的线程
                # pending_friend_list_requests 中的条目由 get_friend_list 自己清理
                print(f"[INFO] Received friend list for echo: {echo}, {len(parsed_friends)} friends.")
                return # 响应已被特定处理器消耗
            else:
                print(f"[WARN] Echo {echo} found in pending but event/holder missing.")

    except json.JSONDecodeError:
        print(f"[WARN] 收到的消息不是有效的JSON格式: {message[:200]}...")
    except Exception as e:
        print(f"[ERROR] on_message 处理时出错: {e}") # 更通用的错误信息
    
    handle_incoming_message(message) # 交给通用消息处理器

def on_error(ws, error):
    """处理WebSocket错误"""
    print(f"[ERROR] WebSocket错误: {error}")

def on_close(ws, close_status_code, close_msg):
    """处理WebSocket连接关闭"""
    print(f"[INFO] WebSocket连接已关闭 - 状态码: {close_status_code}, 消息: {close_msg}")

def on_open(ws):
    """处理WebSocket连接建立"""
    print("[INFO] WebSocket连接已建立")

def init_ws():
    """初始化WebSocket连接"""
    global ws_app
    
    ws_url = CONFIG["qqbot"]["ws_url"]
    token = CONFIG["qqbot"]["token"]
    print(f"[INFO] 正在连接WebSocket服务器: {ws_url}")
    
    try:
        # 添加token到headers
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        ws_app = websocket.WebSocketApp(
            ws_url,
            header=headers,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )
        
        wst = threading.Thread(target=ws_app.run_forever)
        wst.daemon = True
        wst.start()
        print("[INFO] WebSocket客户端线程已启动")
        
    except Exception as e:
        print(f"[ERROR] 初始化WebSocket连接失败: {e}")
        raise

def send_ws_message(data):
    """发送WebSocket消息"""
    global ws_app
    
    if not ws_app:
        print("[ERROR] WebSocket未初始化")
        return
        
    try:
        message = json.dumps(data)
        print(f"[DEBUG] 发送WebSocket消息: {message[:200]}...")  # 只打印前200个字符
        ws_app.send(message)
    except Exception as e:
        print(f"[ERROR] 发送WebSocket消息失败: {e}")

def set_input_status(user_id):
    """设置输入状态"""
    data = {
        "action": "send_private_msg",
        "params": {
            "user_id": user_id,
            "message": "[CQ:typing]"
        }
    }
    send_ws_message(data)

def send_poke(group_id: str, user_id: str):
    """发送群聊戳一戳"""
    print(f"[DEBUG] 准备发送戳一戳到群 {group_id} 的用户 {user_id}")
    data = {
        "action": "group_poke",
        "params": {
            "group_id": int(group_id), # 确保是整数
            "user_id": int(user_id)  # 确保是整数
        }
    }
    send_ws_message(data)

def get_friend_list(timeout: float = 10.0) -> Optional[list[str]]:
    """获取好友列表（同步阻塞，带超时）""" 
    global FRIEND_LIST, pending_friend_list_requests
    
    echo = f"get_friend_list_{time.time()}_{random.randint(0, 100000)}"
    event = threading.Event()
    result_holder = [] # 使用 list 来在线程间传递结果

    pending_friend_list_requests[echo] = (event, result_holder)

    print(f"[INFO] 请求好友列表 (echo: {echo})...")
    request_data = {
        "action": "get_friend_list",
        "params": {},
        "echo": echo
    }
    send_ws_message(request_data)

    try:
        if event.wait(timeout=timeout):
            if result_holder: # 确保 result_holder 中有数据
                friends = result_holder[0]
                print(f"[INFO] 成功获取好友列表 (echo: {echo}), 共 {len(friends)} 个好友.")
                FRIEND_LIST = friends # 更新全局缓存
                return friends
            else:
                # Event 被设置了，但 result_holder 是空的，这不应该发生
                print(f"[ERROR] 获取好友列表响应异常 (echo: {echo}): Event set, but no result.")
                return None
        else:
            print(f"[WARN] 获取好友列表超时 (echo: {echo}, timeout: {timeout}s). unresponsive ws? Or action not supported?")
            return None
    finally:
        # 清理
        if echo in pending_friend_list_requests:
            del pending_friend_list_requests[echo]
