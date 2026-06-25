import os

from langchain_community.chat_models import ChatTongyi
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent

from app.agent.agent_middleware import get_middleware
from app.agent.runtime.budget import get_runtime_budget
from app.agent.skill_registry import get_default_tools
from app.core.logger_handler import logger
from app.models.model_config import UserModelConfig
from app.utils.model_provider import create_chat_model_from_config, create_ollama_chat_model
from app.utils.prompt_loader import load_prompt


class AgentFactory:
    """
    生产 Agent 工厂类
    支持：
    - 每次调用创建全新的 AgentExecutor 实例
    - 动态注入工具、提示词、模型配置
    - 支持异步流式调用
    """

    def __init__(
            self,
            model: str = "qwen3-max",
            api_key: str | None = None,
            default_tools: list[BaseTool] | None = None,
            default_middleware: list | None = None,
            default_system_prompt: str | None = None,
    ):
        self.model = model
        self.api_key = api_key or os.getenv("CHAT_API_KEY")
        self.default_tools = default_tools or self._get_default_tools()
        self.default_middleware = default_middleware or self._get_default_middleware()
        self.default_system_prompt = default_system_prompt or self._get_default_system_prompt()

    @staticmethod
    def _get_default_tools() -> list[BaseTool]:
        """获取默认工具列表"""
        return get_default_tools()

    def _get_default_middleware(self) -> list:
        """获取默认中间件列表"""
        return get_middleware()

    @staticmethod
    def _get_default_system_prompt() -> str:
        """获取默认系统提示词"""
        return load_prompt('main_prompt')

    def create_chat_model(self, custom_model: str | None = None, model_config: UserModelConfig | None = None):
        """根据LLM_TYPE创建聊天模型实例（context_builder 摘要也复用本方法）。"""
        if model_config is not None:
            logger.info(f"Agent using user model config: {model_config.provider} / {model_config.model_name}")
            return create_chat_model_from_config(model_config, streaming=True)

        llm_type = os.getenv("LLM_TYPE", "ALIYUN").upper()

        if llm_type == "OLLAMA":
            model_name = custom_model or os.getenv("OLLAMA_MODEL_NAME", self.model)
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

            logger.info(f"🤖 Agent使用Ollama模型: {model_name}")

            return create_ollama_chat_model(
                model_name=model_name,
                base_url=base_url,
                streaming=True,
            )

        elif llm_type == "ALIYUN":
            api_key = os.getenv("ALIYUN_ACCESS_KEY_SECRET")
            base_url = os.getenv("ALIYUN_BASE_URL")
            model_name = custom_model or os.getenv("ALIYUN_MODEL_NAME", os.getenv("CHAT_MODEL_NAME", self.model))

            logger.info(f"🤖 Agent使用阿里云百炼模型: {model_name}")

            return ChatTongyi(
                model=model_name,
                api_key=api_key,
                base_url=base_url,
                streaming=True,
                top_p=0.7,
            )

        else:
            raise ValueError(f"不支持的LLM_TYPE: {llm_type}，可选值: ALIYUN, OLLAMA")

    def _create_prompt(self) -> ChatPromptTemplate:
        """内部方法：创建提示词模板（system_prompt 在 invoke 时经 inputs 注入）。"""
        return ChatPromptTemplate.from_messages([
            ("system", "{system_prompt}"),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

    def create_agent_executor(
            self,
            custom_tools: list[BaseTool] | None = None,
            custom_model: str | None = None,
            model_config: UserModelConfig | None = None,
            custom_system_prompt: str | None = None,
            verbose: bool = True,
            return_intermediate_steps: bool = True,
            **kwargs
    ) -> AgentExecutor:
        """
        核心工厂方法：创建全新的 AgentExecutor 实例
        每次调用都会生成新的实例，彻底避免全局状态污染
        """
        # 1. 创建组件（每次都重新创建，避免全局状态污染）
        chat_model = self.create_chat_model(custom_model, model_config)
        prompt = self._create_prompt()
        tools = self.default_tools if custom_tools is None else custom_tools

        # 2. 创建 Agent
        agent = create_tool_calling_agent(chat_model, tools, prompt)

        # 3. 创建 Executor
        return AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=verbose,
            return_intermediate_steps=return_intermediate_steps,
            handle_parsing_errors=True,
            max_iterations=get_runtime_budget()["max_iterations"],
            **kwargs
        )


# 初始化全局工厂配置
agent_factory = AgentFactory()
