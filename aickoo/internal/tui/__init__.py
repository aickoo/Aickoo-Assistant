#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Terminal User Interface for Aickoo-Assistant using Textual
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Button, Static, Input, TextArea, Label
from textual.screen import Screen
from textual import events
from typing import Optional
from aickoo import logging
from aickoo.internal.app import App as AickooAssistantAPP


class ChatScreen(Screen):
    """Main chat screen"""
    
    def __init__(self, app: AickooAssistantAPP):
        super().__init__()
        self.aickoo_app = app
        self.current_session = None
    
    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield Container(
            Vertical(
                Static("Chat Messages", id="messages-container"),
                id="messages-area"
            ),
            Horizontal(
                TextArea(id="input-area"),
                Button("Send", id="send-button"),
                id="input-container"
            ),
            id="main-container"
        )
        yield Footer()
    
    def on_mount(self) -> None:
        """Called when screen is mounted"""
        self.query_one("#input-area").focus()
        
        # Load or create a session
        sessions = self.aickoo_app.sessions.list_sessions(limit=1)
        if sessions:
            self.current_session = sessions[0]
            self.aickoo_app.sessions.set_current_session(self.current_session)
            self.load_messages()
        else:
            self.current_session = self.aickoo_app.sessions.create_session("New Session")
    
    def load_messages(self) -> None:
        """Load messages for current session"""
        if not self.current_session:
            return
        
        messages = self.aickoo_app.messages.get_messages(self.current_session.id)
        messages_container = self.query_one("#messages-container")
        
        # Clear existing messages
        messages_container.remove_children()
        
        # Add messages
        for msg in messages:
            message_widget = Static(f"{msg.role}: {msg.content}")
            messages_container.mount(message_widget)
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "send-button":
            self.send_message()
    
    def on_key(self, event: events.Key) -> None:
        """Handle key presses"""
        if event.key == "enter" and event.ctrl:
            self.send_message()
    
    def send_message(self) -> None:
        """Send the current message"""
        input_area = self.query_one("#input-area")
        message_text = input_area.text.strip()
        
        if not message_text or not self.current_session:
            return
        
        # Clear input
        input_area.text = ""
        
        # Add user message to UI
        messages_container = self.query_one("#messages-container")
        messages_container.mount(Static(f"user: {message_text}"))
        
        # Add user message to database
        user_message = self.aickoo_app.messages.create_message(
            session_id=self.current_session.id,
            role="user",
            content=message_text
        )
        
        # Get AI response
        try:
            response = self.aickoo_app.primary_agent.process_message(
                session_id=self.current_session.id,
                message=user_message,
                quiet=False
            )
            
            # Add assistant message to database
            self.aickoo_app.messages.create_message(
                session_id=self.current_session.id,
                role="assistant",
                content=response
            )
            
            # Add assistant message to UI
            messages_container.mount(Static(f"assistant: {response}"))
            
        except Exception as e:
            logging.error(f"Failed to get AI response: {e}")
            messages_container.mount(Static(f"Error: {e}"))


class TUI(App):
    """Main TUI application"""
    
    CSS = """
    #main-container {
        layout: vertical;
        height: 100%;
    }
    
    #messages-area {
        height: 80%;
        border: solid $primary;
        overflow-y: auto;
    }
    
    #messages-container {
        padding: 1;
    }
    
    #input-container {
        height: 20%;
        border-top: solid $primary;
    }
    
    #input-area {
        width: 80%;
    }
    
    #send-button {
        width: 20%;
    }
    """
    
    def __init__(self, aickoo_app: AickooAssistantAPP):
        super().__init__()
        self.aickoo_app = aickoo_app
    
    def on_mount(self) -> None:
        """Called when app is mounted"""
        self.push_screen(ChatScreen(self.aickoo_app))
    
    def run(self) -> None:
        """Run the TUI"""
        try:
            super().run()
        except KeyboardInterrupt:
            logging.info("TUI interrupted by user")
        except Exception as e:
            logging.error(f"TUI error: {e}")
            raise