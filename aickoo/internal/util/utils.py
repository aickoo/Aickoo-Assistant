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

import os
import subprocess
import chardet
import click
from aickoo.internal.config import Config
import base64


def ls_files(path: str = ".") -> str:
    """模拟Go中的LsTool.Run功能，列出指定路径下的文件和文件夹"""
    try:
        # 获取目录下的所有文件/文件夹名称
        entries = os.listdir(path)
        # 格式化输出，模仿ls命令的简洁样式
        return "\n".join(sorted(entries))
    except Exception as e:
        return f"Error listing directory: {str(e)}"


def bool_to_yes_no(value: bool) -> str:
    """将布尔值转换为 Yes/No 字符串（对应Go代码中的boolToYesNo）"""
    return "Yes" if value else "No"


def is_git_repo(path: str) -> bool:
    """判断指定路径是否是Git仓库"""
    try:
        # 调用git命令检查是否为git仓库，静默执行（不输出到控制台）
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=True
        )
        # 命令执行成功且输出为true表示是git仓库
        return result.stdout.strip() == "true"
    except (subprocess.CalledProcessError, FileNotFoundError):
        # 命令执行失败（非git仓库）或没装git，都返回False
        return False


def is_git_folder(dir_path: str) -> bool:
    """
    判断指定目录是否为Git仓库（复刻Go版本逻辑）

    Args:
        dir_path: 要检查的目录路径

    Returns:
        bool: 如果目录下存在.git文件夹返回True，否则返回False
    """
    # 拼接.git文件夹的完整路径（对应Go的filepath.Join）
    git_dir = os.path.join(dir_path, ".git")
    # 检查路径是否存在且是目录（对应Go的os.Stat + err == nil）
    return os.path.isdir(git_dir)


def get_current_path() -> str:
    config = get_config()
    return config.path_workspace  # os.getcwd()


def get_config() -> Config:
    return click.get_current_context().obj['config']


def get_skills_path() -> str:
    config = get_config()
    return config.path_skills  # os.getcwd()


def image_to_base64(image_path):
    ext = os.path.splitext(image_path)[-1].lower().replace(".", "")
    mime_type = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "bmp": "image/bmp",
        "gif": "image/gif"
    }.get(ext, "image/jpeg")

    with open(image_path, "rb") as f:
        base64_str = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime_type};base64,{base64_str}"

    # with open(image_path, "rb") as f:
    #     base64_str = base64.b64encode(f.read()).decode("utf-8")
    #     return f"data:image/jpeg;base64,{base64_str}"


def detect_and_convert_to_utf8(raw_data, fallback_encoding='utf-8'):
    """
    检测字符串编码并转换为UTF-8，内部处理所有异常

    Args:
        raw_data: 待检测的字符串/字节数据
        fallback_encoding: 兜底编码，默认utf-8

    Returns:
        str: 转换后的UTF-8编码字符串，转换失败则返回原数据
    """
    # 处理输入类型，确保是字节数据
    try:
        if isinstance(raw_data, str):
            # 如果已经是字符串，先尝试按utf-8编码为字节
            byte_data = raw_data.encode('utf-8')
        elif isinstance(raw_data, bytes):
            byte_data = raw_data
        else:
            # 非字符串/字节类型，转为字符串后再处理
            byte_data = str(raw_data).encode('utf-8')
    except Exception:
        # 编码失败直接使用原始数据的字符串形式
        return str(raw_data)

    # 定义常见编码优先级列表，覆盖绝大多数场景
    common_encodings = [
        'utf-8', 'gbk', 'gb2312', 'gb18030', 'big5',
        'latin-1', 'cp1252', 'ascii', 'utf-16',
        'utf-16le', 'utf-16be', 'iso-8859-1'
    ]

    detected_encoding = None

    # 第一步：使用chardet智能检测编码
    try:
        detection_result = chardet.detect(byte_data)
        if detection_result['confidence'] > 0.7:  # 置信度大于70%才使用检测结果
            detected_encoding = detection_result['encoding']
    except Exception:
        # chardet检测失败，跳过
        pass

    # 第二步：尝试解码
    decoded_str = None
    # 先尝试检测到的编码
    if detected_encoding:
        try:
            decoded_str = byte_data.decode(detected_encoding)
        except (UnicodeDecodeError, LookupError):
            # 解码失败或编码不存在，继续尝试其他编码
            pass

    # 如果检测编码失败，依次尝试常见编码
    if decoded_str is None:
        for encoding in common_encodings:
            try:
                decoded_str = byte_data.decode(encoding)
                break  # 解码成功则退出循环
            except (UnicodeDecodeError, LookupError):
                continue  # 解码失败则尝试下一个

    # 第三步：处理解码结果并转换为UTF-8
    try:
        if decoded_str is not None:
            # 解码成功，转换为UTF-8编码的字符串
            utf8_str = decoded_str.encode('utf-8').decode('utf-8')
            return utf8_str
        else:
            # 所有编码都尝试失败，返回原数据的字符串形式
            return str(raw_data)
    except Exception:
        # 任何意外异常都返回原数据
        return str(raw_data)


# ------------------------------
# 测试示例
# ------------------------------
if __name__ == "__main__":
    # 测试不同编码的字符串
    test_cases = [
        # UTF-8字符串
        "测试UTF-8编码".encode('utf-8'),
        # GBK字符串
        "测试GBK编码".encode('gbk'),
        # BIG5字符串（繁体中文）
        "測試BIG5編碼".encode('big5'),
        # Latin-1字符串
        "Test Latin-1 encoding ñ ç".encode('latin-1'),
        # 乱码/无法识别的字节
        b'\x80\x81\x82\x83',
        # 普通字符串
        "普通字符串无需转换",
        # 非字符串类型
        12345
    ]

    for i, test_data in enumerate(test_cases):
        print(f"\n测试案例 {i + 1}:")
        print(f"原始数据: {test_data}")
        result = detect_and_convert_to_utf8(test_data)
        print(f"转换结果: {result}")
        print(f"结果编码: {type(result)} (UTF-8)")