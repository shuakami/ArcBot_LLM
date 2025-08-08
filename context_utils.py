from config import config
from common.text import estimate_tokens
from storage.notebook import DEFAULT_ROLE_KEY
from logger import log

def build_context_within_limit(full_history, active_role: str = DEFAULT_ROLE_KEY):
    max_tokens = config["ai"].get("max_context_tokens", 15000)
    debug_mode = config.get("debug", False)
    context = []
    current_tokens = 0

    system_prompt = None
    if full_history and isinstance(full_history[0], dict) and full_history[0].get("role") == "system":
        system_prompt = full_history[0]
        dialog_history = full_history[1:]
    else:
        dialog_history = full_history

    if system_prompt:
        system_tokens = estimate_tokens(system_prompt.get("content", ""))
        if system_tokens <= max_tokens:
            context.append(system_prompt)
            current_tokens += system_tokens
        else:
            log.warning(f"系统提示过长 ({system_tokens} tokens)，超过最大限制 {max_tokens} tokens，本次请求将不包含系统提示。")
            system_prompt = None

    for message in reversed(dialog_history):
        message_content = message.get("content", "")
        message_tokens = estimate_tokens(message_content)

        if current_tokens + message_tokens > max_tokens and (len(context) > 1 or not system_prompt):
            if debug_mode:
                log.debug(f"因达到Token上限停止构建上下文。当前: {current_tokens}, 新增: {message_tokens}, 上限: {max_tokens}")
            break

        insert_index = 1 if system_prompt else 0
        context.insert(insert_index, message)
        current_tokens += message_tokens
        
        if debug_mode:
            log.debug(f"添加消息 (Tokens: {message_tokens}). 当前上下文Tokens: {current_tokens}, 上下文长度: {len(context)}")

        if current_tokens > max_tokens and len(context) == (2 if system_prompt else 1):
            log.warning(f"最新的消息过长 ({message_tokens} tokens)，可能导致上下文被截断。")
            break

    log.info(f"上下文构建完成: 共 {len(context)} 条消息, 约 {current_tokens} tokens (上限 {max_tokens})。")
    return context
