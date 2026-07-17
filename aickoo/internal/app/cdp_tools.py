#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Chrome DevTools Protocol (CDP) Client - 提供完整的 CDP 功能支持

CDP (Chrome DevTools Protocol) 是 Chrome 浏览器提供的调试协议，
允许通过 WebSocket 与浏览器进行通信，实现页面自动化、调试、性能分析等功能。

主要功能域：
- Network: 网络请求监控和拦截
- Page: 页面导航和截图
- Runtime: JavaScript 代码执行
- DOM: DOM 操作
- CSS: 样式操作
- Debugger: JavaScript 调试
- Performance: 性能分析
- Security: 安全相关
- Target: 目标页面管理
"""

import asyncio
import json
import websockets
from typing import Dict, Any, Optional, List, Callable, Awaitable
from dataclasses import dataclass, field
import base64
import time
import aiohttp
import aickoo.logging as logging


@dataclass
class CDPResponse:
    """CDP 响应对象"""
    id: int
    result: Optional[Dict] = None
    error: Optional[Dict] = None
    method: Optional[str] = None
    params: Optional[Dict] = None
    session_id: Optional[str] = None


class CDPClient:
    """Chrome DevTools Protocol 客户端"""

    def __init__(self):
        self.websocket = None
        self.url = None
        self._next_id = 1
        self._callbacks: Dict[int, asyncio.Future] = {}
        self._event_listeners: Dict[str, List[Callable]] = {}
        self._session_callbacks: Dict[str, Dict[int, asyncio.Future]] = {}
        self._connected = False

    async def connect(self, url=None) -> str:
        """
        连接到 Chrome DevTools Protocol
        
        :param url: WebSocket 连接地址，默认为本地 Chrome 调试端口
        :return: 是否连接成功
        """
        try:
            # 1. 先拿真实 WS 地址
            if url is None and self.url is None:
                async with aiohttp.ClientSession() as session:
                    async with session.get("http://localhost:9222/json/list") as resp:
                        targets = await resp.json()
                        if not targets:
                            logging.error("没有可调试页面")
                        else:
                            url = targets[0]["webSocketDebuggerUrl"]
                            logging.info(f"真实 WS 地址:{url}")

            if url is None:
                logging.error("获取调试页面失败，请确认chrome dev启动成功，程序退出")
                return None

            self.websocket = await websockets.connect(url, ping_interval=20, ping_timeout=10, max_size=None)
            self.url = url
            self._connected = True
            # 启动消息监听任务
            asyncio.create_task(self._listen())
            return self.url
        except Exception as e:
            logging.error(f"CDP 连接失败: {e}")
            return None

    async def disconnect(self):
        """断开连接"""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            self._connected = False
            self.url = None

    async def _listen(self):
        """监听 CDP 消息"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                except json.JSONDecodeError as e:
                    logging.warn(f"收到非 JSON 消息: {message[:100]}, 错误: {e}")
                    continue

                # 处理响应消息
                if 'id' in data:
                    msg_id = data['id']
                    if msg_id in self._callbacks:
                        future = self._callbacks.pop(msg_id)
                        if 'error' in data:
                            future.set_exception(Exception(data['error']['message']))
                        else:
                            future.set_result(data.get('result', {}))
                
                # 处理事件消息
                if 'method' in data:
                    method = data['method']
                    params = data.get('params', {})
                    session_id = data.get('sessionId')
                    
                    # 触发事件监听器
                    if method in self._event_listeners:
                        for callback in self._event_listeners[method]:
                            try:
                                if asyncio.iscoroutinefunction(callback):
                                    await callback(params, session_id)
                                else:
                                    callback(params, session_id)
                            except Exception as e:
                                logging.error(f"事件处理错误 {method}: {e}")
        except websockets.exceptions.ConnectionClosed as e:
            logging.info(f"WebSocket 连接关闭: {e}")
        except Exception as e:
            logging.error(f"监听循环异常: {e}", exc_info=True)
        finally:
            self._connected = False
            # 清理所有等待中的回调，避免卡住
            for future in self._callbacks.values():
                if not future.done():
                    future.set_exception(Exception("WebSocket 连接已断开"))
            self._callbacks.clear()
            logging.info("CDP 监听循环已结束")

    async def _send(self, method: str, params: Dict = None, session_id: str = None) -> Dict:
        """
        发送 CDP 请求
        
        :param method: CDP 方法名
        :param params: 方法参数
        :param session_id: 目标会话 ID
        :return: 响应结果
        """
        if not self._connected:
            raise Exception("CDP 未连接")
        
        if not self.websocket:
            raise Exception("WebSocket 未初始化")

        msg_id = self._next_id
        self._next_id += 1

        message = {
            'id': msg_id,
            'method': method,
        }
        if params:
            message['params'] = params
        if session_id:
            message['sessionId'] = session_id

        future = asyncio.get_event_loop().create_future()
        self._callbacks[msg_id] = future

        try:
            await self.websocket.send(json.dumps(message))
            # 设置 30 秒超时，防止无限等待
            return await asyncio.wait_for(future, timeout=30)
        except asyncio.TimeoutError:
            self._callbacks.pop(msg_id, None)
            raise Exception(f"CDP 请求超时: {method}")
        except Exception as e:
            self._callbacks.pop(msg_id, None)
            raise Exception(f"CDP 请求失败 {method}: {str(e)}")

    def on(self, event: str, callback: Callable):
        """
        注册事件监听器
        
        :param event: 事件名（如 Network.requestWillBeSent）
        :param callback: 回调函数，接收 (params, session_id) 参数
        """
        if event not in self._event_listeners:
            self._event_listeners[event] = []
        self._event_listeners[event].append(callback)

    def off(self, event: str, callback: Callable):
        """
        移除事件监听器
        
        :param event: 事件名
        :param callback: 要移除的回调函数
        """
        if event in self._event_listeners:
            self._event_listeners[event].remove(callback)

    # ==================== Target 域 ====================

    async def target_get_targets(self) -> List[Dict]:
        """获取所有可用目标"""
        result = await self._send("Target.getTargets")
        return result.get('targetInfos', [])

    async def target_create_target(self, url: str, width: int = None, height: int = None) -> str:
        """
        创建新目标页面
        
        :param url: 页面 URL
        :param width: 视口宽度（可选）
        :param height: 视口高度（可选）
        :return: 目标 ID
        """
        params = {'url': url}
        if width is not None and height is not None:
            params.update({
                'width': width,
                'height': height,
                'newWindow': True  # 设置为新窗口时才能指定位置
            })
        
        result = await self._send("Target.createTarget", params)
        return result.get('targetId')

    async def target_attach_to_target(self, target_id: str, flatten: bool = True) -> str:
        """
        附加到目标
        
        :param target_id: 目标 ID
        :param flatten: 是否扁平化事件（直接发送到主连接）
        :return: 会话 ID
        """
        result = await self._send("Target.attachToTarget", {
            'targetId': target_id,
            'flatten': flatten
        })
        return result.get('sessionId')

    async def target_close_target(self, target_id: str) -> bool:
        """
        关闭目标
        
        :param target_id: 目标 ID
        :return: 是否成功
        """
        result = await self._send("Target.closeTarget", {'targetId': target_id})
        return result.get('success', False)

    # ==================== Page 域 ====================

    async def page_navigate(self, url: str, session_id: str = None) -> str:
        """
        导航到指定 URL
        
        :param url: 目标 URL
        :param session_id: 会话 ID（可选）
        :return: 导航 ID
        """
        result = await self._send("Page.navigate", {'url': url}, session_id)
        return result.get('frameId')

    async def page_reload(self, session_id: str = None):
        """
        重新加载页面
        
        :param session_id: 会话 ID（可选）
        """
        await self._send("Page.reload", {}, session_id)
    
    async def page_navigate_back(self, session_id: str = None):
        """
        返回上一页
        
        :param session_id: 会话 ID（可选）
        """
        await self._send("Page.navigateBack", {}, session_id)
    
    async def page_get_appmanifest(self, session_id: str = None) -> Dict:
        """
        获取应用清单
        
        :param session_id: 会话 ID（可选）
        :return: 清单数据
        """
        return await self._send("Page.getAppManifest", {}, session_id)

    async def page_capture_screenshot(self, format: str = "png", quality: int = 100, 
                                     session_id: str = None) -> bytes:
        """
        捕获页面截图
        
        :param format: 图片格式 (png, jpeg, webp)
        :param quality: 图片质量 (0-100)
        :param session_id: 会话 ID（可选）
        :return: 截图二进制数据
        """
        result = await self._send("Page.captureScreenshot", {
            'format': format,
            'quality': quality
        }, session_id)
        return base64.b64decode(result.get('data', ''))

    async def page_set_viewport(self, width: int, height: int, device_scale_factor: float = 1.0,
                               session_id: str = None):
        """
        设置视口大小
        
        :param width: 宽度
        :param height: 高度
        :param device_scale_factor: 设备缩放因子
        :param session_id: 会话 ID（可选）
        """
        await self._send("Page.setViewport", {
            'width': width,
            'height': height,
            'deviceScaleFactor': device_scale_factor
        }, session_id)

    async def page_enable(self, session_id: str = None):
        """启用 Page 域"""
        await self._send("Page.enable", {}, session_id)

    async def page_disable(self, session_id: str = None):
        """禁用 Page 域"""
        await self._send("Page.disable", {}, session_id)

    # ==================== Runtime 域 ====================

    async def runtime_evaluate(self, expression: str, context_id: int = None, 
                              return_by_value: bool = False, session_id: str = None) -> Dict:
        """
        执行 JavaScript 表达式
        
        :param expression: JS 表达式
        :param context_id: 执行上下文 ID（可选）
        :param return_by_value: 是否返回值而非引用（Chrome 149 推荐使用 serializeOptions）
        :param session_id: 会话 ID（可选）
        :return: 执行结果
        """
        params = {'expression': expression}
        if return_by_value:
            params['serializeOptions'] = {'maxDepth': 100}
        if context_id:
            params['contextId'] = context_id
        
        return await self._send("Runtime.evaluate", params, session_id)

    async def runtime_call_function_on(self, object_id: str, function_declaration: str,
                                       args: List = None, session_id: str = None) -> Dict:
        """
        调用对象上的函数
        
        :param object_id: 对象 ID
        :param function_declaration: 函数声明
        :param args: 函数参数
        :param session_id: 会话 ID（可选）
        :return: 调用结果
        """
        params = {
            'objectId': object_id,
            'functionDeclaration': function_declaration
        }
        if args:
            params['arguments'] = args
        
        return await self._send("Runtime.callFunctionOn", params, session_id)

    async def runtime_get_properties(self, object_id: str, session_id: str = None) -> List[Dict]:
        """
        获取对象属性
        
        :param object_id: 对象 ID
        :param session_id: 会话 ID（可选）
        :return: 属性列表
        """
        result = await self._send("Runtime.getProperties", {'objectId': object_id}, session_id)
        return result.get('result', [])

    async def runtime_enable(self, session_id: str = None):
        """启用 Runtime 域"""
        await self._send("Runtime.enable", {}, session_id)

    async def runtime_disable(self, session_id: str = None):
        """禁用 Runtime 域"""
        await self._send("Runtime.disable", {}, session_id)

    # ==================== Network 域 ====================

    async def network_enable(self, session_id: str = None):
        """
        启用网络监控
        
        :param session_id: 会话 ID（可选）
        """
        await self._send("Network.enable", {}, session_id)

    async def network_disable(self, session_id: str = None):
        """禁用网络监控"""
        await self._send("Network.disable", {}, session_id)

    async def network_get_request_post_data(self, request_id: str, session_id: str = None) -> str:
        """
        获取请求的 POST 数据
        
        :param request_id: 请求 ID
        :param session_id: 会话 ID（可选）
        :return: POST 数据
        """
        result = await self._send("Network.getRequestPostData", {'requestId': request_id}, session_id)
        return result.get('postData', '')

    async def network_get_response_body(self, request_id: str, session_id: str = None) -> str:
        """
        获取响应体
        
        :param request_id: 请求 ID
        :param session_id: 会话 ID（可选）
        :return: 响应体内容
        """
        result = await self._send("Network.getResponseBody", {'requestId': request_id}, session_id)
        body = result.get('body', '')
        if result.get('base64Encoded', False):
            body = base64.b64decode(body).decode('utf-8')
        return body

    async def network_set_credentials(self, origin: str, username: str, password: str,
                                     session_id: str = None):
        """
        设置认证凭据（Chrome 149 中已废弃，建议使用 Network.setExtraHTTPHeaders）
        
        :param origin: 目标源
        :param username: 用户名
        :param password: 密码
        :param session_id: 会话 ID（可选）
        """
        # 在新版本 CDP 中，setCredentials 已废弃
        # 使用 setExtraHTTPHeaders 设置 Authorization header
        import base64
        auth = base64.b64encode(f"{username}:{password}".encode()).decode()
        await self._send("Network.setExtraHTTPHeaders", {
            'headers': {
                'Authorization': f'Basic {auth}'
            }
        }, session_id)

    async def network_set_blocked_urls(self, urls: List[str], session_id: str = None):
        """
        设置拦截 URL 列表
        
        :param urls: URL 模式列表
        :param session_id: 会话 ID（可选）
        """
        await self._send("Network.setBlockedURLs", {'urls': urls}, session_id)

    async def network_clear_browser_cache(self, session_id: str = None):
        """清除浏览器缓存"""
        await self._send("Network.clearBrowserCache", {}, session_id)

    async def network_clear_browser_cookies(self, session_id: str = None):
        """清除浏览器 Cookie"""
        await self._send("Network.clearBrowserCookies", {}, session_id)

    # ==================== Input 域 ====================

    async def input_dispatch_key_event(self, type: str, text: str = "",
                                      key: str = "", session_id: str = None):
        """
        分发键盘事件

        :param type: 事件类型 (keyDown, keyUp, char)
        :param text: 输入的文本内容
        :param key: 键名
        :param session_id: 会话 ID（可选）
        """
        params = {'type': type}
        if text:
            params['text'] = text
        if key:
            params['key'] = key
        await self._send("Input.dispatchKeyEvent", params, session_id)

    async def input_dispatch_mouse_event(self, type: str, x: int, y: int,
                                         session_id: str = None,
                                         button: str = 'left', click_count: int = 1):
        """
        分发鼠标事件

        :param type: 事件类型 (mouseDown, mouseUp, mouseMove)
        :param x: 鼠标 X 坐标
        :param y: 鼠标 Y 坐标
        :param session_id: 会话 ID（可选）
        :param button:
        :param click_count:
        """
        button_map = {'left': 0, 'right': 2, 'middle': 1}
        is_pressed = type in('mousePressed', 'mouseDown')
        await self._send("Input.dispatchMouseEvent", {
            'type': type,
            'x': x,
            'y': y,
            'button': button_map.get(button, 0),
            'buttons': 1 if is_pressed else 0,
            'clickCount': click_count
        }, session_id)

    # ==================== DOM 域 ====================

    async def dom_get_document(self, depth: int = -1, pierce: bool = False,
                              session_id: str = None) -> Dict:
        """
        获取文档根节点

        :param depth: 返回深度，-1 表示完整树
        :param pierce: 是否穿透 shadow DOM
        :param session_id: 会话 ID（可选）
        :return: 文档节点
        """
        return await self._send("DOM.getDocument", {
            'depth': depth,
            'pierce': pierce
        }, session_id)

    async def dom_get_element_by_id(self, element_id: str, session_id: str = None) -> Dict:
        """
        通过 ID 获取元素

        :param element_id: 元素 ID
        :param session_id: 会话 ID（可选）
        :return: 元素信息
        """
        return await self._send("DOM.getElementById", {'id': element_id}, session_id)

    async def dom_query_selector(self, node_id: int, selector: str, session_id: str = None) -> int:
        """
        查询选择器匹配的第一个元素

        :param node_id: 起始节点 ID
        :param selector: CSS 选择器
        :param session_id: 会话 ID（可选）
        :return: 元素节点 ID
        """
        result = await self._send("DOM.querySelector", {
            'nodeId': node_id,
            'selector': selector
        }, session_id)
        return result.get('nodeId')

    async def dom_query_selector_all(self, node_id: int, selector: str,
                                    session_id: str = None) -> List[int]:
        """
        查询选择器匹配的所有元素

        :param node_id: 起始节点 ID
        :param selector: CSS 选择器
        :param session_id: 会话 ID（可选）
        :return: 元素节点 ID 列表
        """
        result = await self._send("DOM.querySelectorAll", {
            'nodeId': node_id,
            'selector': selector
        }, session_id)
        return result.get('nodeIds', [])

    async def dom_get_attributes(self, node_id: int, session_id: str = None) -> List[str]:
        """
        获取元素属性

        :param node_id: 节点 ID
        :param session_id: 会话 ID（可选）
        :return: 属性列表（键值对交替）
        """
        result = await self._send("DOM.getAttributes", {'nodeId': node_id}, session_id)
        return result.get('attributes', [])

    async def dom_get_box_model(self, node_id: int, session_id: str = None) -> Dict:
        """
        获取元素的盒子模型信息

        :param node_id: 节点 ID
        :param session_id: 会话 ID（可选）
        :return: 盒子模型信息，包含 content/padding/border/margin 边界
        """
        result = await self._send("DOM.getBoxModel", {'nodeId': node_id}, session_id)
        return result

    async def dom_set_attribute_value(self, node_id: int, name: str, value: str,
                                      session_id: str = None):
        """
        设置元素属性值
        
        :param node_id: 节点 ID
        :param name: 属性名
        :param value: 属性值
        :param session_id: 会话 ID（可选）
        """
        await self._send("DOM.setAttributeValue", {
            'nodeId': node_id,
            'name': name,
            'value': value
        }, session_id)

    async def dom_remove_attribute(self, node_id: int, name: str, session_id: str = None):
        """
        移除元素属性
        
        :param node_id: 节点 ID
        :param name: 属性名
        :param session_id: 会话 ID（可选）
        """
        await self._send("DOM.removeAttribute", {
            'nodeId': node_id,
            'name': name
        }, session_id)

    async def dom_set_node_value(self, node_id: int, value: str, session_id: str = None):
        """
        设置节点文本值
        
        :param node_id: 节点 ID
        :param value: 文本值
        :param session_id: 会话 ID（可选）
        """
        await self._send("DOM.setNodeValue", {
            'nodeId': node_id,
            'value': value
        }, session_id)

    async def dom_click(self, node_id: int, session_id: str = None):
        """
        点击元素
        
        :param node_id: 节点 ID
        :param session_id: 会话 ID（可选）
        """
        await self._send("DOM.click", {'nodeId': node_id}, session_id)

    async def dom_focus(self, node_id: int, session_id: str = None):
        """
        聚焦指定元素

        :param node_id: 节点 ID
        :param session_id: 会话 ID（可选）
        """
        await self._send("DOM.focus", {'nodeId': node_id}, session_id)

    async def dom_enable(self, session_id: str = None):
        """启用 DOM 域"""
        await self._send("DOM.enable", {}, session_id)

    async def dom_disable(self, session_id: str = None):
        """禁用 DOM 域"""
        await self._send("DOM.disable", {}, session_id)

    # ==================== CSS 域 ====================

    async def css_enable(self, session_id: str = None):
        """启用 CSS 域"""
        await self._send("CSS.enable", {}, session_id)

    async def css_disable(self, session_id: str = None):
        """禁用 CSS 域"""
        await self._send("CSS.disable", {}, session_id)

    async def css_get_computed_style_for_node(self, node_id: int, session_id: str = None) -> List[Dict]:
        """
        获取节点的计算样式
        
        :param node_id: 节点 ID
        :param session_id: 会话 ID（可选）
        :return: 样式属性列表
        """
        result = await self._send("CSS.getComputedStyleForNode", {'nodeId': node_id}, session_id)
        return result.get('computedStyle', [])

    async def css_get_inline_style_for_node(self, node_id: int, session_id: str = None) -> Dict:
        """
        获取节点的内联样式
        
        :param node_id: 节点 ID
        :param session_id: 会话 ID（可选）
        :return: 内联样式
        """
        return await self._send("CSS.getInlineStyleForNode", {'nodeId': node_id}, session_id)

    async def css_set_style_text(self, style_id: str, text: str, session_id: str = None):
        """
        设置样式文本
        
        :param style_id: 样式 ID
        :param text: 样式文本
        :param session_id: 会话 ID（可选）
        """
        await self._send("CSS.setStyleText", {
            'styleId': style_id,
            'text': text
        }, session_id)

    async def css_add_rule(self, style_sheet_id: str, rule_text: str, 
                          origin: str = "author", session_id: str = None) -> Dict:
        """
        添加 CSS 规则
        
        :param style_sheet_id: 样式表 ID
        :param rule_text: 规则文本
        :param origin: 规则来源 (author/user/user-agent)
        :param session_id: 会话 ID（可选）
        :return: 新规则信息
        """
        return await self._send("CSS.addRule", {
            'styleSheetId': style_sheet_id,
            'ruleText': rule_text,
            'origin': origin
        }, session_id)

    # ==================== Debugger 域 ====================

    async def debugger_enable(self, session_id: str = None):
        """启用调试器"""
        await self._send("Debugger.enable", {}, session_id)

    async def debugger_disable(self, session_id: str = None):
        """禁用调试器"""
        await self._send("Debugger.disable", {}, session_id)

    async def debugger_set_breakpoint(self, script_id: str, line_number: int, 
                                      column_number: int = 0, condition: str = None,
                                      session_id: str = None) -> str:
        """
        设置断点
        
        :param script_id: 脚本 ID
        :param line_number: 行号
        :param column_number: 列号
        :param condition: 断点条件
        :param session_id: 会话 ID（可选）
        :return: 断点 ID
        """
        params = {
            'location': {
                'scriptId': script_id,
                'lineNumber': line_number,
                'columnNumber': column_number
            }
        }
        if condition:
            params['condition'] = condition
        
        result = await self._send("Debugger.setBreakpoint", params, session_id)
        return result.get('breakpointId')

    async def debugger_remove_breakpoint(self, breakpoint_id: str, session_id: str = None):
        """
        移除断点
        
        :param breakpoint_id: 断点 ID
        :param session_id: 会话 ID（可选）
        """
        await self._send("Debugger.removeBreakpoint", {'breakpointId': breakpoint_id}, session_id)

    async def debugger_pause(self, session_id: str = None):
        """暂停执行"""
        await self._send("Debugger.pause", {}, session_id)

    async def debugger_resume(self, session_id: str = None):
        """恢复执行"""
        await self._send("Debugger.resume", {}, session_id)

    async def debugger_step_over(self, session_id: str = None):
        """单步执行（跳过函数调用）"""
        await self._send("Debugger.stepOver", {}, session_id)

    async def debugger_step_into(self, session_id: str = None):
        """单步执行（进入函数调用）"""
        await self._send("Debugger.stepInto", {}, session_id)

    async def debugger_step_out(self, session_id: str = None):
        """跳出当前函数"""
        await self._send("Debugger.stepOut", {}, session_id)

    # ==================== Performance 域 ====================

    async def performance_enable(self, session_id: str = None):
        """启用性能监控"""
        await self._send("Performance.enable", {}, session_id)

    async def performance_disable(self, session_id: str = None):
        """禁用性能监控"""
        await self._send("Performance.disable", {}, session_id)

    async def performance_get_metrics(self, session_id: str = None) -> List[Dict]:
        """
        获取性能指标
        
        :param session_id: 会话 ID（可选）
        :return: 指标列表
        """
        result = await self._send("Performance.getMetrics", {}, session_id)
        return result.get('metrics', [])

    async def performance_start_tracing(self, buffer_size: int = None, 
                                       categories: str = None, session_id: str = None):
        """
        开始性能追踪（Chrome 149 使用 Tracing.start 替代 Performance.startTracing）
        
        :param buffer_size: 缓冲区大小
        :param categories: 追踪类别（逗号分隔）
        :param session_id: 会话 ID（可选）
        """
        # Chrome 149 中 Performance.startTracing 已废弃，使用 Tracing.start
        params = {
            'categories': categories or '',
            'bufferUsageReportingInterval': 1000
        }
        if buffer_size:
            params['bufferSize'] = buffer_size
        
        await self._send("Tracing.start", params, session_id)

    async def performance_stop_tracing(self, session_id: str = None) -> bytes:
        """
        停止性能追踪并获取追踪数据（Chrome 149 使用 Tracing.end 替代 Performance.stopTracing）
        
        :param session_id: 会话 ID（可选）
        :return: 追踪数据（JSON 格式）
        """
        # 使用事件监听获取追踪数据
        tracing_data = []
        
        def on_data(params, sid):
            if 'data' in params:
                tracing_data.append(params['data'])
        
        self.on("Tracing.dataCollected", on_data)
        
        try:
            await self._send("Tracing.end", {}, session_id)
            # 等待追踪数据收集完成
            await asyncio.sleep(1)
        finally:
            self.off("Tracing.dataCollected", on_data)
        
        if tracing_data:
            return base64.b64decode(''.join(tracing_data))
        return b''

    # ==================== Security 域 ====================

    async def security_enable(self, session_id: str = None):
        """启用安全监控"""
        await self._send("Security.enable", {}, session_id)

    async def security_disable(self, session_id: str = None):
        """禁用安全监控"""
        await self._send("Security.disable", {}, session_id)

    async def security_get_security_state(self, session_id: str = None) -> Dict:
        """
        获取安全状态
        
        :param session_id: 会话 ID（可选）
        :return: 安全状态信息
        """
        return await self._send("Security.getSecurityState", {}, session_id)

    async def security_set_ignore_certificate_errors(self, ignore: bool, session_id: str = None):
        """
        设置是否忽略证书错误（Chrome 149 参数格式变更）
        
        :param ignore: 是否忽略
        :param session_id: 会话 ID（可选）
        """
        # Chrome 149 中参数格式变更，使用列表形式
        await self._send("Security.setIgnoreCertificateErrors", {
            'ignoreCertificateErrors': ignore
        }, session_id)

    # ==================== 便捷方法 ====================

    async def wait_for_navigation(self, session_id: str = None, timeout: int = 30):
        """
        等待页面导航完成
        
        :param session_id: 会话 ID（可选）
        :param timeout: 超时时间（秒）
        """
        event = asyncio.Event()
        
        def on_navigated(params, sid):
            if session_id is None or sid == session_id:
                event.set()
        
        self.on("Page.frameNavigated", on_navigated)
        
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        finally:
            self.off("Page.frameNavigated", on_navigated)

    async def wait_for_load(self, session_id: str = None, timeout: int = 30):
        """
        等待页面加载完成
        
        :param session_id: 会话 ID（可选）
        :param timeout: 超时时间（秒）
        """
        event = asyncio.Event()
        
        def on_load(params, sid):
            if session_id is None or sid == session_id:
                event.set()
        
        self.on("Page.loadEventFired", on_load)
        
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        finally:
            self.off("Page.loadEventFired", on_load)

    async def execute_script(self, script: str, session_id: str = None) -> Any:
        """
        便捷方法：执行 JavaScript 脚本
        
        :param script: JS 脚本
        :param session_id: 会话 ID（可选）
        :return: 执行结果
        """
        result = await self.runtime_evaluate(script, return_by_value=True, session_id=session_id)
        if 'result' in result and 'value' in result['result']:
            return result['result']['value']
        return result


