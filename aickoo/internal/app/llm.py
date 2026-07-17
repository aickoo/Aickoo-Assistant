#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.
"""


from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from langchain_community.embeddings import volcengine
from openai import OpenAI
import json
import aickoo.internal.util.utils as utils
import base64
from aickoo.internal.config import Config
import aickoo.logging as logging
import re

# 全局配置对象
_global_config: Optional[Config] = None
json_block_pattern = re.compile(r"```json\s*([\s\S]*?)\s*```", re.MULTILINE)
think_pattern = re.compile(r'<think>(.*?)</think>', re.IGNORECASE | re.DOTALL)
ansi_pattern = re.compile(r'\x1b\[[0-9;]*m')


def get_deepseek_client() -> Dict:
    """从配置获取 Deepseek 配置"""
    global _global_config
    if _global_config and "deepseek-llm" in _global_config.ai_providers:
        ai_config = _global_config.ai_providers["deepseek-llm"]
        return {
            "api_key": ai_config["api_key"],
            "base_url": ai_config["base_url"],
            "model": ai_config.get("model", "deepseek-reasoner")
        }
    # 默认配置
    logging.error(f"Read Deepseek API key Failed")
    return {"api_key": "", "base_url": "", "model": "deepseek-reasoner"}

def get_volcengine_generate_image_client() -> Dict:
    """从配置获取 Volcengine 图片生成配置"""
    global _global_config
    if _global_config and "volcengine-gen-image" in _global_config.ai_providers:
        ai_config = _global_config.ai_providers["volcengine-gen-image"]
        return {
            "api_key": ai_config["api_key"],
            "base_url": ai_config["base_url"],
            "model": ai_config.get("model", "")
        }
    # 默认配置
    logging.error(f"Read Volcengine generate image API key Failed")
    return {"api_key": "", "base_url": "", "model": ""}

def get_volcengine_image_qa_client() -> Dict:
    """从配置获取 Volcengine 图片问答配置"""
    global _global_config
    if _global_config and "volcengine-image-qa" in _global_config.ai_providers:
        ai_config = _global_config.ai_providers["volcengine-image-qa"]
        return {
            "api_key": ai_config["api_key"],
            "base_url": ai_config["base_url"],
            "model": ai_config.get("model", "")
        }
    # 默认配置
    logging.error(f"Read Volcengine image qa API key Failed")
    return {"api_key": "", "base_url": "", "model": ""}

# 使用函数获取客户端（延迟初始化）
# 注意：这些变量在模块加载时为空，需要在 set_global_config 后重新获取
deepseek = None
volcengine_generate_image = None
volcengine_image_qa = None

def refresh_configs():
    """刷新配置，在 set_global_config 后调用"""
    global deepseek, volcengine_generate_image, volcengine_image_qa
    deepseek = get_deepseek_client()
    volcengine_generate_image = get_volcengine_generate_image_client()
    volcengine_image_qa = get_volcengine_image_qa_client()

def set_global_config(config: Config):
    """设置全局配置对象"""
    global _global_config
    _global_config = config
    # 设置配置后立即刷新
    refresh_configs()

@dataclass
class LLMResponse:
    """Response from an AI agent"""
    content: str
    reasoning_content: str
    tool_calls: Optional[List[Dict]] = None
    finish_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    json_content: Optional[str] = None


class DeepseekClient:
    """Deepseek API client"""

    def __init__(self, config=None):
        self.config = config
        self._client = None
        self._model = None

    @property
    def client(self):
        """延迟获取 OpenAI 客户端"""
        if self._client is None:
            config_dict = get_deepseek_client()
            self._client = OpenAI(
                api_key=config_dict.get("api_key", ""),
                base_url=config_dict.get("base_url", "")
            )
        return self._client

    @property
    def model(self):
        """延迟获取模型名称"""
        if self._model is None:
            config_dict = get_deepseek_client()
            self._model = config_dict.get("model", "deepseek-reasoner")
        return self._model

    def generate_response(self, messages: List[Dict], tools: List[Dict]=[], quiet: bool = False, max_tokens=15000) -> LLMResponse:
        """Generate a response by echoing the last message"""
        if not messages or not messages[0]:
            return LLMResponse(content="Hello! I'm Deepseek. How can I help you?")

        response = self.client.chat.completions.create(
            model=self.model,  # 从配置获取模型
            messages=messages,
            max_tokens=max_tokens,
            # temperature=0.7,
            tools=tools,
            tool_choice="auto",
            stream=False
        )

        # 初始化返回内容
        reasoning_content = ""
        content = ""
        tool_calls = []

        # 解析响应
        choice = response.choices[0]
        message = choice.message
        finish_reason = choice.finish_reason

        # 1. 提取普通文本内容
        if message.content:
            content = message.content
        if message.model_extra:
            if hasattr(choice.message.model_extra, 'reasoning_content'):
                reasoning_content = choice.message.model_extra.get('reasoning_content', '')
            elif hasattr(choice.message.model_extra, 'reasoning'):
                reasoning_content = choice.message.model_extra.get('reasoning', '')

        # 2. 解析工具调用（核心逻辑）
        if hasattr(message, 'tool_calls') and message.tool_calls:
            for tool_call in message.tool_calls:
                # 仅处理 function 类型的工具调用（OpenAI/DeepSeek 唯一支持的类型）
                if tool_call.type == "function":
                    func_call = tool_call.function
                    raw_args_str = func_call.arguments

                    # 清除ANSI颜色转义字符（[0m、[31m等）
                    raw_args_str = ansi_pattern.sub('', raw_args_str)

                    # 解析函数参数（JSON 字符串转字典）
                    try:
                        arguments = json.loads(raw_args_str)  # func_call.arguments
                    except json.JSONDecodeError as e:
                        arguments = {}  # 解析失败时置空
                        logging.error(f'function call parse problem: {str(e)}')

                    # 构建标准化的工具调用结构
                    tool_calls.append({
                        "id": tool_call.id,  # 工具调用 ID
                        "name": func_call.name,  # 要调用的函数名
                        "arguments": arguments  # 函数参数（字典格式）
                    })

        ################# 解决格式各个llm返回格式不统一的问题 ################33

        # 第一步：提取 ```json 代码块中的 JSON 内容
        json_block_match = json_block_pattern.search(content)
        json_content = ''
        if json_block_match:
            json_content = json_block_match.group(1).strip()
        else:
            try:
                json.loads(content.strip())
                json_content = content
            except (json.JSONDecodeError, TypeError):
                # 整体不是合法JSON，进入内容提取逻辑
                pass

        # 第二步：提取<think>与</think>之间的内容
        if reasoning_content is None or reasoning_content == '':
            think_match = think_pattern.search(content)
            if think_match:
                reasoning_content = think_match.group(1).strip()

        # 返回包含普通内容和工具调用的响应
        return LLMResponse(content=content, tool_calls=tool_calls, finish_reason=finish_reason, reasoning_content=reasoning_content, json_content=json_content)


class VolcengineGenerateImageClient:
    """Volcengine image generation client"""

    def __init__(self):
        self._client = None
        self._model = None
        self.size = "1k"
        self.response_format = "b64_json"

    @property
    def client(self):
        """延迟获取 OpenAI 客户端"""
        if self._client is None:
            config_dict = get_volcengine_generate_image_client()
            self._client = OpenAI(
                api_key=config_dict.get("api_key", ""),
                base_url=config_dict.get("base_url", "")
            )
        return self._client

    @property
    def model(self):
        """延迟获取模型名称"""
        if self._model is None:
            config_dict = get_volcengine_generate_image_client()
            self._model = config_dict.get("model", "")
        return self._model

    def generate_image(self, prompt: str, generated_img_path: str, reference_img_path: str = None):

        resp = None
        if reference_img_path is not None:
            # 使用
            image_base64 = utils.image_to_base64(reference_img_path)
            # 1. 调用接口获取 base64
            resp = self.client.images.generate(
                model=self.model,
                prompt=prompt,
                size=self.size,
                response_format=self.response_format,  # 这里必须是 base64
                extra_body={
                    "image": image_base64,
                    "watermark": False
                },
            )
        else:
            # 1. 调用接口获取 base64
            resp = self.client.images.generate(
                model=self.model,
                prompt=prompt,
                size=self.size,
                response_format=self.response_format,  # 这里必须是 base64
                extra_body={"watermark": False},
            )

        # 2. 取出 base64（根据接口返回结构取值）
        image_base64 = resp.data[0].b64_json  # 按实际返回路径改

        # 3. 保存到本地
        with open(generated_img_path, "wb") as f:
            f.write(base64.b64decode(image_base64))

        return len(resp.data)

class VolcengineImageQAClient:
    """Volcengine image QA client"""

    def __init__(self):
        self._client = None
        self._model = None

    @property
    def client(self):
        """延迟获取 OpenAI 客户端"""
        if self._client is None:
            config_dict = get_volcengine_image_qa_client()
            self._client = OpenAI(
                api_key=config_dict.get("api_key", ""),
                base_url=config_dict.get("base_url", "")
            )
        return self._client

    @property
    def model(self):
        """延迟获取模型名称"""
        if self._model is None:
            config_dict = get_volcengine_image_qa_client()
            self._model = config_dict.get("model", "")
        return self._model

    def image_qa(self, prompt: str, reference_img_path: str, file_id: str = None):
        if file_id is None:
            file_id = self.upload_image(reference_img_path)
            print(f'file id: {file_id}')

        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_image", "file_id": file_id},
                        {"type": "input_text", "text": prompt},
                    ],
                }
            ]
        )

        return response.output[1].content[0].text, file_id

    def upload_image(self, image_path: str):
        """
        上传图片 → 直接返回可用的 file.id
        支持：jpg、jpeg、png、webp、bmp
        """
        with open(image_path, "rb") as f:
            file = self.client.files.create(
                file=f,
                purpose="user_data"  # 固定这个值
            )
        return file.id


# deepseek client
deepseek_client = DeepseekClient()
volcengine_image_qa_client = VolcengineImageQAClient()
volcengine_generate_image = VolcengineGenerateImageClient()
