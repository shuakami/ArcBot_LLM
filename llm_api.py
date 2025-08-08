import json
import requests
import base64
import re
from typing import Iterator, Dict, Any, List

from config import config
from logger import log

# --- 辅助函数 ---

def _encode_image_to_base64(image_path: str) -> str:
    """将图片文件编码为 Base64 字符串。"""
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception as e:
        log.error(f"读取或编码图片文件失败: {e}")
        raise IOError(f"处理本地图片文件失败: {e}") from e

def _stream_response_generator(response: requests.Response) -> Iterator[str]:
    """从流式响应中逐块生成内容。"""
    buffer = ""
    # 正则表达式，用于匹配 [send] 或 [longtext:...] 标记
    # re.DOTALL 使得 '.' 可以匹配包括换行符在内的任意字符
    splitter = re.compile(r'(\[send\]|\[longtext:.*?\])', re.DOTALL)

    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue

        line_data = line[len("data:"):].strip()
        if line_data == "[DONE]":
            break
        
        try:
            data = json.loads(line_data)
            delta = data.get("choices", [{}])[0].get("delta", {}).get("content")
            if not delta:
                continue

            buffer += delta

            # 使用正则表达式进行分割
            parts = splitter.split(buffer)
            
            # parts 会是 [text, separator, text, separator, ...] 的形式
            # 我们需要处理成对的部分
            i = 0
            while i + 1 < len(parts):
                text_part = parts[i]
                separator = parts[i+1]
                
                if text_part.strip():
                    yield text_part.strip()
                
                # 如果分隔符是 longtext，则把它作为一个整体 yield
                if separator.startswith('[longtext:'):
                    yield separator
                
                i += 2
            
            # 剩下的部分放回 buffer
            buffer = parts[-1]

        except json.JSONDecodeError:
            log.warning(f"无法解析流式 JSON 响应: {line_data}")
            continue
        except Exception as e:
            log.error(f"处理流式响应时出错: {e}, line: {line_data}", exc_info=True)
            continue
            
    if buffer.strip():
        yield buffer.strip()

# --- 主要 API 函数 ---

def get_ai_response(conversation: List[Dict[str, Any]]) -> Iterator[str]:
    """调用 AI 接口，并以流式方式返回响应块。"""
    api_url = config["ai"]["api_url"]
    headers = {
        "Authorization": f"Bearer {config['ai']['token']}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": config["ai"]["model"],
        "messages": conversation,
        "stream": True
    }
    
    log.debug(f"向 {api_url} 发送流式请求...")
    try:
        response = requests.post(api_url, headers=headers, json=payload, stream=True, timeout=120)
        response.raise_for_status()
        log.debug("开始接收流式响应...")
        yield from _stream_response_generator(response)
        log.debug("AI接口调用完成")
    except requests.RequestException as e:
        log.error(f"AI接口请求失败: {e}")
        raise ConnectionError(f"AI接口请求失败: {e}") from e

def get_ai_response_with_image(
    conversation: List[Dict[str, Any]], image: str, image_type: str = "url"
) -> str:
    """调用多模态AI接口，处理包含图片的消息。"""
    api_url = config['image_ai']['api_url']
    token = config['image_ai']['token']
    model = config['image_ai']['model']
    
    if image_type == "file":
        image = _encode_image_to_base64(image)
        image_type = "base64"

    if "dashscope.aliyuncs.com" in api_url:
        return _call_dashscope_api(conversation, image, image_type, token, model)
    else:
        return _call_openai_compatible_api(conversation, image, image_type, token, model, api_url)

# --- 特定 API 的实现 ---

def _build_multimodal_message(
    conversation: List[Dict[str, Any]], image_url: str
) -> List[Dict[str, Any]]:
    """为多模态请求构建消息体。"""
    messages = list(conversation)
    image_content = {"type": "image_url", "image_url": {"url": image_url}}

    # 将图片添加到最后一个用户消息中
    for msg in reversed(messages):
        if msg.get("role") == "user":
            if isinstance(msg.get("content"), list):
                msg["content"].append(image_content)
            else:
                msg["content"] = [
                    {"type": "text", "text": msg.get("content", "")},
                    image_content
                ]
            return messages
    
    # 如果没有用户消息，则创建一个新的
    messages.append({"role": "user", "content": [image_content]})
    return messages

def _call_dashscope_api(
    conversation: List[Dict[str, Any]], image: str, image_type: str, token: str, model: str
) -> str:
    """调用 DashScope (通义千问) 多模态 API。"""
    try:
        import dashscope
    except ImportError:
        raise ImportError("未找到 DashScope 库，请运行 'pip install dashscope'。")
        
    dashscope.api_key = token
    image_url = f"data:image/png;base64,{image}" if image_type == "base64" else image
    messages = _build_multimodal_message(conversation, image_url)

    log.debug(f"DashScope 请求: model='{model}'")
    try:
        response = dashscope.MultiModalConversation.call(model=model, messages=messages)
        if response.status_code == 200:
            return response.output.choices[0].message.content
        else:
            raise ConnectionError(f"DashScope API 调用失败: {response.code}, {response.message}")
    except Exception as e:
        log.error(f"调用 DashScope API 时发生异常: {e}")
        raise ConnectionError(f"调用 DashScope API 失败: {e}") from e

def _call_openai_compatible_api(
    conversation: List[Dict[str, Any]], image: str, image_type: str, token: str, model: str, api_url: str
) -> str:
    """调用兼容 OpenAI 的多模态 API。"""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    image_url = f"data:image/png;base64,{image}" if image_type == "base64" else image
    messages = _build_multimodal_message(conversation, image_url)
    payload = {"model": model, "messages": messages, "stream": False}

    log.debug(f"OpenAI 兼容接口请求: url='{api_url}', model='{model}'")
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except requests.RequestException as e:
        log.error(f"调用 OpenAI 兼容 API 失败: {e}")
        raise ConnectionError(f"调用 OpenAI 兼容 API 失败: {e}") from e