# 同步包装器（便于在同步代码中使用）

class CDPClientSync:
    """CDP 同步客户端包装器"""
    
    def __init__(self):
        self._client = CDPClient()
        self._loop = None
    
    def connect(self, url: str = None) -> bool:
        """连接到 CDP"""
        self._loop = asyncio.new_event_loop()
        return self._loop.run_until_complete(self._client.connect(url))
    
    def disconnect(self):
        """断开连接"""
        if self._loop:
            self._loop.run_until_complete(self._client.disconnect())
            self._loop.close()
    
    def __getattr__(self, name):
        """代理所有方法到异步客户端并同步执行"""
        method = getattr(self._client, name)
        if asyncio.iscoroutinefunction(method):
            def wrapper(*args, **kwargs):
                return self._loop.run_until_complete(method(*args, **kwargs))
            return wrapper
        return method


# 示例使用
if __name__ == "__main__":
    import asyncio
    
    async def main():
        # 创建客户端

        # ws_url = None
        #
        # # 1. 先拿真实 WS 地址
        # async with aiohttp.ClientSession() as session:
        #     async with session.get("http://localhost:9222/json/list") as resp:
        #         targets = await resp.json()
        #         if not targets:
        #             print("没有可调试页面")
        #             return
        #         ws_url = targets[0]["webSocketDebuggerUrl"]
        #         print("真实 WS 地址:", ws_url)
        #
        # if ws_url is None:
        #     print("获取调试页面失败，请确认chrome dev启动成功，程序退出")
        #     return
        
        client = CDPClient()
        
        # 连接到 Chrome
        # if not await client.connect("ws://localhost:9222/devtools/browser"): # 96版本以后就不用了，改成动态的
        if not await client.connect():
            print("无法连接到 Chrome，请确保 Chrome 已启动并开启远程调试")
            return
        
        try:
            # 获取所有目标
            targets = await client.target_get_targets()
            print(f"发现 {len(targets)} 个目标")
            
            # 如果没有打开的页面，创建一个新页面（不传递尺寸参数以避免位置设置错误）
            if not targets:
                target_id = await client.target_create_target("https://www.bing.com")
                print(f"创建新目标: {target_id}")
                # 等待目标创建完成
                await asyncio.sleep(1)
                # 重新获取目标列表
                targets = await client.target_get_targets()
                if targets:
                    target_id = targets[0]['targetId']
            else:
                target_id = targets[0]['targetId']
            
            # 附加到目标
            session_id = await client.target_attach_to_target(target_id)
            print(f"会话 ID: {session_id}")
            
            # 启用必要的域
            await client.page_enable(session_id)
            await client.network_enable(session_id)
            
            # 导航到页面
            await client.page_navigate("https://www.bing.com", session_id)
            await client.wait_for_load(session_id)
            
            # 执行 JavaScript
            title = await client.execute_script("document.title", session_id)
            print(f"页面标题: {title}")
            
            # 捕获截图
            screenshot = await client.page_capture_screenshot(session_id=session_id)
            with open("screenshot.png", "wb") as f:
                f.write(screenshot)
            print("截图已保存")
            
        finally:
            # 断开连接
            await client.disconnect()
    
    asyncio.run(main())
