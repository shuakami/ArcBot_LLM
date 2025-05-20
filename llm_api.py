import json
import requests
import base64
from config import CONFIG
import requests # Ensure requests is imported for specific exceptions
import json # Ensure json is imported for specific exceptions

from logger import get_logger
logger = get_logger(__name__)

def get_ai_response(conversation):
    """
    调用 AI 接口，基于 conversation 内容进行流式返回。
    参数:
      conversation: 包含对话上下文消息的列表，格式符合 AI 接口要求
    返回:
      通过 yield 分段返回 AI 回复内容；如果遇到错误则抛出异常。
    """
    logger.debug(f"准备调用AI接口，对话上下文包含 {len(conversation)} 条消息")
    
    headers = {
        "Authorization": f"Bearer {CONFIG['ai']['token']}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": CONFIG["ai"]["model"],
        "messages": conversation,
        "stream": True
    }
    
    api_url = CONFIG["ai"]["api_url"]
    logger.debug(f"发送请求到 {api_url}")

    try:
        response = requests.post(api_url, headers=headers, json=payload, stream=True, timeout=CONFIG.get("ai_timeout", 60)) # Added timeout
        response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)
    except requests.exceptions.HTTPError as e_http:
        error_msg = f"AI接口调用失败 (HTTP错误): {e_http.response.status_code} - {e_http.response.reason}. Response: {e_http.response.text}"
        logger.error(error_msg)
        raise Exception(error_msg) from e_http
    except requests.exceptions.ConnectionError as e_conn:
        error_msg = f"AI接口调用失败 (网络连接错误): {e_conn}"
        logger.error(error_msg)
        raise Exception(error_msg) from e_conn
    except requests.exceptions.Timeout as e_timeout:
        error_msg = f"AI接口调用失败 (请求超时): {e_timeout}"
        logger.error(error_msg)
        raise Exception(error_msg) from e_timeout
    except requests.exceptions.RequestException as e_req: # Catch other request-related errors
        error_msg = f"AI接口调用失败 (请求异常): {e_req}"
        logger.error(error_msg)
        raise Exception(error_msg) from e_req
    except Exception as e_gen: # Generic fallback for other errors during request setup
        error_msg = f"AI接口调用前发生未知错误: {e_gen}"
        logger.exception(error_msg, exc_info=True)
        raise Exception(error_msg) from e_gen

    logger.debug("开始接收流式响应")
    buffer = ""
    try:
        for line in response.iter_lines(decode_unicode=True):
        line = line.strip() # 先去除两端空白
        if not line:
            continue # 跳过空行

        # 严格检查是否为 SSE 数据或结束标记
            line = line.strip() # 先去除两端空白
            if not line:
                continue # 跳过空行

            # 严格检查是否为 SSE 数据或结束标记
            if line.startswith("data:"):
                line_data = line[len("data:"):].strip()
                if line_data == "[DONE]":
                    logger.debug("收到流式响应结束标记 [DONE]")
                    break # 正常结束
                try:
                    data = json.loads(line_data)
                    if CONFIG.get("debug_llm", False): # Use a more specific debug flag
                        logger.debug(f"Stream Data: {repr(line_data)}")
                except json.JSONDecodeError as e_json:
                    logger.error(f"解析流式 JSON 响应出错: {e_json}, line内容: {repr(line_data)}")
                    continue # Skip this malformed line
                
                # 提取内容
                delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if delta:
                    delta = delta.replace("\r\n", "\n")
                    buffer += delta
                    # Yielding logic for [send] or newline
                    while "[send]" in buffer or (buffer.endswith("\n") and "\n" in buffer.strip()): # ensure \n is not just trailing whitespace
                        if "[send]" in buffer:
                            part, buffer = buffer.split("[send]", 1)
                        else: # split by newline
                            part, buffer = buffer.split("\n", 1)
                        
                        part = part.strip() # Strip part before checking if it's empty
                        if part:
                            logger.debug(f"发送回复片段: {part[:50].replace(chr(10), '/n')}...") 
                            yield part
            elif line == "[DONE]": # Handle [DONE] if it's not prefixed with "data:"
                logger.debug("收到独立的 [DONE] 标记")
                break
            else:
                # Log lines that are not empty and not "data: ..." might indicate issues or non-SSE compliant streams
                logger.warning(f"收到非 SSE 标准的行: {repr(line)}")

    except Exception as e_stream:
        logger.exception("处理流式响应时发生错误", exc_info=True)
        raise Exception(f"处理AI流式响应时出错: {e_stream}") from e_stream
    finally:
        response.close() # Ensure the response is closed

    # 输出剩余内容
    if buffer.strip():
        final_part = buffer.strip()
        logger.debug(f"发送最后的回复片段: {final_part[:50].replace(chr(10), '/n')}...")
        yield final_part
    
    logger.debug("AI接口调用完成")

