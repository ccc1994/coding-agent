import os
from autogen import AssistantAgent, UserProxyAgent, register_function
from src.tools.file_tools import get_file_tools
from src.tools.shell_tools import get_shell_tools
from src.tools.git_tools import get_git_tools
from src.tools.index_tools import semantic_code_search
from src.tools.lsp_tools import get_lsp_tools
import warnings

def load_role_prompt(role: str) -> str:
    """从 prompts 目录加载特定角色的提示词。"""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", f"{role.lower()}.md")
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

def get_agent_configs():
    return {
        "Architect": {
            "model": os.getenv("ARCHITECT_MODEL_ID"),
            "system_message": load_role_prompt("Architect"),
        },
        "Coder": {
            "model": os.getenv("CODER_MODEL_ID"),
            "system_message": load_role_prompt("Coder")
        },
        "Reviewer": {
            "model": os.getenv("REVIEWER_MODEL_ID"),
            "system_message": load_role_prompt("Reviewer")
        },
        "Tester": {
            "model": os.getenv("TESTER_MODEL_ID"),
            "system_message": load_role_prompt("Tester")
        }
    }

def create_agents(api_key: str, base_url: str, mcp_manager=None):
    """初始化带有特定角色模型配置的 AutoGen Agent。"""
    configs = get_agent_configs()
    
    # 校验是否设置了所有必需的模型 ID
    missing_models = [role for role, config in configs.items() if not config.get("model")]
    if missing_models:
        raise ValueError(f"以下角色在 .env 中缺失模型 ID：{', '.join(missing_models)}")

    def make_config(model_id):
        cache_seed_raw = os.getenv("CACHE_SEED", "42")
        # Handle "None" or empty string to disable caching
        cache_seed = None if cache_seed_raw.lower() == "none" or not cache_seed_raw else int(cache_seed_raw)
        
        # 价格配置 (单位: 元/1k tokens)
        prices = {
            "qwen-plus-2025-07-28": [0.0008, 0.002],
            "qwen-flash-2025-07-28": [0.00015, 0.0015],
            "qwen3-coder-plus": [0.00015, 0.0015],
        }
        
        config = {
            "model": model_id,
            "api_key": api_key,
            "base_url": base_url,
            "api_type": "openai",
        }
        
        if model_id in prices:
            config["price"] = prices[model_id]
            
        return {
            "config_list": [config],
            "cache_seed": cache_seed
        }
    
    def make_manager_config():
        """为 GroupChatManager 创建轻量级配置，使用最便宜的模型"""
        manager_model = os.getenv("GENERAL_MODEL_ID")
        return make_config(manager_model)

    # 为 Architect 创建配置
                
    architect = AssistantAgent(
        name="Architect",
        system_message=configs["Architect"]["system_message"],
        llm_config=make_config(configs["Architect"]["model"]),
        code_execution_config=False
    )

    coder = AssistantAgent(
        name="Coder",
        system_message=configs["Coder"]["system_message"],
        llm_config=make_config(configs["Coder"]["model"]),
        code_execution_config=False
    )

    reviewer = AssistantAgent(
        name="Reviewer",
        system_message=configs["Reviewer"]["system_message"],
        llm_config=make_config(configs["Reviewer"]["model"]),
        code_execution_config=False
    )

    tester = AssistantAgent(
        name="Tester",
        system_message=configs["Tester"]["system_message"],
        llm_config=make_config(configs["Tester"]["model"]),
        code_execution_config=False
    )

    user_proxy = UserProxyAgent(
        name="User",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=30,
        is_termination_msg=lambda x: "TERMINATE" in (x.get("content", "") or "").upper(),
        code_execution_config=False
    )

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*is being overridden.*")
        # 1. 为 Coder 注册文件工具
        for tool in get_file_tools():
            register_function(
                tool,
                caller=coder,
                executor=coder,
                name=tool.__name__,
                description=tool.__doc__
            )

        # 2. 为 Architect 注册文件工具（读取目录和文件内容）
        for tool in get_file_tools("read"):
            register_function(
                tool,
                caller=architect,
                executor=user_proxy, 
                name=tool.__name__,
                description=tool.__doc__
            )
            register_function(
                tool,
                caller=reviewer,
                executor=reviewer, 
                name=tool.__name__,
                description=tool.__doc__
            )
            register_function(
                tool,
                caller=tester,
                executor=tester, 
                name=tool.__name__,
                description=tool.__doc__
            )
            
        # 3. 为相关角色注册 LSP 工具
        for tool in get_lsp_tools():
            register_function(
                tool,
                caller=architect,
                executor=user_proxy,
                name=tool.__name__,
                description=tool.__doc__
            )
            register_function(
                tool,
                caller=coder,
                executor=coder,
                name=tool.__name__,
                description=tool.__doc__
            )
            register_function(
                tool,
                caller=reviewer,
                executor=reviewer,
                name=tool.__name__,
                description=tool.__doc__
            )

        # 4. 注册代码搜索工具 (LlamaIndex)
        register_function(
            semantic_code_search,
            caller=architect,
            executor=user_proxy,
            name="semantic_code_search",
            description=semantic_code_search.__doc__   
        )
        register_function(
            semantic_code_search,
            caller=coder,
            executor=coder,
            name="semantic_code_search",
            description=semantic_code_search.__doc__
        )
        register_function(
            semantic_code_search,
            caller=reviewer,
            executor=reviewer,
            name="semantic_code_search",
            description=semantic_code_search.__doc__
        )

        # 2. 为 Coder 注册 Shell 工具（用于运行构建、测试等命令）
        for tool in get_shell_tools():
            register_function(
                tool,
                caller=coder,
                executor=coder,
                name=tool.__name__,
                description=tool.__doc__
            )
            register_function(
                tool,
                caller=reviewer,
                executor=reviewer,
                name=tool.__name__,
                description=tool.__doc__
            )

        # 4. 为 Tester 注册 Shell 工具
        for tool in get_shell_tools():
            register_function(
                tool,
                caller=tester,
                executor=tester,
                name=tool.__name__,
                description=tool.__doc__
            )

    # 5. 注册 MCP 工具
    if mcp_manager:
        # Register definitions for Agents (Callers)
        for tool_def in mcp_manager.tools:
            for agent in [architect, coder, reviewer]:
                if agent.llm_config:
                    if "tools" not in agent.llm_config["config_list"][0]:
                        agent.llm_config["config_list"][0]["tools"] = []
                    # Avoid duplicates
                    existing_tools = [t["function"]["name"] for t in agent.llm_config["config_list"][0]["tools"]]
                    if tool_def["function"]["name"] not in existing_tools:
                        agent.llm_config["config_list"][0]["tools"].append(tool_def)
        
        # Register functions for UserProxy (Executor)
        # Note: AutoGen executes tools via the executor agent.
        # We need to ensure the function map is populated.
        # We can update user_proxy._function_map directly or use register_function in a way that respects it?
        # register_function helper registers to agent.function_map.
        
        for name, func in mcp_manager.tool_functions.items():
            user_proxy.register_function(
                function_map={name: func}
            )
            # Also register for Coder self-execution if needed? 
            # Coder has code_execution_config=False, so it relies on executor (UserProxy) or itself if it is the executor.
            # In previous blocks: executor=coder for some tools.
            # Let's register for Coder as executor too, just in case.
            coder.register_function(
                function_map={name: func}
            )

    return architect, coder, reviewer, tester, user_proxy, make_manager_config()
