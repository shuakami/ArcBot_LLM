import json
import websocket
import threading
from config import CONFIG
from napcat.get import handle_incoming_message

ws_app = None

def on_message(ws, message):
    """处理收到的WebSocket消息"""
    print(f"[DEBUG] WebSocket收到消息: {message[:200]}...")  # 只打印前200个字符
    handle_incoming_message(message)

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
