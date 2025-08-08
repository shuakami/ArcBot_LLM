import logging
import os
import json
from logging.handlers import RotatingFileHandler
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.logging import RichHandler
from config import config

# ==================================================================================================
# 1. 初始化
# ==================================================================================================

log = logging.getLogger("arcbot")
console = Console(soft_wrap=True)

# ==================================================================================================
# 2. 集中化配置
# ==================================================================================================

def setup_logging():
    """
    根据配置文件设置日志记录器。
    这个函数应该在应用启动时被调用一次。
    """
    is_debug_mode = config.get("debug", False)
    log_config = config.get("logging", {})
    
    # 检查全局 debug 标志，如果为 true, 则强制使用 DEBUG 级别
    if is_debug_mode:
        log_level_str = "DEBUG"
    else:
        log_level_str = log_config.get("log_level", "INFO").upper()
        
    log_file_path = log_config.get("log_file", "logs/arcbot.log")

    log_level = getattr(logging, log_level_str, logging.INFO)
    
    log.setLevel(log_level)

    if log.hasHandlers():
        log.handlers.clear()
        
    log.propagate = False

    # --- 控制台 Handler (RichHandler) ---
    console_handler = RichHandler(
        console=console,
        markup=True,
        rich_tracebacks=True,
        show_path=False,
        log_time_format="[%X]"
    )
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(console_handler)

    # --- 文件 Handler (RotatingFileHandler) ---
    try:
        log_dir = os.path.dirname(log_file_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file_path, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8'
        )
        file_formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)-8s] %(name)s:%(funcName)s:%(lineno)d - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        log.addHandler(file_handler)

    except Exception as e:
        log.error(f"Failed to set up file logging to {log_file_path}: {e}")

# ==================================================================================================
# 3. 特定格式的输出函数
# ==================================================================================================

def log_received_message(data: dict):
    """以美观的面板格式打印接收到的消息"""
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title="[bold green]Received Message[/bold green]", border_style="green", expand=False))

def log_sent_message(data: dict):
    """以美观的面板格式打印发送的消息"""
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title="[bold blue]Sent Message[/bold blue]", border_style="blue", expand=False))

def log_llm_context(context: list):
    """美观地打印发送给LLM的上下文"""
    content_str = ""
    for msg in context:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        color = "white"
        if role == "system":
            color = "magenta"
            content_str += f"[bold {color}]System Prompt[/bold {color}]\n---\n{content}\n---\n\n"
        else:
            if role == "user":
                color = "green"
            elif role == "assistant":
                color = "cyan"
            content_str += f"[bold {color}]{role.upper()}[/bold {color}]\n{content}\n\n"
    console.print(Panel(content_str.strip(), title="[bold yellow]Final Context to AI[/bold yellow]", border_style="yellow", expand=False))
