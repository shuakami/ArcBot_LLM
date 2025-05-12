from logger import init_db
from napcat.post import init_ws
from utils.group_activity import group_activity_manager
from llm import process_conversation
import time
import updater
import threading

def main():
    # 检查更新（异步）
    threading.Thread(target=updater.check_and_update, daemon=True).start()

    # 初始化消息记录数据库
    print("🚀 初始化数据库...")
    init_db()
    # 初始化 WebSocket 连接（注意：get.py 中会自动处理消息接收）
    print("🚀 初始化 WebSocket 连接...")
    init_ws()
    
    # 初始化群活跃度管理器
    print("🚀 初始化群活跃度管理器...")
    group_activity_manager.init_process_conversation(process_conversation)
    
    print("✅ 初始化完成，主程序运行中...")
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
