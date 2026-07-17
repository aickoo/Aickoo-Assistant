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


import platform
import datetime
import os
from aickoo.internal.util.utils import is_git_folder, ls_files, bool_to_yes_no
from typing import List, Dict, Any
import json
from aickoo.internal.config import Config
import click


def get_environment_info(config) -> str:
    """核心函数：获取并格式化环境信息（对应原Go函数）"""
    cwd_str = ''
    is_git_str = ''
    ls_content_str = ''

    if config.prompt_path_flag:
        # 1. 获取当前工作目录（对应config.WorkingDirectory()）
        aickoo_config = click.get_current_context().obj['config']
        cwd = aickoo_config.path_workspace  # os.getcwd()
        cwd_str = f'Working directory: {cwd}'

        # 2. 判断是否为Git仓库
        is_git = is_git_folder(cwd)
        is_git_str = f'Is directory a git repo: {bool_to_yes_no(is_git)}'

        # 5. 列出当前目录文件（对应LsTool.Run）
        ls_content = ls_files(cwd)  # ls_files(".")
        ls_content_str = f'Files and folders in the current directory: {ls_content}'

    # 3. 获取系统平台（对应runtime.GOOS）
    # platform.system()返回Windows/Linux/Darwin（macOS）等，和GOOS格式对齐
    platform_name = platform.system()

    # 4. 获取当前日期，格式为 月/日/年（对应Go的"1/2/2006"）
    # Python的strftime格式：%m=月 %d=日 %Y=年
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")

    # 6. 格式化最终返回字符串
    return f"""Here is useful information about the environment you are running in:
<env>
Platform: {platform_name}
Today's date: {current_date}
{cwd_str}
{is_git_str}
{ls_content_str}
</env>
"""


def lsp_information():
    return """# LSP Information
Tools that support it will also include useful diagnostics such as linting and typechecking.
- These diagnostics will be automatically enabled when you run the tool, and will be displayed in the output at the bottom within the <file_diagnostics></file_diagnostics> and <project_diagnostics></project_diagnostics> tags.
- Take necessary actions to fix the issues.
- You should ignore diagnostics of files that you did not change or are not related or caused by your changes unless the user explicitly asks you to fix them.
"""


# 核心改造后的代码
def count_tokens(text: str) -> int:
    """
    简易token计数（实际建议用tiktoken/anthropic的tokenizer）
    中文/英文 token 近似计算：1个中文字≈1 token，1个英文单词≈1 token
    """
    import tiktoken
    try:
        # 适配Claude/OpenAI模型的token计数
        enc = tiktoken.get_encoding("cl100k_base")  # 通用编码
        return len(enc.encode(text))
    except:
        # 降级方案
        return len(text) // 4  # 粗略估算：4个字符≈1 token


def get_message_tokens(message: Dict[str, Any]) -> int:
    """计算单条消息的token数"""
    content = message.get("content", "")
    # 工具调用额外计数
    tool_calls = message.get("tool_calls", [])
    tool_content = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else ""
    return count_tokens(content) + count_tokens(tool_content)


if __name__ == '__main__':
    print(get_environment_info())