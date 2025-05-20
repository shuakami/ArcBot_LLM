from logger import setup_logging, get_logger # Import new logging functions
# Note: logger.py no longer contains init_db, assuming it's handled elsewhere or not needed for this task.
# If init_db is still needed, it should be imported from its correct new location if moved,
# or this line will cause an error. For now, I will comment it out as per the logger.py content.
# from logger import init_db 
from utils.db_logger import init_db # Assuming db logging is now in utils.db_logger

from napcat.post import init_ws
from utils.group_activity import group_activity_manager
from llm import process_conversation
import time
import updater
import threading

def main():
    # Setup logging as early as possible
    setup_logging() # Using default level, can be customized e.g., setup_logging(level=logging.DEBUG)
    logger = get_logger(__name__) # Get logger for main.py

    # 检查更新（异步）
    # updater.py now uses logging, so its output will go through the new system.
    threading.Thread(target=updater.check_and_update, daemon=True).start()

    # 初始化消息记录数据库 (assuming init_db is from utils.db_logger)
    logger.info("🚀 初始化数据库...")
    try:
        init_db() # This was from the original logger.py, ensure it's correctly refactored
        logger.info("数据库初始化完成。")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        logger.exception("Exception during database initialization", exc_info=True)
        # Decide if the application should exit if DB init fails. For now, it continues.

    # 初始化 WebSocket 连接
    logger.info("🚀 初始化 WebSocket 连接...")
    init_ws() # Assuming init_ws handles its own logging or doesn't need explicit logging here
    
    # 初始化群活跃度管理器
    logger.info("🚀 初始化群活跃度管理器...")
    group_activity_manager.init_process_conversation(process_conversation)
    
    logger.info("✅ 初始化完成，主程序运行中...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("主程序被用户中断。正在关闭...")
    except Exception as e:
        logger.critical(f"主循环发生未捕获的致命错误: {e}", exc_info=True)
    finally:
        logger.info("主程序结束。")


if __name__ == "__main__":
    main()