def get_ai_response_with_image(conversation, image=None, image_type="url"):
    """
    自动判断API类型：
    - 如果image_ai.api_url包含'dashscope.aliyuncs.com'，用dashscope SDK
    - 否则用OpenAI兼容HTTP请求
    """
    api_url = CONFIG['image_ai']['api_url']
    token = CONFIG['image_ai']['token']
    model = CONFIG['image_ai']['model']
    logger.debug(f"get_ai_response_with_image: Using API URL='{api_url}', Model='{model}'")

    # 自动处理本地图片为base64
    original_image_type = image_type
    if image_type == "file" and image:
        logger.debug(f"get_ai_response_with_image: Converting file to base64: '{image}'")
        try:
            with open(image, "rb") as f:
                image_data = base64.b64encode(f.read()).decode()
            image_type = "base64" # Update image_type
            image = image_data # Update image content to base64 string
            logger.debug("get_ai_response_with_image: File converted to base64 successfully.")
        except FileNotFoundError:
            logger.error(f"get_ai_response_with_image: Image file not found: {image}")
            raise Exception(f"图片文件未找到: {image}")
        except IOError as e_io:
            logger.error(f"get_ai_response_with_image: Failed to read image file '{image}': {e_io}")
            raise Exception(f"读取图片文件失败: {e_io}")
        except Exception as e_b64: # Catch other potential errors during base64 conversion
             logger.exception(f"get_ai_response_with_image: Failed to convert file to base64: {e_b64}", exc_info=True)
             raise Exception(f"处理本地图片文件失败: {e_b64}")

    logger.debug(f"get_ai_response_with_image: Final image_type='{image_type}'")

    # 判断是否为阿里云DashScope
    if "dashscope.aliyuncs.com" in api_url:
        try:
            import dashscope
        except ImportError:
             logger.error("DashScope library not found. Please install with: pip install dashscope")
             raise Exception("未检测到dashscope库，请先安装：pip install dashscope")
        
        dashscope.api_key = token
        messages = []
        for msg in conversation:
            if msg["role"] == "user" and image:
                content = []
                if "content" in msg:
                    if isinstance(msg["content"], str):
                        content.append({"text": msg["content"]})
                    elif isinstance(msg["content"], list):
                        content.extend(msg["content"])
                if image_type == "base64":
                    content.append({"image": f"data:image/png;base64,{image}"})
                else:
                    content.append({"image": image})
                content_list = []
                # Handle if original content is string or list
                if "content" in msg:
                    if isinstance(msg["content"], str):
                        content_list.append({"text": msg["content"]})
                    elif isinstance(msg["content"], list): # If content is already a list of parts
                        content_list.extend(msg["content"]) 
                
                if image_type == "base64":
                    content_list.append({"image": f"data:image/png;base64,{image}"})
                else: # Assuming URL
                    content_list.append({"image": image})
                messages.append({"role": msg["role"], "content": content_list})
            else:
                messages.append(msg)
        
        logger.debug(f"DashScope Request: model='{model}', messages_structure={[m['role'] for m in messages]}")
        try:
            # Ensure timeout is configurable for DashScope as well
            response = dashscope.MultiModalConversation.call(
                model=model,
                messages=messages,
                timeout=CONFIG.get("image_ai_timeout", 120) # Example timeout
            )
            logger.debug(f"DashScope Response Status: {response.status_code if hasattr(response, 'status_code') else 'N/A'}") # status_code might not be present on all responses
            if hasattr(response, 'status_code') and response.status_code == 200:
                content = response.output.choices[0].message.content
                logger.debug(f"DashScope Response Success, content='{str(content)[:100]}...'")
                return content
            else:
                error_code = response.code if hasattr(response, 'code') else 'UnknownCode'
                error_message = response.message if hasattr(response, 'message') else 'UnknownError'
                logger.error(f"DashScope API Call Failed: Code={error_code}, Message={error_message}")
                raise Exception(f"调用DashScope失败: {error_code}, {error_message}")
        except Exception as e_dash: # Catch any exception from DashScope call
            logger.exception(f"Calling DashScope API failed: {e_dash}", exc_info=True)
            raise Exception(f"调用DashScope API时发生错误: {e_dash}")
    else:
        # OpenAI兼容HTTP请求
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        messages = list(conversation)
        if image:
            image_obj = None
            if image_type == "base64":
                image_obj = {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}"}}
            else:
                image_obj = {"type": "image_url", "image_url": {"url": image}}
            if messages and messages[-1].get("role") == "user":
                if "content" in messages[-1] and isinstance(messages[-1]["content"], list):
                    messages[-1]["content"].append(image_obj)
                elif "content" in messages[-1]:
                    # Ensure content is a list
                    if not isinstance(processed_messages[i].get("content"), list):
                        current_content = processed_messages[i].get("content", "")
                        processed_messages[i]["content"] = [{"type": "text", "text": current_content}] if current_content else []
                    processed_messages[i]["content"].append(image_obj)
                    found_user_message = True
                    break
            if not found_user_message: # If no user message to append to, create a new one
                processed_messages.append({"role": "user", "content": [image_obj]})

        logger.debug(f"OpenAI-Compat Request: url='{api_url}', model='{model}', messages_structure={[m['role'] for m in processed_messages]}")
        payload = {
            "model": model,
            "messages": processed_messages,
            "stream": False # Assuming non-stream for this function
        }
        try:
            # Add timeout to OpenAI compatible requests
            response = requests.post(api_url, headers=headers, json=payload, timeout=CONFIG.get("image_ai_timeout", 120))
            response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)
            
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            logger.debug(f"OpenAI-Compat Response Success, content='{str(content)[:100]}...'")
            return content
        except requests.exceptions.HTTPError as e_http:
            error_msg = f"OpenAI-Compat API Call Failed (HTTP错误): {e_http.response.status_code} - {e_http.response.reason}. Response: {e_http.response.text}"
            logger.error(error_msg)
            raise Exception(error_msg) from e_http
        except requests.exceptions.ConnectionError as e_conn:
            error_msg = f"OpenAI-Compat API Call Failed (网络连接错误): {e_conn}"
            logger.error(error_msg)
            raise Exception(error_msg) from e_conn
        except requests.exceptions.Timeout as e_timeout:
            error_msg = f"OpenAI-Compat API Call Failed (请求超时): {e_timeout}"
            logger.error(error_msg)
            raise Exception(error_msg) from e_timeout
        except requests.exceptions.RequestException as e_req: # Catch other request-related errors
            error_msg = f"OpenAI-Compat API Call Failed (请求异常): {e_req}"
            logger.error(error_msg)
            raise Exception(error_msg) from e_req
        except json.JSONDecodeError as e_json:
            logger.error(f"OpenAI-Compat API: Failed to parse JSON response: {e_json}. Response text: {response.text if 'response' in locals() else 'N/A'}")
            raise Exception(f"解析OpenAI兼容API响应失败: {e_json}") from e_json
        except Exception as e_gen: # Generic fallback
            logger.exception(f"Calling OpenAI-Compat API failed: {e_gen}", exc_info=True)
            raise Exception(f"调用OpenAI兼容API时发生未知错误: {e_gen}") from e_gen