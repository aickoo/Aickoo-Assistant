#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Task Orchestrator for Aickoo-Assistant
支持顺序分步执行的任务编排，适配小说编写、开发等场景
"""
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from sympy import false

from aickoo import logging
from aickoo.internal.db import Session, Message
from aickoo.internal.app.agents import PrimaryAgent, Agent, LLMResponse
from aickoo.internal.app.messages import MessageManager
from aickoo.internal.app.llm import deepseek_client
from aickoo.internal.listener import emit_thinking_event
import traceback


@dataclass
class OrchestratorStep:
    """编排器步骤定义"""
    step_id: str  # 步骤唯一ID
    name: str  # 步骤名称（如"小说大纲生成"、"代码模块设计"）
    description: str  # 步骤描述
    agent_type: str  # 执行该步骤的Agent类型（"primary" / "task_agent"）
    required_agent: str  # 所需agent的名称
    prompt_template: str = field(init=False)  # 步骤执行的提示词模板（支持上下文变量替换）
    conversation_history: List
    skip_on_failure: bool = False  # 失败时是否跳过后续步骤
    dependencies: List[str] = field(default_factory=list)  # 该步骤依赖的上下文键
    result: any = field(init=False)
    status: str = "pending" # pending / running / completed / failed


@dataclass
class OrchestratorTask:
    """编排器任务定义"""
    task_id: str
    session_id: str
    title: str
    steps: List[OrchestratorStep]
    context: Dict[str, Any] = field(default_factory=dict)  # 步骤间共享上下文
    current_step_idx: int = 0  # 当前执行的步骤索引
    status: str = "pending"  # pending / running / completed / failed


class SequentialOrchestrator:
    """顺序执行的任务编排器"""

    def __init__(self, primary_agent_dict: Dict[str, Any], message_manager: MessageManager):
        """
        初始化编排器
        :param primary_agent_dict: Agent实例工厂，格式{"primary": PrimaryAgent实例, "task_agent": Agent实例}
        :param message_manager: 消息管理器（用于存储步骤执行记录）
        """
        self.primary_agent_dict = primary_agent_dict
        self.message_manager = message_manager
        self.running_tasks: Dict[str, OrchestratorTask] = {}  # 运行中的任务

    def plan(self, content: str, session_id="", conversation_history: List[str] = None):
        # 数据库创建用户内容
        user_message = self.message_manager.create_message(
            session_id=session_id,
            role="user",
            content=content
        )

        # agents信息收集供llm选择
        agents = []
        for name, agent in self.primary_agent_dict.items():
            agents.append({"name": name, "description": agent.config.description})

        # 任务拆解子提示词
        TASK_SPLIT_PROMPT = f"""
        ## 任务
        根据用户要求编排任务清单，必须尽可能的执行并完成用户任务，任务执行的相关要求和清单参照参照本提示词的相关内容。
        
        ## 要求：基于用户需求，将其拆解为有序的子任务列表，需满足：
        1. 子任务按「依赖顺序」排列（如：先编写核心函数，再写测试用例）；后面任务若提及前面任务内容，需确认前面相关内容或者结果存在。
        2. 每个子任务明确「输入」「输出」「执行工具/Agent」；
        3. 子任务粒度不超过10个，避免过度拆解；
        4. 若需求包含多语言/多模块，按模块拆分。
        
        ## 可用agent清单
        {json.dumps(agents, ensure_ascii=false)}

        ## 输出格式,严格执行json格式返回：
        [
          {{
            "index": 子任务的纯数字id,也是顺序标识，数字越大标识步骤越在后面，例如 1，2，3.最先执行1，再2，再3
            "name": "子任务名称",
            "description": "子任务详细描述",
            "required_agent": "所需的Agent名称",
            "dependencies": []  # 依赖的子任务ID数组
          }},
          ...
        ]
        
        ## 用户任务
        {content}
        """
        messages = []

        if conversation_history:
            messages.extend(conversation_history)

        # 以system角色进行划分任务，暂时不用此方式，改以用户角色分解任务
        # 当有历史内容的时候，就不添加系统信息了
        # if len(conversation_history) == 0:
        #     messages.append({"role": "system", "content": TASK_SPLIT_PROMPT})
        # messages.append({"role": "user", "content": content})

        # 用户角色分解任务
        messages.append({"role": "user", "content": TASK_SPLIT_PROMPT})

        # Emit thinking event for task planning
        emit_thinking_event("正在分析用户需求并规划任务...")

        # json 返回，确认格式是否符合要求，重复执行最多三次。
        steps = []
        retry_times = 0
        while retry_times < 3:
            try:
                response = deepseek_client.generate_response(messages=messages)
                if response is None:
                    return response, [], 'LLM没有返回内容，请确认是否LLM大模型可用？'

                llm_content = response.json_content
                if llm_content is None or llm_content.strip() == '':
                    llm_content = response.content

                if llm_content is None or llm_content.strip() == '':
                    return response, [], 'LLM没有返回可用内容'

                # 处理步骤安排
                resp_step_list = json.loads(llm_content)

                # 整体任务作为context
                conversation_history_step = []
                # conversation_history_step = [{"role": "user", "content": content}]

                # create orchestrator step
                steps = []
                finish_flag = True

                for resp_step in resp_step_list:
                    # 去除不合格的数据
                    if resp_step.get('index') is None or resp_step.get('name') is None or resp_step.get('description') is None or resp_step.get("required_agent" is None):
                        finish_flag = False
                        break
                    # 拼装任务步骤
                    step = OrchestratorStep(step_id=resp_step.get('index'),
                                            name=resp_step.get('name'),
                                            description=resp_step.get('description'),
                                            agent_type='primary',
                                            required_agent=resp_step.get('required_agent'),
                                            dependencies=resp_step.get('dependencies'),
                                            conversation_history=conversation_history_step
                                            )
                    steps.append(step)

                if finish_flag:
                    break
            except Exception as e:
                print(str(e))
                retry_times = retry_times + 1
                logging.error(f"返回数据格式异常，将重试{retry_times}")
                continue

        if steps is None or len(steps) == 0:
            return response, [], '编排器其没有可以继续执行的任务'

        # Emit thinking event for task execution
        emit_thinking_event(f"任务规划完成，将执行{len(steps)}个步骤")

        task: OrchestratorTask = self.create_task(session_id=session_id, title=content, steps=steps)
        return self.execute_task(task_id=task.task_id)


    def create_task(self, session_id: str, title: str, steps: List[OrchestratorStep]) -> OrchestratorTask:
        """创建新的编排任务"""
        task_id = f"task_{session_id}_{len(self.running_tasks) + 1}"
        task = OrchestratorTask(
            task_id=task_id,
            session_id=session_id,
            title=title,
            steps=steps
        )
        self.running_tasks[task_id] = task
        logging.info(f"Created orchestrator task: {task_id} for session {session_id}")
        return task

    def execute_task(self, task_id: str, quiet: bool = False) -> OrchestratorTask:
        """执行编排任务（顺序执行所有步骤）"""
        if task_id not in self.running_tasks:
            raise ValueError(f"Task {task_id} not found")

        task = self.running_tasks[task_id]
        task.status = "running"
        logging.info(
            f"Start executing task {task_id} (session: {task.session_id}), total steps: {len(task.steps)}")

        response = tool_results = result_message = None
        # 顺序执行每个步骤
        while task.current_step_idx < len(task.steps):
            step = task.steps[task.current_step_idx]
            try:
                logging.info(f"Executing step {task.current_step_idx + 1}: {step.name} (step_id: {step.step_id})")

                # 1. 构建步骤执行的上下文
                step.status = 'running'
                # step_context = self._build_step_context(task, step)
                # 替换提示词模板中的变量
                # step_prompt = self._render_prompt_template(step.prompt_template, step_context)

                # 2. 创建步骤执行的Message（用于Agent调用）
                # step_message = self.message_manager.create_message_without_store_db(
                #     session_id=task.session_id,
                #     role="user",
                #     content=step.description   # content=step_prompt
                # )

                # Emit thinking event for step execution
                emit_thinking_event(f"正在执行步骤{step.step_id}: {step.name}...")
                
                # 3. 获取对应Agent并执行
                agent = self.primary_agent_dict.get(step.required_agent)
                response, tool_results, result_message = agent.start_process_message(
                    session_id=task.session_id,
                    content=str({"index":step.index if hasattr(step, 'index') else "",
                                 "name":step.name if hasattr(step, 'name') else "",
                                 "description":step.description if hasattr(step, 'description') else "",
                                 "dependencies":step.dependencies if hasattr(step, 'dependencies') else "",
                                 "required_agent":step.required_agent if hasattr(step, 'required_agent') else ""}),
                    quiet=quiet,
                    role='user',
                    conversation_history=step.conversation_history
                )
                # response, tool_results, result_message = agent.process_message_loop(
                #     session_id=task.session_id,
                #     message=step_message,
                #     quiet=quiet
                # )

                # 4. 存储步骤执行结果到DB
                # self._save_step_result(task, step, response, tool_results)

                # 5. 将步骤输出存入任务上下文
                if response is None:
                    step.result = ""
                    logging.error(f"Step {step.step_id} failed: response is None")
                    task.current_step_idx = task.current_step_idx + 1
                    continue
                step.result = response.content
                # task.context[step.output_key] = response.content
                logging.info(f"Step {step.step_id} completed, result: {step.result}")
                
                # Emit thinking event for step completion
                emit_thinking_event(f"步骤{step.step_id}执行完成")

                # 6. 推进到下一个步骤
                task.current_step_idx = task.current_step_idx + 1

            except Exception as e:
                logging.error(traceback.print_exc())
                logging.error(f"Step {step.step_id} failed: {str(e)}")
                
                # Emit thinking event for step failure
                emit_thinking_event(f"步骤{step.step_id}执行失败: {str(e)}")

                task.status = "failed"
                if step.skip_on_failure:
                    task.current_step_idx += 1  # 跳过当前失败步骤，继续下一个
                else:
                    break

        # 任务执行完成
        if task.current_step_idx >= len(task.steps):
            task.status = "completed"
            logging.info(f"Task {task_id} completed successfully")
            # Emit thinking event for task completion
            emit_thinking_event("所有任务步骤执行完成")

        self.running_tasks[task_id] = task
        # return task

        return response, tool_results, result_message

    def _build_step_context(self, task: OrchestratorTask, step: OrchestratorStep) -> Dict[str, Any]:
        """构建步骤执行的上下文（仅包含该步骤依赖的键）"""
        step_context = {"task_title": task.title, "steps": [{"step_name": step.name, "step_description": step.description, }]  }
        # for key in step.dependencies:
        #     if key in task.context:
        #         step_context[key] = task.context[key]
        #     else:
        #         logging.warn(f"Step {step.step_id} missing context key: {key}, using empty string")
        #         step_context[key] = ""
        return step_context

    def _render_prompt_template(self, template: str, context: Dict[str, Any]) -> str:
        """渲染提示词模板（替换{{key}}为上下文值）"""
        rendered = template
        for key, value in context.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        return rendered

    def _save_step_result(self, task: OrchestratorTask, step: OrchestratorStep,
                          response: LLMResponse, tool_results: List[Dict]):
        """将步骤执行结果保存到数据库（Message）"""
        # 1. 保存步骤执行的请求（用户视角）
        self.message_manager.create_message(
            session_id=task.session_id,
            role="user",
            content=f"【编排步骤执行】：{step.name}\n{step.description}"
        )

        # 2. 保存步骤执行的响应（助手视角）
        self.message_manager.create_message(
            session_id=task.session_id,
            role="assistant",
            content=response.content,
            reasoning_content=response.reasoning_content,
            tool_calls=response.tool_calls,
            tool_results=tool_results
        )

    def get_task_status(self, task_id: str) -> Optional[OrchestratorTask]:
        """获取任务执行状态"""
        return self.running_tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """取消正在执行的任务"""
        if task_id in self.running_tasks:
            task = self.running_tasks[task_id]
            task.status = "cancelled"
            logging.info(f"Task {task_id} cancelled")
            return True

        return False