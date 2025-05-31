import json
import requests
import base64
from config import CONFIG

def get_ai_response(conversation):
    """
    调用 AI 接口，基于 conversation 内容进行流式返回。
    参数:
      conversation: 包含对话上下文消息的列表，格式符合 AI 接口要求
    返回:
      通过 yield 分段返回 AI 回复内容；如果遇到错误则抛出异常。
    """
    print(f"[DEBUG] 准备调用AI接口，对话上下文包含 {len(conversation)} 条消息")
    
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
    print(f"[DEBUG] 发送请求到 {api_url}")
    response = requests.post(api_url, headers=headers, json=payload, stream=True)
    
    if response.status_code != 200:
        error_msg = f"AI接口调用失败, 状态码：{response.status_code}, {response.text}"
        print(f"[ERROR] {error_msg}")
        raise Exception(error_msg)

    print("[DEBUG] 开始接收流式响应")
    buffer = ""
    for line in response.iter_lines(decode_unicode=True):
        line = line.strip() # 先去除两端空白
        if not line:
            continue # 跳过空行

        # 严格检查是否为 SSE 数据或结束标记
        if line.startswith("data:"):
            line_data = line[len("data:"):].strip()
            if line_data == "[DONE]":
                print("[DEBUG] 收到流式响应结束标记")
                break # 正常结束
            try:
                data = json.loads(line_data)
                if CONFIG["debug"]:
                    print(f"[DEBUG] Stream Data: {repr(line_data)}")
            except json.JSONDecodeError as e:
                # 仅记录 JSON 解析错误，忽略非 JSON 行
                print(f"[ERROR] 解析流式 JSON 响应出错: {e}, line内容: {repr(line_data)}")
                continue
            except Exception as e:
                print(f"[ERROR] 处理流式响应时发生未知错误: {e}, line内容: {repr(line_data)}")
                continue
            
            # 提取内容
            delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
            if delta:
                delta = delta.replace("\r\n", "\n")
                buffer += delta
                
                while True:
                    part_to_yield = None
                    processed_something = False

                    if "[send]" in buffer:
                        part, buffer = buffer.split("[send]", 1)
                        part_to_yield = part.strip()
                        processed_something = True
                    elif "\n" in buffer:
                        potential_part = buffer.split("\n", 1)[0]
                        last_open_longtext = potential_part.rfind("[longtext:")
                        is_inside_longtext = False
                        if last_open_longtext != -1:
                            if potential_part.rfind("]") < last_open_longtext:
                                is_inside_longtext = True
                        
                        if is_inside_longtext:
                            break
                        else:
                            if buffer.endswith("\n") or "\n" in buffer:
                                part, buffer = buffer.split("\n", 1)
                                part_to_yield = part.strip()
                                processed_something = True
                            else:
                                break
                    else:
                        break

                    if part_to_yield is not None: 
                         if part_to_yield:
                            print(f"[DEBUG] 发送回复片段: {part_to_yield[:50]}...")
                            yield part_to_yield
                    elif not processed_something:
                        break
        elif line == "[DONE]":
            print("[DEBUG] 收到[DONE]标记")
            break

    # 输出剩余内容
    if buffer.strip():
        final_part = buffer.strip()
        print(f"[DEBUG] 发送最后的回复片段: {final_part[:50]}...") # 只打印前50个字符
        yield final_part
    
    print("[DEBUG] AI接口调用完成")

def get_ai_response_with_image(conversation, image=None, image_type="url"):
    """
    自动判断API类型：
    - 如果image_ai.api_url包含'dashscope.aliyuncs.com'，用dashscope SDK
    - 否则用OpenAI兼容HTTP请求
    """
    api_url = CONFIG['image_ai']['api_url']
    token = CONFIG['image_ai']['token']
    model = CONFIG['image_ai']['model']
    print(f"[DEBUG] get_ai_response_with_image: Using API URL='{api_url}', Model='{model}'")

    # 自动处理本地图片为base64
    original_image_type = image_type
    if image_type == "file" and image:
        print(f"[DEBUG] get_ai_response_with_image: Converting file to base64: '{image}'")
        try:
            with open(image, "rb") as f:
                image = base64.b64encode(f.read()).decode()
            image_type = "base64"
            print("[DEBUG] get_ai_response_with_image: File converted to base64 successfully.")
        except Exception as e:
             print(f"[ERROR] get_ai_response_with_image: Failed to read or encode file: {e}")
             raise Exception(f"处理本地图片文件失败: {e}")

    print(f"[DEBUG] get_ai_response_with_image: Final image_type='{image_type}'")

    # 判断是否为阿里云DashScope
    if "dashscope.aliyuncs.com" in api_url:
        try:
            import dashscope
        except ImportError:
             print("[ERROR] DashScope library not found. Please install with: pip install dashscope")
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
                messages.append({"role": msg["role"], "content": content})
            else:
                messages.append(msg)
        print(f"[DEBUG] DashScope Request: model='{model}', messages_structure={[m['role'] for m in messages]}")
        try:
            response = dashscope.MultiModalConversation.call(
                model=model,
                messages=messages
            )
            print(f"[DEBUG] DashScope Response Status: {response.status_code}")
            if response.status_code == 200:
                content = response.output.choices[0].message.content
                print(f"[DEBUG] DashScope Response Success, content='{content[:100]}...'")
                return content
            else:
                print(f"[ERROR] DashScope API Call Failed: Code={response.code}, Message={response.message}")
                raise Exception(f"调用失败: {response.code}, {response.message}")
        except Exception as e:
            print(f"[ERROR] Calling DashScope API failed: {str(e)}")
            raise Exception(f"调用DashScope API失败: {str(e)}")
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
                    messages[-1]["content"] = [messages[-1]["content"], image_obj]
                else:
                    messages[-1]["content"] = [image_obj]
            else:
                messages.append({"role": "user", "content": [image_obj]})
        print(f"[DEBUG] OpenAI-Compat Request: url='{api_url}', model='{model}', messages_structure={[m['role'] for m in messages]}")
        payload = {
            "model": model,
            "messages": messages,
            "stream": False
        }
        try:
            response = requests.post(api_url, headers=headers, json=payload)
            print(f"[DEBUG] OpenAI-Compat Response Status: {response.status_code}")
            if response.status_code != 200:
                 print(f"[ERROR] OpenAI-Compat API Call Failed: Status={response.status_code}, Response Text='{response.text}'")
                 raise Exception(f"AI接口调用失败, 状态码：{response.status_code}, {response.text}")
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"[DEBUG] OpenAI-Compat Response Success, content='{content[:100]}...'")
            return content
        except Exception as e:
            print(f"[ERROR] Calling OpenAI-Compat API failed: {str(e)}")
            raise Exception(f"调用OpenAI兼容API失败: {str(e)}") 