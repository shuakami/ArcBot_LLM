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
import urllib.parse
import ipaddress
from logger import get_logger # Import the new logger

logger = get_logger(__name__) # Get a logger for this module

def describe_image(image_source: str, image_type: str = "url") -> str:
    """
    识图接口：根据图片来源(URL或路径)返回描述。
    """
    logger.debug(f"describe_image: source='{image_source}', type='{image_type}'")
    prompt_path = os.path.join(os.path.dirname(__file__), '../config/image_system_prompt.txt')
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            system_prompt = f.read().strip()
    except FileNotFoundError:
        logger.warning(f"Image system prompt file not found at {prompt_path}. Using default prompt.")
        system_prompt = "请用中文描述这张图片的内容。"
    except Exception as e_file:
        logger.error(f"Error reading image system prompt from {prompt_path}: {e_file}", exc_info=True)
        system_prompt = "请用中文描述这张图片的内容。"
        
    # 构造 LLM 对话
    conversation = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "请用中文描述这张图片的内容。"}
    ]
    try:
        # Assuming get_ai_response_with_image handles its own logging or is already converted
        desc = get_ai_response_with_image(conversation, image=image_source, image_type=image_type)
        logger.debug(f"describe_image: Success, desc='{str(desc)[:100]}...' ")
        # 兼容 desc 为 list 或 str
        desc_text = None
        if isinstance(desc, list):
            if desc and isinstance(desc[0], dict) and 'text' in desc[0]:
                desc_text = desc[0]['text']
            else:
                desc_text = str(desc) # Fallback if structure is not as expected
        elif isinstance(desc, str):
            desc_text = desc
        else:
            desc_text = str(desc) # Fallback for other types
        return f"[图片内容描述: {desc_text.strip()}]"
    except Exception as e:
        logger.error(f"describe_image: Failed, error='{str(e)}'", exc_info=True)
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
            logger.debug(f"parse_group_message: Found text: '{text[:100]}...'") # Log potentially long text carefully
            if text.startswith(reply_prefix):
                should_describe_images = True
            output_parts.append(text)

        # 图片或表情包段
        elif seg_type in ("image", "mface"):
            logger.debug(f"parse_group_message: Found {seg_type}, data='{str(data)[:100]}...'") # Log data carefully
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
                logger.debug(f"parse_group_message: Using local file path: {image_source_path}")
            else:
                # 2. 下载 URL
                if url:
                    logger.debug(f"parse_group_message: Validating URL: {url}")
                    try:
                        parsed_url = urllib.parse.urlparse(url)
                        if parsed_url.scheme not in ('http', 'https'):
                            raise ValueError("Invalid URL scheme. Only HTTP/HTTPS are allowed.")
                        
                        hostname = parsed_url.hostname
                        if hostname:
                            try:
                                ip_addr = ipaddress.ip_address(hostname)
                                if ip_addr.is_private or ip_addr.is_loopback:
                                    raise ValueError(f"URL hostname '{hostname}' is a private or loopback IP address.")
                            except ValueError: # Catches if hostname is not a valid IP address string for ipaddress.ip_address()
                                # This means it's likely a domain name, which is fine.
                                # logger.debug(f"Hostname '{hostname}' is not an IP address, assuming valid domain or to be handled by whitelist.")
                                pass 
                        else:
                            raise ValueError("URL has no hostname.")

                        # TODO: Consider adding a domain whitelist check here for further security.
                        # Example: 
                        # allowed_domains = CONFIG.get("allowed_image_domains", [])
                        # if parsed_url.hostname not in allowed_domains:
                        #     raise ValueError(f"Domain {parsed_url.hostname} not in allowed whitelist.")

                        logger.debug(f"parse_group_message: Downloading from URL: {url}")
                        response = requests.get(url, stream=True, timeout=10)
                        response.raise_for_status()
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as tmpf:
                            for chunk in response.iter_content(chunk_size=8192):
                                tmpf.write(chunk)
                            temp_file_path = tmpf.name
                            temp_files_to_delete.append(temp_file_path)
                            image_source_path = temp_file_path
                            is_temp_file = True # Flag that this file is temporary
                            logger.debug(f"parse_group_message: Downloaded to temp file: {image_source_path}")
                    except ValueError as ve: 
                        logger.error(f"URL validation failed for {url}: {ve}")
                        output_parts.append("[图片URL无效或不安全]")
                    except requests.exceptions.HTTPError as e_http:
                        logger.error(f"Downloading image from {url} failed (HTTP Error): {e_http.response.status_code} - {e_http.response.reason}")
                        output_parts.append("[图片下载失败: 服务器错误]")
                    except requests.exceptions.ConnectionError as e_conn:
                        logger.error(f"Downloading image from {url} failed (Connection Error): {e_conn}")
                        output_parts.append("[图片下载失败: 网络连接问题]")
                    except requests.exceptions.Timeout as e_timeout:
                        logger.error(f"Downloading image from {url} failed (Timeout): {e_timeout}")
                        output_parts.append("[图片下载超时]")
                    except requests.exceptions.RequestException as e_req: 
                        logger.error(f"Downloading image from {url} failed (General Request Error): {e_req}", exc_info=True)
                        output_parts.append("[图片下载失败]")
                    except Exception as e_other: 
                        logger.error(f"Processing image URL {url} failed with an unexpected error: {e_other}", exc_info=True)
                        output_parts.append("[图片处理异常]")
                else: # if no URL
                    if seg_type == "image":
                        output_parts.append("[图片URL缺失]")
                    # For mface, if no URL and no file, it might just be a summary
                    elif data.get("summary"):
                         output_parts.append(f"[表情包: {data.get('summary')}]")
                    else:
                        output_parts.append("[表情包URL缺失]")


            # 3. 调用识别接口并加入输出 (only if image_source_path is set)
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
            # Only attempt to remove if it was marked as a temporary file from URL download
            # This check might be redundant if temp_files_to_delete only ever contains such files
            # but added for clarity/safety if logic changes.
            # if is_temp_file and fpath == temp_file_path: # This check is flawed, simply iterate and remove
            os.remove(fpath)
            logger.debug(f"Successfully deleted temporary file: {fpath}")
        except FileNotFoundError:
            logger.warning(f"Attempted to delete temporary file, but it was not found: {fpath}")
        except OSError as e_os:
            logger.error(f"删除临时文件失败: {fpath}, Error: {e_os}", exc_info=True)
        except Exception as e_del: # Catch any other unexpected error during deletion
            logger.error(f"删除临时文件时发生未知错误: {fpath}, Error: {e_del}", exc_info=True)


    return " ".join(output_parts).strip()
