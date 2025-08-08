
def extract_text_from_message(msg_dict):
    text = ""
    for seg in msg_dict.get("message", []):
        if seg.get("type") == "text":
            text += seg.get("data", {}).get("text", "")
    return text

# @shuakami
def estimate_tokens(text):
    """基于字符数估算 Token 数，平均 1.5 字符约为 1 Token（虽然tokenizer更准确但是要挂梯子来下文件"""
    if not isinstance(text, str):
        return 0
    estimated_tokens = (len(text) * 2) // 3 + 1
    return estimated_tokens