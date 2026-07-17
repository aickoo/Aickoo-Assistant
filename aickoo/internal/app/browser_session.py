#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

BrowserSession - CDP 高级封装层
提供对 Chrome DevTools Protocol 的高级封装，包含：
- CDP 连接管理
- 多 Session 管理
- 浏览器状态管理
- 高层 API 封装
"""

import asyncio
import json
import time
import aiohttp
from typing import Dict, Any, Optional, List, Set, Callable
from dataclasses import dataclass, field
import base64
import aickoo.logging as logging

from .cdp_tools import CDPClient


@dataclass
class BrowserState:
    """浏览器状态摘要"""
    current_url: str = ""
    current_title: str = ""
    current_target_id: str = ""
    current_session_id: str = ""
    page_loaded: bool = False
    cookies_count: int = 0
    network_requests_count: int = 0
    open_tabs: int = 0


@dataclass
class SelectorInfo:
    """选择器信息"""
    selector: str
    node_id: int
    tag_name: str
    attributes: Dict[str, str] = field(default_factory=dict)
    text_content: str = ""


class BrowserSession:
    """
    浏览器会话管理器 - CDP 高级封装层
    
    核心功能：
    1. CDP 连接管理（root 连接和多个 session）
    2. 浏览器状态维护
    3. 高层 API 封装
    """
    
    def __init__(self, browser_ws_url: str = None):
        """
        初始化浏览器会话
        
        :param browser_ws_url: Chrome DevTools WebSocket 地址
        """
        self._browser_ws_url = browser_ws_url
        self._cdp_client_root: Optional[CDPClient] = None
        self._sessions: Dict[str, CDPClient] = {}  # session_id -> CDPClient
        self._target_session_map: Dict[str, str] = {}  # target_id -> session_id
        
        # 状态管理
        self._current_target_id: str = ""
        self._current_session_id: str = ""
        self._current_url: str = ""
        self._page_loaded_event = asyncio.Event()
        self._network_requests: Set[str] = set()
        
        # 事件监听器
        self._event_handlers: Dict[str, List[Callable]] = {}
        
    # ==================== 连接管理 ====================
    
    async def connect(self) -> bool:
        """
        建立 CDP 连接
        
        :return: 是否连接成功
        """
        self._cdp_client_root = CDPClient()
        browser_ws_url = await self._cdp_client_root.connect(self._browser_ws_url)
        
        if browser_ws_url:
            self._browser_ws_url = browser_ws_url
            # 注册事件监听
            await self._register_root_events()
            logging.info(f"BrowserSession 已连接到 {self._browser_ws_url}")
            return True
        
        return False
    
    async def disconnect(self):
        """断开所有连接"""
        # 关闭 root 连接
        if self._cdp_client_root:
            await self._cdp_client_root.disconnect()
        
        self._sessions.clear()
        self._target_session_map.clear()
        logging.info("BrowserSession 已断开连接")
    
    async def reconnect(self) -> bool:
        """重新连接"""
        await self.disconnect()
        return await self.connect()
    
    async def _register_root_events(self):
        """注册 root 级别的事件监听"""
        if not self._cdp_client_root:
            return
        
        # 监听目标创建
        self._cdp_client_root.on("Target.targetCreated", self._on_target_created)
        # 监听目标销毁
        self._cdp_client_root.on("Target.targetDestroyed", self._on_target_destroyed)
        # 监听目标信息变化
        self._cdp_client_root.on("Target.targetInfoChanged", self._on_target_info_changed)
    
    def _on_target_created(self, params: Dict, session_id: str):
        """处理目标创建事件"""
        target_info = params.get("targetInfo", {})
        target_id = target_info.get("targetId")
        if target_id:
            logging.info(f"目标创建: {target_id} - {target_info.get('url', '')}")

    def _on_target_destroyed(self, params: Dict, session_id: str):
        target_id = params.get("targetId")
        if target_id:
            session_id = self._target_session_map.pop(target_id, None)
            if session_id and session_id in self._sessions:
                # ❌ 错误：不应该断开共享的 root client
                # asyncio.create_task(self._sessions[session_id].disconnect())
                # ✅ 正确：只清理映射
                del self._sessions[session_id]
            logging.info(f"目标销毁: {target_id}")
    
    def _on_target_info_changed(self, params: Dict, session_id: str):
        """处理目标信息变化事件"""
        target_info = params.get("targetInfo", {})
        target_id = target_info.get("targetId")
        if target_id and target_id == self._current_target_id:
            self._current_url = target_info.get("url", "")
    
    # ==================== Session 管理 ====================

    async def get_or_create_cdp_session(self, target_id: str = None) -> str:
        if not target_id:
            target_id = await self._get_or_create_default_target()

        # 已有会话直接返回 session_id
        if target_id in self._target_session_map:
            return self._target_session_map[target_id]

        if not self._cdp_client_root:
            raise Exception("CDP root 连接未建立")

        # 通过 root client 附加到目标，获得 session_id
        session_id = await self._cdp_client_root.target_attach_to_target(target_id)

        # 存储映射：target_id -> session_id
        self._target_session_map[target_id] = session_id
        self._current_target_id = target_id
        self._current_session_id = session_id

        # session_id -> CDTClient
        self._sessions[session_id] = self._cdp_client_root

        # 注意：不需要 self._sessions 字典！所有命令都通过 root client + session_id 发送
        # 但为了兼容现有代码（如 navigate_to 检查 session_id in self._sessions），
        # 你可以仍然存入一个占位符，或者修改所有检查逻辑。
        # 最简单的兼容方式：self._sessions[session_id] = None 或存一个空对象，
        # 然后修改所有方法改为直接使用 root client。

        # 启用必要的域（通过 root client + session_id）
        root = self._cdp_client_root
        await root.page_enable(session_id)
        await root.network_enable(session_id)
        await root.runtime_enable(session_id)
        await root.dom_enable(session_id)

        # 注册页面加载完成事件监听器
        root.on("Page.loadEventFired", self._on_page_load)
        root.on("Network.requestWillBeSent", self._on_network_request)
        root.on("Network.responseReceived", self._on_network_response)

        logging.info(f"创建 Session: {session_id} 用于目标: {target_id}")
        return session_id
    
    async def _get_or_create_default_target(self) -> str:
        """获取或创建默认目标"""
        if not self._cdp_client_root:
            raise Exception("CDP root 连接未建立")
        
        targets = await self._cdp_client_root.target_get_targets()
        
        # 优先使用已存在的页面目标
        for target in targets:
            if target.get("type") == "page" and target.get("url") != "about:blank":
                return target["targetId"]
        
        # 创建新目标
        return await self._cdp_client_root.target_create_target("about:blank")
    
    # ==================== 目标管理（对外 API）====================
    
    async def list_targets(self) -> List[Dict]:
        """
        列出所有可用目标
        
        :return: 目标列表，每个目标包含 target_id, type, url, title
        """
        if not self._cdp_client_root:
            raise Exception("CDP root 连接未建立")
        
        targets = await self._cdp_client_root.target_get_targets()
        result = []
        
        for target in targets:
            result.append({
                "target_id": target.get("targetId"),
                "type": target.get("type"),
                "url": target.get("url", ""),
                "title": target.get("title", ""),
                "attached": target.get("attached", False),
                "is_current": target.get("targetId") == self._current_target_id
            })
        
        return result
    
    async def get_or_create_session_by_target(self, target_id: str = None) -> str:
        """
        基于 target_id 获取或创建 session
        
        :param target_id: 目标 ID，为空则使用当前活动目标
        :return: Session ID
        """
        if not target_id:
            target_id = self._current_target_id
            if not target_id:
                target_id = await self._get_or_create_default_target()
        
        return await self.get_or_create_cdp_session(target_id)
    
    async def switch_to_target(self, target_id: str) -> str:
        """
        切换到指定目标
        
        :param target_id: 目标 ID
        :return: Session ID
        """
        if not self._cdp_client_root:
            raise Exception("CDP root 连接未建立")
        
        # 获取或创建 session
        session_id = await self.get_or_create_cdp_session(target_id)
        
        # 更新当前状态
        self._current_target_id = target_id
        self._current_session_id = session_id
        
        logging.info(f"已切换到目标: {target_id}")
        return session_id
    
    def get_current_target_id(self) -> str:
        """
        获取当前活动目标 ID
        
        :return: 当前 target_id
        """
        return self._current_target_id
    
    def get_target_id_by_session(self, session_id: str) -> Optional[str]:
        """
        通过 session_id 获取对应的 target_id
        
        :param session_id: Session ID
        :return: Target ID
        """
        for target_id, sid in self._target_session_map.items():
            if sid == session_id:
                return target_id
        return None
    
    async def create_new_tab(self, url: str = "about:blank") -> str:
        """
        创建新标签页
        
        :param url: 初始 URL
        :return: 新目标的 target_id
        """
        if not self._cdp_client_root:
            raise Exception("CDP root 连接未建立")
        
        target_id = await self._cdp_client_root.target_create_target(url)
        logging.info(f"创建新标签页: {target_id}")
        
        # 自动切换到新标签页
        await self.switch_to_target(target_id)
        
        return target_id
    
    async def close_target(self, target_id: str):
        """
        关闭指定目标（标签页）
        
        :param target_id: 目标 ID
        """
        if not self._cdp_client_root:
            raise Exception("CDP root 连接未建立")
        
        # 先关闭 session
        await self.close_session(target_id=target_id)
        
        # 调用 CDP 关闭目标
        await self._cdp_client_root.target_close_target(target_id)
        
        logging.info(f"已关闭目标: {target_id}")
    
    async def close_session(self, session_id: str = None, target_id: str = None):
        """
        关闭指定 Session
        
        :param session_id: Session ID
        :param target_id: 目标 ID（优先级高于 session_id）
        
        注意：不会断开共享的 _cdp_client_root，只清理内部映射
        """
        # 通过 target_id 查找 session_id
        if target_id:
            session_id = self._target_session_map.get(target_id)
        
        if not session_id:
            logging.warn(f"Session 未找到: session_id={session_id}, target_id={target_id}")
            return
        
        # 清理映射（不断开 root client）
        for tid, sid in list(self._target_session_map.items()):
            if sid == session_id:
                del self._target_session_map[tid]
                break
        
        # 从 sessions 中移除
        if session_id in self._sessions:
            # 注意：这里不应该 disconnect，因为可能还有其他 session 使用 root client
            # self._sessions[session_id] 是同一个 root client
            del self._sessions[session_id]
        
        # 如果关闭的是当前 session，更新当前状态
        if session_id == self._current_session_id:
            self._current_session_id = ""
            self._current_target_id = ""
        
        logging.info(f"Session 已关闭: {session_id}")
    
    def _on_page_load(self, params: Dict, session_id: str):
        """页面加载完成事件"""
        self._page_loaded_event.set()
        logging.info(f"页面加载完成: {session_id}")
    
    def _on_network_request(self, params: Dict, session_id: str):
        """网络请求发送事件"""
        request_id = params.get("request", {}).get("requestId")
        if request_id:
            self._network_requests.add(request_id)
    
    def _on_network_response(self, params: Dict, session_id: str):
        """网络响应接收事件"""
        request_id = params.get("requestId")
        if request_id in self._network_requests:
            self._network_requests.remove(request_id)
    
    # ==================== 状态管理 ====================
    
    async def get_browser_state_summary(self) -> BrowserState:
        """
        获取浏览器状态摘要
        
        :return: BrowserState 对象
        """
        state = BrowserState()
        
        if self._cdp_client_root:
            # 获取目标列表
            targets = await self._cdp_client_root.target_get_targets()
            state.open_tabs = len([t for t in targets if t.get("type") == "page"])
        
        if self._current_session_id and self._current_session_id in self._sessions:
            client = self._sessions[self._current_session_id]
            
            # 获取当前页面标题
            title = await client.execute_script("document.title", self._current_session_id)
            state.current_title = title or ""
            
            # 获取当前 URL
            url = await client.execute_script("window.location.href", self._current_session_id)
            state.current_url = url or ""
            
            # 获取 cookies 数量
            cookies = await self._cdp_network_get_all_cookies(self._current_session_id)
            state.cookies_count = len(cookies)
            
            # 获取网络请求数量
            state.network_requests_count = len(self._network_requests)
        
        state.current_target_id = self._current_target_id
        state.current_session_id = self._current_session_id
        state.page_loaded = self._page_loaded_event.is_set()
        
        return state
    
    async def get_selector_map(self, session_id: str = None) -> Dict[str, SelectorInfo]:
        """
        获取页面选择器映射
        
        :param session_id: Session ID，为空则使用当前 session
        :return: 选择器信息字典
        """
        session_id = session_id or self._current_session_id
        if not session_id or session_id not in self._sessions:
            return {}
        
        client = self._sessions[session_id]
        selector_map = {}
        
        # 获取文档根节点
        doc = await client.dom_get_document(session_id=session_id)
        root_node_id = doc.get('root', {}).get('nodeId')
        
        if root_node_id:
            # 查询所有可交互元素
            interactive_selectors = [
                'button', 'a', 'input', 'textarea', 'select', 
                '[onclick]', '[data-testid]', '[role="button"]'
            ]
            
            for selector in interactive_selectors:
                node_ids = await client.dom_query_selector_all(root_node_id, selector, session_id)
                for node_id in node_ids:
                    attrs = await client.dom_get_attributes(node_id, session_id)
                    attr_dict = {}
                    for i in range(0, len(attrs), 2):
                        if i + 1 < len(attrs):
                            attr_dict[attrs[i]] = attrs[i + 1]
                    
                    tag_name = attr_dict.get('tagName', '').lower()
                    text = await client.execute_script(
                        f"document.evaluate('//*[@nodeId={node_id}]', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue?.textContent",
                        session_id
                    )
                    
                    # 生成唯一选择器
                    unique_selector = self._generate_unique_selector(attr_dict)
                    if unique_selector:
                        selector_map[unique_selector] = SelectorInfo(
                            selector=unique_selector,
                            node_id=node_id,
                            tag_name=tag_name,
                            attributes=attr_dict,
                            text_content=text or ""
                        )
        
        return selector_map
    
    def _generate_unique_selector(self, attrs: Dict[str, str]) -> str:
        """生成唯一选择器"""
        if 'id' in attrs:
            return f"#{attrs['id']}"
        if 'data-testid' in attrs:
            return f"[data-testid='{attrs['data-testid']}']"
        if 'name' in attrs:
            return f"[name='{attrs['name']}']"
        if 'class' in attrs and attrs['class']:
            classes = attrs['class'].split()[:3]
            if classes:
                return f".{'.'.join(classes)}"
        return ""
    
    async def _resolve_target(self, target_id: str = None) -> str:
        """
        解析 target_id，获取或创建 session_id
        
        :param target_id: 目标 ID，为空则使用当前活动目标
        :return: Session ID
        """
        if not self._cdp_client_root:
            raise Exception("CDP root 连接未建立")
        
        if target_id:
            return await self.get_or_create_cdp_session(target_id)
        
        # 如果没有指定 target_id，尝试使用当前目标
        if self._current_target_id:
            return await self.get_or_create_cdp_session(self._current_target_id)
        
        # 如果没有当前目标，获取或创建默认目标
        target_id = await self._get_or_create_default_target()
        return await self.get_or_create_cdp_session(target_id)
    
    async def _ensure_session(self, target_id: str = None, session_id: str = None) -> tuple:
        """
        确保存在有效的 session，返回 (client, session_id)
        
        :param target_id: 目标 ID（优先级高）
        :param session_id: Session ID
        :return: (CDPClient, session_id)
        """
        if not self._cdp_client_root:
            raise Exception("CDP root 连接未建立")
        
        if target_id:
            session_id = await self.get_or_create_cdp_session(target_id)
        elif not session_id:
            session_id = await self._resolve_target()
        
        return self._cdp_client_root, session_id
    
    # ==================== 高层 API 封装 ====================
    
    async def navigate_to(self, url: str, target_id: str = None) -> str:
        """
        导航到指定 URL
        
        :param url: 目标 URL
        :param target_id: 目标 ID（标签页），为空则使用当前活动标签页
        :return: 框架 ID
        """
        client, session_id = await self._ensure_session(target_id)
        
        self._page_loaded_event.clear()
        frame_id = await client.page_navigate(url, session_id)
        
        # 更新当前状态
        if target_id:
            self._current_target_id = target_id
        self._current_session_id = session_id
        
        # 等待页面加载
        try:
            await asyncio.wait_for(self._page_loaded_event.wait(), timeout=60)
        except asyncio.TimeoutError:
            logging.warn(f"页面加载超时: {url}")
        
        return frame_id
    
    async def get_cookies(self, urls: List[str] = None, target_id: str = None) -> List[Dict]:
        """
        获取浏览器 Cookie
        
        :param urls: 目标 URL 列表，为空则获取所有
        :param target_id: 目标 ID（标签页），为空则使用当前活动标签页
        :return: Cookie 列表
        """
        client, session_id = await self._ensure_session(target_id)
        return await self._cdp_network_get_all_cookies(session_id, urls)
    
    async def set_cookie(self, cookie: Dict, target_id: str = None):
        """
        设置 Cookie
        
        :param cookie: Cookie 字典，包含 name, value, url 等字段
        :param target_id: 目标 ID（标签页），为空则使用当前活动标签页
        """
        client, session_id = await self._ensure_session(target_id)
        await self._cdp_network_set_cookie(cookie, session_id)
    
    async def delete_cookie(self, name: str, url: str = None, target_id: str = None):
        """
        删除 Cookie
        
        :param name: Cookie 名称
        :param url: 目标 URL
        :param target_id: 目标 ID（标签页），为空则使用当前活动标签页
        """
        client, session_id = await self._ensure_session(target_id)
        await self._cdp_network_delete_cookie(name, url, session_id)
    
    async def screenshot(self, format: str = "png", quality: int = 100, 
                        target_id: str = None) -> bytes:
        """
        捕获页面截图
        
        :param format: 图片格式 (png, jpeg, webp)
        :param quality: 图片质量 (0-100)
        :param target_id: 目标 ID（标签页），为空则使用当前活动标签页
        :return: 截图二进制数据
        """
        client, session_id = await self._ensure_session(target_id)
        return await client.page_capture_screenshot(format, quality, session_id)
    
    async def execute_script(self, script: str, target_id: str = None) -> Any:
        """
        执行 JavaScript 脚本
        
        :param script: JS 脚本
        :param target_id: 目标 ID（标签页），为空则使用当前活动标签页
        :return: 执行结果
        """
        client, session_id = await self._ensure_session(target_id)
        return await client.execute_script(script, session_id)
    
    async def click_element(self, selector: str, target_id: str = None):
        """
        点击指定元素
        
        :param selector: CSS 选择器
        :param target_id: 目标 ID（标签页），为空则使用当前活动标签页
        """
        client, session_id = await self._ensure_session(target_id)

        # enable dom
        await client.dom_enable(session_id)
        # 获取文档根节点
        doc = await client.dom_get_document(session_id=session_id)
        root_node_id = doc.get('root', {}).get('nodeId')
        
        if not root_node_id:
            return

        node_id = await client.dom_query_selector(root_node_id, selector, session_id)
        if not node_id:
            return

        node_info = await client.dom_get_box_model(node_id, session_id)
        if node_info:
            model = node_info.get('model', {})
            content = model.get('content', [])
            if len(content) >= 8:
                x = int((content[0] + content[2] + content[4] + content[6]) / 4)
                y = int((content[1] + content[3] + content[5] + content[7]) / 4)
                await client.input_dispatch_mouse_event('mousePressed', x, y, session_id)
                await client.input_dispatch_mouse_event('mouseReleased', x, y, session_id)
    
    async def type_text(self, selector: str, text: str, target_id: str = None):
        """
        在输入框中输入文本
        
        :param selector: CSS 选择器
        :param text: 要输入的文本
        :param target_id: 目标 ID（标签页），为空则使用当前活动标签页
        """
        # 使用 JavaScript 输入文本
        # script = f"""
        #     const el = document.querySelector('{selector}');
        #     if (el) {{
        #         el.value = '{text}';
        #         el.dispatchEvent(new Event('input'));
        #         el.dispatchEvent(new Event('change'));
        #     }}
        # """
        # await self.execute_script(script, target_id)

        # 上面通过js输入的在一些场景会失效，现在使用另外一种方式： 模拟键盘真实输入。
        client, session_id = await self._ensure_session(target_id)

        # enable dom
        await client.dom_enable(session_id)
        # 获取文档根节点
        doc = await client.dom_get_document(session_id=session_id)
        root_node_id = doc.get('root', {}).get('nodeId')

        if not root_node_id:
            return

        # 查询元素
        node_id = await client.dom_query_selector(root_node_id, selector, session_id)
        if not node_id:
            return

        # 获取元素位置并点击获得焦点
        await client.css_enable(session_id)
        node_info = await client.dom_get_box_model(node_id, session_id)
        if node_info:
            model = node_info.get('model', {})
            content = model.get('content', [])
            if len(content) >= 8:
                x = (content[0] + content[2] + content[4] + content[6]) / 4
                y = (content[1] + content[3] + content[5] + content[7]) / 4
                await client.input_dispatch_mouse_event('mousePressed', int(x), int(y), session_id)
                await client.input_dispatch_mouse_event('mouseReleased', int(x), int(y), session_id)

        await client.dom_focus(node_id, session_id)

        # 使用 CDP Input.dispatchKeyEvent 逐个字符输入
        for char in text:
            # await client.input_dispatch_key_event('keyDown', text=char, key=char, session_id=session_id)
            await client.input_dispatch_key_event('char', text=char, session_id=session_id)
            await client.input_dispatch_key_event('keyUp', text=char, key=char, session_id=session_id)

    async def wait_for_element(self, selector: str, timeout: int = 30,
                              target_id: str = None) -> bool:
        """
        等待元素出现
        
        :param selector: CSS 选择器
        :param timeout: 超时时间（秒）
        :param target_id: 目标 ID（标签页），为空则使用当前活动标签页
        :return: 是否找到元素
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            result = await self.execute_script(
                f"document.querySelector('{selector}') !== null",
                target_id
            )
            if result:
                return True
            await asyncio.sleep(0.5)
        
        return False
    
    # ==================== 底层 CDP 命令封装 (_cdp_* 系列) ====================
    
    async def _cdp_page_navigate(self, url: str, session_id: str = None) -> str:
        """CDP: Page.navigate"""
        session_id = session_id or self._current_session_id
        if session_id not in self._sessions:
            raise Exception("无效的 Session")
        return await self._sessions[session_id].page_navigate(url, session_id)
    
    async def _cdp_page_reload(self, session_id: str = None):
        """CDP: Page.reload"""
        session_id = session_id or self._current_session_id
        if session_id not in self._sessions:
            raise Exception("无效的 Session")
        await self._sessions[session_id].page_reload(session_id)
    
    async def _cdp_network_get_all_cookies(self, session_id: str = None, urls: List[str] = None) -> List[Dict]:
        """CDP: Network.getAllCookies"""
        session_id = session_id or self._current_session_id
        if session_id not in self._sessions:
            raise Exception("无效的 Session")
        
        # 在 CDPClient 中添加此方法，或直接调用
        result = await self._sessions[session_id]._send("Network.getAllCookies", {}, session_id)
        return result.get('cookies', [])
    
    async def _cdp_network_set_cookie(self, cookie: Dict, session_id: str = None):
        """CDP: Network.setCookie"""
        session_id = session_id or self._current_session_id
        if session_id not in self._sessions:
            raise Exception("无效的 Session")
        
        await self._sessions[session_id]._send("Network.setCookie", cookie, session_id)
    
    async def _cdp_network_delete_cookie(self, name: str, url: str = None, session_id: str = None):
        """CDP: Network.deleteCookie"""
        session_id = session_id or self._current_session_id
        if session_id not in self._sessions:
            raise Exception("无效的 Session")
        
        params = {'name': name}
        if url:
            params['url'] = url
        
        await self._sessions[session_id]._send("Network.deleteCookie", params, session_id)
    
    async def _cdp_runtime_evaluate(self, expression: str, session_id: str = None) -> Dict:
        """CDP: Runtime.evaluate"""
        session_id = session_id or self._current_session_id
        if session_id not in self._sessions:
            raise Exception("无效的 Session")
        return await self._sessions[session_id].runtime_evaluate(expression, session_id=session_id)
    
    async def _cdp_dom_query_selector(self, selector: str, session_id: str = None) -> int:
        """CDP: DOM.querySelector"""
        session_id = session_id or self._current_session_id
        if session_id not in self._sessions:
            raise Exception("无效的 Session")
        
        client = self._sessions[session_id]
        doc = await client.dom_get_document(session_id=session_id)
        root_node_id = doc.get('root', {}).get('nodeId')
        
        if root_node_id:
            return await client.dom_query_selector(root_node_id, selector, session_id)
        return -1
    
    async def _cdp_target_create_target(self, url: str) -> str:
        """CDP: Target.createTarget"""
        if not self._cdp_client_root:
            raise Exception("CDP root 连接未建立")
        return await self._cdp_client_root.target_create_target(url)
    
    async def _cdp_target_close_target(self, target_id: str) -> bool:
        """CDP: Target.closeTarget"""
        if not self._cdp_client_root:
            raise Exception("CDP root 连接未建立")
        return await self._cdp_client_root.target_close_target(target_id)
    
    # ==================== 事件系统 ====================
    
    def on(self, event_name: str, handler: Callable):
        """
        注册事件处理器
        
        :param event_name: 事件名称
        :param handler: 事件处理函数
        """
        if event_name not in self._event_handlers:
            self._event_handlers[event_name] = []
        self._event_handlers[event_name].append(handler)
    
    def off(self, event_name: str, handler: Callable):
        """
        移除事件处理器
        
        :param event_name: 事件名称
        :param handler: 事件处理函数
        """
        if event_name in self._event_handlers:
            self._event_handlers[event_name].remove(handler)
    
    async def _emit(self, event_name: str, **kwargs):
        """
        触发事件
        
        :param event_name: 事件名称
        :param kwargs: 事件参数
        """
        if event_name in self._event_handlers:
            for handler in self._event_handlers[event_name]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(**kwargs)
                    else:
                        handler(**kwargs)
                except Exception as e:
                    logging.info(f"事件处理错误 {event_name}: {e}")


# 示例使用
if __name__ == "__main__":
    import asyncio
    import time
    
    async def main():
        # 创建浏览器会话
        session = BrowserSession()
        
        # 连接到 Chrome
        if not await session.connect():
            logging.info("无法连接到 Chrome，请确保 Chrome 已启动并开启远程调试")
            return
        
        try:
            # 获取或创建 session
            session_id = await session.get_or_create_cdp_session()
            logging.info(f"当前 Session: {session_id}")
            
            # 导航到页面
            await session.navigate_to("https://www.example.com")
            logging.info("导航完成")
            
            # 获取页面标题
            title = await session.execute_script("document.title")
            logging.info(f"页面标题: {title}")
            
            # 获取状态摘要
            state = await session.get_browser_state_summary()
            logging.info(f"状态摘要: {state}")
            
            # 获取选择器映射
            selectors = await session.get_selector_map()
            logging.info(f"找到 {len(selectors)} 个可交互元素")
            
            # 捕获截图
            screenshot = await session.screenshot()
            with open("browser_session_screenshot.png", "wb") as f:
                f.write(screenshot)
            logging.info("截图已保存")
            
        finally:
            # 断开连接
            await session.disconnect()
    
    asyncio.run(main())
