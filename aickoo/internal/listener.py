#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

事件监听器模块 - 用于监听AI处理过程中的事件并通知前端
"""

from typing import Callable, List, Optional, Any
from aickoo import logging


class ThinkingEventListener:
    """思考事件监听器"""
    
    _instance = None
    _eel_ui = None
    
    def __new__(cls):
        """单例模式，确保只有一个监听器实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化监听器"""
        if self._initialized:
            return
        self._initialized = True
        self._callbacks: List[Callable] = []
        logging.info("ThinkingEventListener initialized")
    
    def set_eel_ui(self, eel_ui) -> None:
        """设置eel_ui实例"""
        self._eel_ui = eel_ui
        logging.info("EelUI instance set for ThinkingEventListener")
    
    def register_callback(self, callback: Callable) -> None:
        """注册事件回调函数"""
        if callback not in self._callbacks:
            self._callbacks.append(callback)
            logging.info(f"Registered thinking event callback: {callback.__name__}")
    
    def unregister_callback(self, callback: Callable) -> None:
        """取消注册事件回调函数"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
            logging.info(f"Unregistered thinking event callback: {callback.__name__}")
    
    def emit_thinking(self, message: str) -> None:
        """触发思考事件
        
        Args:
            message: 思考消息内容
        """
        try:
            # 调用所有注册的回调函数
            for callback in self._callbacks:
                try:
                    callback(message)
                except Exception as e:
                    logging.error(f"Error in thinking callback {callback.__name__}: {e}")
            
            # 如果有eel_ui实例，直接发送thinking消息
            if self._eel_ui:
                self._eel_ui.send_thinking_message(message)
        except Exception as e:
            logging.error(f"Error emitting thinking event: {e}")
    
    def clear_callbacks(self) -> None:
        """清除所有注册的回调函数"""
        self._callbacks.clear()
        logging.info("Cleared all thinking event callbacks")


# 全局监听器实例
_thinking_listener = None

def get_thinking_listener() -> ThinkingEventListener:
    """获取全局思考事件监听器实例"""
    global _thinking_listener
    if _thinking_listener is None:
        _thinking_listener = ThinkingEventListener()
    return _thinking_listener


def emit_thinking_event(message: str) -> None:
    """便捷函数：触发思考事件
    
    Args:
        message: 思考消息内容
    """
    listener = get_thinking_listener()
    listener.emit_thinking(message)


def set_eel_ui_for_listener(eel_ui) -> None:
    """便捷函数：设置eel_ui实例
    
    Args:
        eel_ui: EelUI实例
    """
    listener = get_thinking_listener()
    listener.set_eel_ui(eel_ui)
