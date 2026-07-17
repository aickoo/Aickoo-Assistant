#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Eel-based web interface for Aickoo-Assistant
"""

import eel
import json
import os
import sys
import threading
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from aickoo import logging
from aickoo.internal.app import App as AickooAssistantAPP
from aickoo.internal.db import Message
from uuid import uuid4


@dataclass
class EelMessage:
    """Message format for Eel interface"""
    role: str
    content: str
    created_at: str
    session_id: str


@dataclass
class EelSession:
    """Session format for Eel interface"""
    id: str
    title: str
    created_at: str
    summary: Optional[str] = None


class EelUI:
    """Eel-based web interface for Aickoo-Assistant"""
    
    def __init__(self, aickoo_app: AickooAssistantAPP):
        self.aickoo_app = aickoo_app
        self.eel_app = None
        self._running = False
        self._callbacks = {}

        # Set this EelUI instance for logging
        logging.set_eel_ui(self)
        
        # Initialize thinking event listener
        from aickoo.internal.listener import set_eel_ui_for_listener
        set_eel_ui_for_listener(self)
        logging.info("Thinking event listener initialized with EelUI")

    def run(self, host: str = 'localhost', port: int = 0,
            size: tuple = (1200, 800), position: tuple = None) -> None:
        """Run the Eel interface"""
        self._running = True
        
        try:
            # Initialize Eel
            eel.init('web', ['.ts', '.js', '.html', '.css'])
            
            # Expose Python functions to JavaScript
            self._expose_functions()
            
            # Start Eel
            logging.info(f"Starting Eel interface on {host}:{port}")
            
            # Start with Chrome
            try:
                eel.start('index.html', 
                         host=host,
                         port=port,
                         size=size,
                         position=position if position else (100, 100),
                         mode='chrome',
                         cmdline_args=['--disable-http-cache'],
                         block=False,
                         close_callback=self._on_browser_close)

                for agent in self.aickoo_app.config.agents:
                    eel.appendRunner(agent, agent)

                eel.switchRunner(self.aickoo_app.config.runner)
            except Exception as chrome_error:
                logging.warn(f"Chrome mode failed: {chrome_error}, trying default browser")
                # Fallback to default browser
                eel.start('index.html', 
                         host=host,
                         port=port,
                         size=size,
                         block=False,
                         close_callback=self._on_browser_close)
            
            self.eel_app = eel
            
            # Keep the application running
            while self._running:
                eel.sleep(1)
                
        except KeyboardInterrupt:
            logging.info("Eel interface interrupted by user")
        except Exception as e:
            logging.error(f"Eel interface error: {e}")
            raise
        finally:
            self.shutdown()
    
    def send_thinking_message(self, message: str) -> None:
        """Send thinking message to frontend"""
        try:
            eel.onThinking(message)()
        except Exception as e:
            logging.error(f"Error sending thinking message: {e}")

    def _expose_functions(self) -> None:
        """Expose Python functions to JavaScript"""
        
        @eel.expose
        def get_sessions() -> List[Dict[str, Any]]:
            """Get all sessions"""
            try:
                logging.info("Getting all sessions")
                sessions = self.aickoo_app.sessions.list_sessions(limit=100)
                logging.info(f"Found {len(sessions)} sessions")
                return [self._session_to_dict(session) for session in sessions]
            except Exception as e:
                logging.error(f"Error getting sessions: {e}")
                return []

        # @eel.expose
        # def create_session(title: str) -> Optional[Dict[str, Any]]:
        #     """Create a new session"""
        #     try:
        #         logging.info(f"Creating new session with title: {title}")
        #         session = self.aickoo_app.sessions.create_session(title)
        #         logging.info(f"Successfully created session: {session.id}")
        #         return self._session_to_dict(session)
        #     except Exception as e:
        #         logging.error(f"Error creating session: {e}")
        #         return None

        @eel.expose
        def get_session_messages(session_id: str) -> Optional[Dict[str, Any]]:
            """Get messages for a session"""
            try:
                logging.info(f"Getting messages for session: {session_id}")
                # Get session
                session = self.aickoo_app.sessions.get_session(session_id)
                if not session:
                    logging.warn(f"Session not found: {session_id}")
                    return None

                # Get messages
                messages = self.aickoo_app.messages.get_messages(session_id)
                logging.info(f"Found {len(messages)} messages for session: {session_id}")

                return {
                    'session': self._session_to_dict(session),
                    'messages': [self._message_to_dict(msg) for msg in messages]
                }
            except Exception as e:
                logging.error(f"Error getting session messages: {e}")
                return None

        @eel.expose
        def create_session() -> Dict[str, Any]:
            """Create a new session and return session info"""
            try:
                logging.info("Creating new session")
                session = self.aickoo_app.sessions.create_session("New Chat")
                
                # Set as current session
                self.aickoo_app.sessions.set_current_session(session)
                
                logging.info(f"Created new session: {session.id}")
                
                return {
                    'id': session.id,
                    'title': session.title,
                    'created_at': session.created_at.isoformat() if hasattr(session.created_at, 'isoformat') else str(session.created_at)
                }
            except Exception as e:
                logging.error(f"Error creating session: {e}")
                return {'error': str(e)}

        @eel.expose
        def send_message(message: str, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
            self.log_info("开始处理数据...", source="data_processor")
            logging.info(f"Sending message, session_id: {session_id}")
            # If no session_id provided, create a new session
            if not session_id:
                logging.error(f"No session_id provided from UI, cannot send message")
                return None

            # 获取conversation表中的历史记录作为额外上下文
            conversation_history = self.aickoo_app.messages.get_conversation_history(session_id, limit=50)

            # Save user message to conversation table
            logging.info(f"Saving user message to conversation table for session: {session_id}")
            self.aickoo_app.messages.save_conversation(session_id, message, "user")

            """Send a message and get AI response"""
            try:
                # Get AI response
                logging.info(f"Processing message for session: {session_id}")

                runner = self.aickoo_app.config.runner
                agent = self.aickoo_app.primary_agent_dict.get(runner)

                result_content = ''
                result_message_id = ''
                sub_session_id = f'{session_id}-{time.time()}'
                if self.aickoo_app.config.runner == '标准编排器' or agent is None:
                    response, _, result_message = self.aickoo_app.orchestrator.plan(message, session_id=sub_session_id, conversation_history=conversation_history)
                    result_content = response.content  if response is not None and hasattr(response, 'content') else None
                    result_message_id = result_message.id if result_message is not None and hasattr(result_message, 'id') else None
                else:
                    response, _, result_message = agent.start_process_message(
                        session_id=sub_session_id,
                        content=message,
                        conversation_history=conversation_history,
                        quiet=False
                    )
                    result_content = response.content if response is not None and hasattr(response, 'content') else None
                    result_message_id = result_message.id if result_message is not None and hasattr(result_message, 'id') else None

                # Save assistant response to conversation table
                logging.info(f"Saving assistant response to conversation table for session: {session_id}")
                if result_content:
                    self.aickoo_app.messages.save_conversation(session_id, result_content, "assistant")
                    logging.info(f"Successfully processed message for session: {session_id}")
                else:
                    result_content = '程序没有信息反馈，可能遇到内部错误。'
                    self.aickoo_app.messages.save_conversation(session_id, result_content, "assistant")
                    logging.info(f"Failed processed message for session: {session_id}")

                return {
                    'content': result_content,
                    'session_id': session_id,
                    'message_id': result_message_id
                }

            except Exception as e:
                result_error = f"出错了，报错如下: {e}"
                logging.error(result_error)
                self.aickoo_app.messages.save_conversation(session_id, result_error, "assistant")
                return {
                    'content': result_error,
                    'session_id': session_id,
                    'message_id': str(uuid4())
                }
                # return {'error': str(e)}

        # 在eel_ui.py的_expose_functions方法中添加：
        # @eel.expose
        # def create_orchestrator_task(session_id: str, title: str, steps: List[Dict]) -> Optional[Dict]:
        #     """创建编排任务"""
        #     try:
        #         # 转换前端步骤为OrchestratorStep对象
        #         orchestrator_steps = []
        #         for idx, step in enumerate(steps):
        #             orchestrator_steps.append(OrchestratorStep(
        #                 step_id=f"step_{idx + 1}",
        #                 name=step["name"],
        #                 description=step["description"],
        #                 agent_type=step.get("agent_type", "primary"),
        #                 prompt_template=step["prompt_template"],
        #                 context_keys=step.get("context_keys", []),
        #                 output_key=step["output_key"],
        #                 skip_on_failure=step.get("skip_on_failure", False)
        #             ))
        #
        #         # 创建任务（需先初始化编排器，建议在EelUI初始化时创建）
        #         task = self.aickoo_app.orchestrator.create_task(
        #             session_id=session_id,
        #             title=title,
        #             steps=orchestrator_steps
        #         )
        #         # execute task
        #         self.aickoo_app.orchestrator.execute_task(task.task_id)
        #         return {"task_id": task.task_id, "status": task.status}
        #     except Exception as e:
        #         logging.error(f"Create orchestrator task error: {e}")
        #         return {"error": str(e)}
        #
        # @eel.expose
        # def execute_orchestrator_task(task_id: str) -> Optional[Dict]:
        #     """执行编排任务"""
        #     try:
        #         task = self.aickoo_app.orchestrator.execute_task(task_id)
        #         return {
        #             "task_id": task.task_id,
        #             "status": task.status,
        #             "current_step": task.current_step_idx,
        #             "total_steps": len(task.steps),
        #             "context": task.context
        #         }
        #     except Exception as e:
        #         logging.error(f"Execute orchestrator task error: {e}")
        #         return {"error": str(e)}
        #
        # @eel.expose
        # def get_orchestrator_task_status(task_id: str) -> Optional[Dict]:
        #     """获取编排任务状态"""
        #     try:
        #         task = self.aickoo_app.orchestrator.get_task_status(task_id)
        #         if not task:
        #             return {"error": "Task not found"}
        #         return {
        #             "task_id": task.task_id,
        #             "status": task.status,
        #             "current_step": task.current_step_idx,
        #             "total_steps": len(task.steps),
        #             "context": task.context
        #         }
        #     except Exception as e:
        #         logging.error(f"Get task status error: {e}")
        #         return {"error": str(e)}

        @eel.expose
        def switch_runner(runner: str) -> bool:
            self.aickoo_app.config.runner = runner

        @eel.expose
        def delete_session(session_id: str) -> bool:
            """Delete a session"""
            try:
                logging.info(f"Deleting session: {session_id}")
                result = self.aickoo_app.sessions.delete_session(session_id)
                logging.info(f"Successfully deleted session: {session_id}, result: {result}")
                return result
            except Exception as e:
                logging.error(f"Error deleting session: {e}")
                return False

        @eel.expose
        def update_session(session_id: str, title: str) -> Optional[Dict[str, Any]]:
            """Update session title"""
            try:
                logging.info(f"Updating session {session_id} with title: {title}")
                session = self.aickoo_app.sessions.update_session(session_id, title=title)
                if session:
                    logging.info(f"Successfully updated session: {session_id}")
                    return self._session_to_dict(session)
                else:
                    logging.warn(f"Session not found for update: {session_id}")
                    return None
            except Exception as e:
                logging.error(f"Error updating session: {e}")
                return None

        @eel.expose
        def app_closing() -> None:
            """Called when the web app is closing"""
            logging.info("Web interface closing")
            self.shutdown()

        @eel.expose
        def ping() -> str:
            """Ping endpoint for connection testing"""
            return "pong"

        @eel.expose
        def list_files(path: str = ".") -> List[Dict[str, Any]]:
            """List files and directories in a given path"""
            try:
                import os
                import stat
                from pathlib import Path

                logging.info(f"Listing files in path: {path}")
                abs_path = Path(path).resolve()
                logging.debug(f"Resolved path: {abs_path}")

                if not abs_path.exists():
                    logging.warn(f"Path does not exist: {path}")
                    return {"error": f"Path does not exist: {path}"}

                items = []
                for item in abs_path.iterdir():
                    try:
                        stat_info = item.stat()
                        is_dir = item.is_dir()
                        items.append({
                            'name': item.name,
                            'path': str(item),
                            'is_dir': is_dir,
                            'size': stat_info.st_size if not is_dir else 0,
                            'modified': stat_info.st_mtime,
                            'permissions': stat.S_IMODE(stat_info.st_mode)
                        })
                    except (OSError, PermissionError) as e:
                        # Skip files we can't access
                        logging.debug(f"Skipping file {item.name}: {e}")
                        continue

                # Sort: directories first, then by name
                items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
                logging.info(f"Found {len(items)} items in {path}")
                return items

            except Exception as e:
                logging.error(f"Error listing files: {e}")
                return {"error": str(e)}

        @eel.expose
        def read_file(file_path: str) -> Optional[Dict[str, Any]]:
            """Read contents of a file"""
            try:
                import os
                from pathlib import Path

                logging.info(f"Reading file: {file_path}")
                file_path_obj = Path(file_path)

                if not file_path_obj.exists():
                    logging.warn(f"File does not exist: {file_path}")
                    return {"error": f"File does not exist: {file_path}"}

                if file_path_obj.is_dir():
                    logging.warn(f"Path is a directory: {file_path}")
                    return {"error": f"Path is a directory: {file_path}"}

                # Check file size (limit to 1MB for safety)
                file_size = file_path_obj.stat().st_size
                if file_size > 1024 * 1024:
                    logging.warn(f"File too large: {file_size} bytes")
                    return {"error": f"File too large: {file_size} bytes"}

                # Read file content
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                logging.info(f"Successfully read file: {file_path} ({file_size} bytes)")
                return {
                    'path': str(file_path_obj),
                    'name': file_path_obj.name,
                    'content': content,
                    'size': file_size,
                    'modified': file_path_obj.stat().st_mtime
                }

            except Exception as e:
                logging.error(f"Error reading file: {e}")
                return {"error": str(e)}

        @eel.expose
        def write_file(file_path: str, content: str) -> Dict[str, Any]:
            """Write content to a file"""
            try:
                import os
                from pathlib import Path

                logging.info(f"Writing file: {file_path} ({len(content)} bytes)")
                file_path_obj = Path(file_path)

                # Ensure parent directory exists
                parent_dir = file_path_obj.parent
                if not parent_dir.exists():
                    logging.debug(f"Creating parent directory: {parent_dir}")
                    parent_dir.mkdir(parents=True, exist_ok=True)

                # Write file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                logging.info(f"Successfully wrote file: {file_path}")
                return {
                    'success': True,
                    'path': str(file_path_obj),
                    'name': file_path_obj.name,
                    'size': len(content)
                }

            except Exception as e:
                logging.error(f"Error writing file: {e}")
                return {"error": str(e), 'success': False}

        @eel.expose
        def create_directory(path: str) -> Dict[str, Any]:
            """Create a new directory"""
            try:
                import os
                from pathlib import Path

                logging.info(f"Creating directory: {path}")
                path_obj = Path(path)
                path_obj.mkdir(parents=True, exist_ok=True)
                logging.info(f"Successfully created directory: {path}")

                return {
                    'success': True,
                    'path': str(path_obj),
                    'name': path_obj.name
                }

            except Exception as e:
                logging.error(f"Error creating directory: {e}")
                return {"error": str(e), 'success': False}

        @eel.expose
        def delete_path(path: str) -> Dict[str, Any]:
            """Delete a file or directory"""
            try:
                import os
                import shutil
                from pathlib import Path

                logging.info(f"Deleting path: {path}")
                path_obj = Path(path)

                if not path_obj.exists():
                    logging.warn(f"Path does not exist: {path}")
                    return {"error": f"Path does not exist: {path}", 'success': False}

                if path_obj.is_dir():
                    logging.debug(f"Deleting directory: {path}")
                    shutil.rmtree(path_obj)
                else:
                    logging.debug(f"Deleting file: {path}")
                    path_obj.unlink()

                logging.info(f"Successfully deleted path: {path}")
                return {
                    'success': True,
                    'path': str(path_obj),
                    'name': path_obj.name
                }

            except Exception as e:
                logging.error(f"Error deleting path: {e}")
                return {"error": str(e), 'success': False}

        @eel.expose
        def get_current_directory() -> str:
            """Get current working directory"""
            try:
                import os
                cwd = os.getcwd()
                logging.debug(f"Current working directory: {cwd}")
                return cwd
            except Exception as e:
                logging.error(f"Error getting current directory: {e}")
                return "."

        @eel.expose
        def get_logs(limit: int = 100) -> List[Dict[str, Any]]:
            """Get recent log entries"""
            try:
                from aickoo.logging import get_recent_logs
                logs = get_recent_logs(limit)
                return logs
            except Exception as e:
                logging.error(f"Error getting logs: {e}")
                return []

        # Shell command execution
        @eel.expose
        def execute_shell_command(command: str, cwd: str = None) -> Dict[str, Any]:
            """Execute a shell command and return the result"""
            import subprocess
            import os
            import threading
            
            try:
                logging.info(f"Executing shell command: {command}")
                
                # Use current directory if not specified
                if cwd is None:
                    cwd = os.getcwd()
                
                # Execute command in a separate thread to avoid blocking
                def run_command():
                    try:
                        # Start the process
                        process = subprocess.Popen(
                            command,
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            cwd=cwd,
                            bufsize=1,
                            universal_newlines=True
                        )
                        
                        # Read stdout in real-time
                        for line in iter(process.stdout.readline, ''):
                            if line:
                                self.call_js('shellOutputReceived', {
                                    'type': 'stdout',
                                    'data': line.rstrip('\n\r')
                                })
                        
                        # Read stderr in real-time
                        for line in iter(process.stderr.readline, ''):
                            if line:
                                self.call_js('shellOutputReceived', {
                                    'type': 'stderr',
                                    'data': line.rstrip('\n\r')
                                })
                        
                        # Wait for process to complete
                        return_code = process.wait()
                        
                        # Notify completion
                        self.call_js('shellOutputReceived', {
                            'type': 'complete',
                            'return_code': return_code
                        })
                        
                    except Exception as e:
                        logging.error(f"Error executing command: {e}")
                        self.call_js('shellOutputReceived', {
                            'type': 'error',
                            'data': str(e)
                        })
                
                # Start command execution in background thread
                thread = threading.Thread(target=run_command, daemon=True)
                thread.start()
                
                return {'success': True, 'message': 'Command started'}
                
            except Exception as e:
                logging.error(f"Error starting shell command: {e}")
                return {'success': False, 'error': str(e)}
        
        @eel.expose
        def change_directory(path: str) -> Dict[str, Any]:
            """Change current working directory"""
            import os
            try:
                logging.info(f"Changing directory to: {path}")
                os.chdir(path)
                new_cwd = os.getcwd()
                logging.info(f"Successfully changed to: {new_cwd}")
                return {'success': True, 'cwd': new_cwd}
            except Exception as e:
                logging.error(f"Error changing directory: {e}")
                return {'success': False, 'error': str(e)}
    
    def _session_to_dict(self, session) -> Dict[str, Any]:
        """Convert session to dictionary"""
        return {
            'id': session.id,
            'title': session.title or 'Untitled',
            'summary': session.summary,
            'created_at': session.created_at.isoformat() if hasattr(session.created_at, 'isoformat') else str(session.created_at)
        }
    
    def _message_to_dict(self, message) -> Dict[str, Any]:
        """Convert message to dictionary"""
        return {
            'id': message.id,
            'session_id': message.session_id,
            'role': message.role,
            'content': message.content,
            'created_at': message.created_at.isoformat() if hasattr(message.created_at, 'isoformat') else str(message.created_at),
            'tool_calls': message.tool_calls,
            'tool_results': message.tool_results
        }
    
    def call_js(self, function_name: str, *args) -> None:
        """Call JavaScript function from Python"""
        if self.eel_app:
            try:
                # Eel的正确调用方式是直接调用eel.function_name()
                if hasattr(self.eel_app, function_name):
                    getattr(self.eel_app, function_name)(*args)
                else:
                    logging.error(f"JS function {function_name} not found")
            except Exception as e:
                logging.error(f"Error calling JS function {function_name}: {e}")
    
    def notify_new_message(self, session_id: str, message: Dict[str, Any]) -> None:
        """Notify JavaScript about new message"""
        self.call_js('pythonMessageReceived', message)
    
    def notify_error(self, error: str) -> None:
        """Notify JavaScript about error"""
        self.call_js('pythonErrorReceived', error)
    
    def notify_sessions_updated(self) -> None:
        """Notify JavaScript that sessions were updated"""
        self.call_js('pythonSessionsUpdated')
    
    def notify_session_created(self, session: Dict[str, Any]) -> None:
        """Notify JavaScript about new session"""
        self.call_js('pythonSessionCreated', session)

    def log_to_output(self, message: str, level: str = "info", source: str = "python") -> None:
        """Send log message to frontend Output panel
        
        Args:
            message: Log message content
            level: Log level (debug, info, warning, error, success)
            source: Source of the log (e.g., 'python', 'agent', 'tool')
        """
        import time
        log_entry = {
            "timestamp": time.strftime("%H:%M:%S"),
            "level": level,
            "source": source,
            "message": message
        }
        self.call_js('pythonLogReceived', log_entry)

    def log_info(self, message: str, source: str = "python") -> None:
        """Log info message to Output panel"""
        self.log_to_output(message, "info", source)

    def log_warning(self, message: str, source: str = "python") -> None:
        """Log warning message to Output panel"""
        self.log_to_output(message, "warning", source)

    def log_error(self, message: str, source: str = "python") -> None:
        """Log error message to Output panel"""
        self.log_to_output(message, "error", source)

    def log_debug(self, message: str, source: str = "python") -> None:
        """Log debug message to Output panel"""
        self.log_to_output(message, "debug", source)

    def log_success(self, message: str, source: str = "python") -> None:
        """Log success message to Output panel"""
        self.log_to_output(message, "success", source)
    
    def _on_browser_close(self, page_path: str, websockets: list) -> None:
        """Called when the browser window is closed"""
        logging.info(f"Browser window closed: {page_path}, remaining websockets: {len(websockets)}")
        if len(websockets) == 0:
            self._running = False
    
    def shutdown(self) -> None:
        """Shutdown the Eel interface"""
        if not self._running:
            return
        
        self._running = False
        logging.info("Eel interface shutdown")