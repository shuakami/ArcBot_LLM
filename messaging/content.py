"""
群聊消息内容解析与富媒体处理工具
- 支持图片、表情包检测与描述
- 可扩展更多类型
"""
from typing import Dict, Any, List
from llm_api import get_ai_response_with_image
from config import CONFIG
import os
import requests
import tempfile

def describe_image(image_source: str, image_type: str = "url") -> str:
    """
    识图接口：根据图片来源(URL或路径)返回描述。
    """
    print(f"[DEBUG] describe_image: source='{image_source}', type='{image_type}'")
    prompt_path = os.path.join(os.path.dirname(__file__), '../config/image_system_prompt.txt')
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            system_prompt = f.read().strip()
    except Exception as e:
        system_prompt = "请用中文描述这张图片的内容。"
    # 构造 LLM 对话
    conversation = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "请用中文描述这张图片的内容。"}
    ]
    try:
        desc = get_ai_response_with_image(conversation, image=image_source, image_type=image_type)
        print(f"[DEBUG] describe_image: Success, desc='{str(desc)[:100]}...' ")
        # 兼容 desc 为 list 或 str
        desc_text = None
        if isinstance(desc, list):
            if desc and isinstance(desc[0], dict) and 'text' in desc[0]:
                desc_text = desc[0]['text']
            else:
                desc_text = str(desc)
        elif isinstance(desc, str):
            desc_text = desc
        else:
            desc_text = str(desc)
        return f"[图片内容描述: {desc_text.strip()}]"
    except Exception as e:
        print(f"[ERROR] describe_image: Failed, error='{str(e)}'")
        return f"[图片内容描述获取失败: {str(e)}]"

def parse_group_message_content(msg_dict: Dict[str, Any]) -> str:
    """
    解析群聊消息内容，按原始顺序拼接图片/表情包描述和用户文本。
    - 只有在遇到以 prefix 开头的文本段之后，才对后续的 image/mface 进行识别；
    - 识别结果与原有段落顺序保持一致，确保最前面仍是带 # 的文本，方便后续去除前缀。
    """
    message_segments: List[Dict[str, Any]] = msg_dict.get("message", [])
    output_parts: List[str] = []
    temp_files_to_delete: List[str] = []
    should_describe_images = False
    reply_prefix = CONFIG["qqbot"].get("group_prefix", "#")

    for seg in message_segments:
        seg_type = seg.get("type")
        data = seg.get("data", {})
        temp_file_path = None

        # 文本段：检查前缀并直接加入输出
        if seg_type == "text":
            text = data.get("text", "").strip()
            print(f"[DEBUG] parse_group_message: Found text: '{text}'")
            if text.startswith(reply_prefix):
                should_describe_images = True
            output_parts.append(text)

        # 图片或表情包段
        elif seg_type in ("image", "mface"):
            print(f"[DEBUG] parse_group_message: Found {seg_type}, data='{data}'")
            # 如果尚未检测到前缀，则只放占位符
            if not should_describe_images:
                if seg_type == "image":
                    output_parts.append("[图片]")
                else:
                    summary = data.get("summary")
                    output_parts.append(f"[表情包: {summary}]" if summary else "[表情包]")
                continue

            # 开始识别图片
            image_source_path = None
            is_temp_file = False
            file_path = data.get("file")
            url = data.get("url")

            # 1. 优先使用本地 file 字段
            if file_path and os.path.exists(file_path):
                image_source_path = file_path
                print(f"[DEBUG] parse_group_message: Using local file path: {image_source_path}")
            else:
                # 2. 下载 URL
                if url:
                    print(f"[DEBUG] parse_group_message: Downloading from URL: {url}")
                    try:
                        response = requests.get(url, stream=True, timeout=10)
                        response.raise_for_status()
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as tmpf:
                            for chunk in response.iter_content(chunk_size=8192):
                                tmpf.write(chunk)
                            temp_file_path = tmpf.name
                            temp_files_to_delete.append(temp_file_path)
                            image_source_path = temp_file_path
                            is_temp_file = True
                            print(f"[DEBUG] parse_group_message: Downloaded to temp file: {image_source_path}")
                    except Exception as e:
                        print(f"[ERROR] 下载或保存图片失败: {e}")

            # 3. 调用识别接口并加入输出
            if image_source_path:
                desc = describe_image(image_source_path, image_type="file")
                if seg_type == "image":
                    output_parts.append(desc)
                else:
                    summary = data.get("summary")
                    mface_part = f"[表情包: {summary}] {desc}" if summary else desc
                    output_parts.append(mface_part)

        # QQ 原生表情
        elif seg_type == "face":
            face_id = data.get("id")
            if face_id:
                output_parts.append(f"[QQ表情:{face_id}]")

        # 其他类型直接忽略（或可扩展）
        else:
            continue

    # 清理所有本次创建的临时文件
    for fpath in temp_files_to_delete:
        try:
            os.remove(fpath)
        except OSError as e:
            print(f"[ERROR] 删除临时文件失败: {fpath}, Error: {e}")

    return " ".join(output_parts).strip()
