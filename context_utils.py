from config import CONFIG
from utils.text import estimate_tokens
from utils.notebook import DEFAULT_ROLE_KEY # 引入 default role key

def build_context_within_limit(full_history, active_role: str = DEFAULT_ROLE_KEY):
    """
    根据配置的 max_context_tokens 构建不超过限制的上下文。
    参数:
      full_history: 包含完整对话历史的列表（消息字典），其中第一条消息可能是系统提示
      active_role: 当前激活的角色名称 (或 DEFAULT_ROLE_KEY)
    返回:
      context: 包含的消息列表，token 数量不超过限制
    """
    max_tokens = CONFIG["ai"].get("max_context_tokens", 15000)
    context = []
    current_tokens = 0

    # 分离系统提示和对话历史记录
    system_prompt = None
    dialog_history = []
    # 检查 full_history 是否非空，且第一项是包含 'role' 键的字典 
    if full_history and isinstance(full_history[0], dict) and "role" in full_history[0] and full_history[0]["role"] == "system":
        system_prompt = full_history[0]
        dialog_history = full_history[1:]
    else:
        dialog_history = full_history

    # 如果存在系统提示，则始终保证其在上下文中
    if system_prompt:
        system_tokens = estimate_tokens(system_prompt.get("content", ""))
        if system_tokens <= max_tokens:
            context.append(system_prompt)
            current_tokens += system_tokens
        else:
            print(f"警告：系统提示过长 ({system_tokens} tokens)，超过最大限制 {max_tokens} tokens，本次请求将不包含系统提示。")
            system_prompt = None

    # 从最近的消息开始，倒序添加，直到达到 token 限制
    for message in reversed(dialog_history):
        message_content = message.get("content", "")
        message_tokens = estimate_tokens(message_content)

        # 如果加入当前消息会超过限制，并且已经有内容则停止添加
        if current_tokens + message_tokens > max_tokens and context:
            print(f"[Debug] Stopping context build due to token limit. Current tokens: {current_tokens}, Adding message tokens: {message_tokens}, Max tokens: {max_tokens}")
            break

        # 将消息插入到上下文中；如果存在系统提示，则保证它始终在第一条
        insert_index = 1 if system_prompt else 0
        context.insert(insert_index, message)

        current_tokens += message_tokens

        # 调试输出：检查添加消息后的token数和上下文长度
        print(f"[Debug] Added message (Tokens: {message_tokens}). Current context tokens: {current_tokens}, Context length: {len(context)}")

        if current_tokens > max_tokens and len(context) == (1 if not system_prompt else 2):
            print(f"警告：最新的消息过长 ({message_tokens} tokens)，可能导致上下文被截断。")

    print(f"构建上下文：包含 {len(context)} 条消息，估算 {current_tokens} tokens (上限 {max_tokens})。原始过滤前历史 {len(full_history)} 条。")
    return context 