import os
from autogen import AssistantAgent, UserProxyAgent
from src.tools.file_tools import get_file_tools
from src.tools.shell_tools import get_shell_tools

def load_role_prompt(role: str) -> str:
    """从 prompts 目录加载特定角色的提示词。"""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", f"{role.lower()}.md")
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

def get_agent_configs():
    """从 .env 加载特定 Agent 的配置，包含回退机制。"""
    default_model = os.getenv("DEFAULT_MODEL_ID")
    
    return {
        "Architect": {
            "model": os.getenv("ARCHITECT_MODEL_ID") or os.getenv("PM_MODEL_ID") or default_model,
            "system_message": load_role_prompt("Architect")
        },
        "Coder": {
            "model": os.getenv("CODER_MODEL_ID") or default_model,
            "system_message": load_role_prompt("Coder")
        },
        "Reviewer": {
            "model": os.getenv("REVIEWER_MODEL_ID") or default_model,
            "system_message": load_role_prompt("Reviewer")
        },
        "Tester": {
            "model": os.getenv("TESTER_MODEL_ID") or default_model,
            "system_message": load_role_prompt("Tester")
        }
    }

def create_agents(api_key: str, base_url: str):
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
            "qwen-flash-2025-07-28": [0.00015, 0.0015]
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
        manager_model = "qwen-flash-2025-07-28"  # 使用最便宜、最快的模型
        return make_config(manager_model)

    architect = AssistantAgent(
        name="Architect",
        system_message=configs["Architect"]["system_message"],
        llm_config=make_config(configs["Architect"]["model"]),
    )

    coder = AssistantAgent(
        name="Coder",
        system_message=configs["Coder"]["system_message"],
        llm_config=make_config(configs["Coder"]["model"]),
    )

    reviewer = AssistantAgent(
        name="Reviewer",
        system_message=configs["Reviewer"]["system_message"],
        llm_config=make_config(configs["Reviewer"]["model"]),
    )

    tester = AssistantAgent(
        name="Tester",
        system_message=configs["Tester"]["system_message"],
        llm_config=make_config(configs["Tester"]["model"]),
    )

    user_proxy = UserProxyAgent(
        name="User",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=10,
        is_termination_msg=lambda x: "TERMINATE" in (x.get("content", "") or "").upper(),
        code_execution_config={"work_dir": "playground", "use_docker": False}
    )

    return architect, coder, reviewer, tester, user_proxy, make_manager_config()
