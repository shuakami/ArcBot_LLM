import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from llm_api import get_ai_response_with_image
from config import CONFIG

# 动态设置 image_ai 配置
CONFIG["image_ai"] = {
    "api_url": "https://dashscope.aliyuncs.com/api/v1/services/vision/text-image-generation/generation",
    "token": "",
    "model": "qwen-vl-plus"
}

IMAGE_PATH = r"E:\Users\Shuakami\Pictures\b_1a4986c89ad467790613b670c9856082.jpg"

if __name__ == "__main__":
    # 构造对话
    system_prompt = "请用中文简要描述这张图片的内容。"
    conversation = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "请描述图片。"}
    ]
    print("正在调用多模态接口识别图片...")
    try:
        result = get_ai_response_with_image(conversation, image=IMAGE_PATH, image_type="file")
        print("识别结果：")
        print(result)
    except Exception as e:
        print("识别失败：", e) 