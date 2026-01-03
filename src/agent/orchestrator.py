from autogen import GroupChat, GroupChatManager, register_function
from src.tools.file_tools import get_file_tools
from src.tools.shell_tools import get_shell_tools
from src.tools.git_tools import get_git_tools
from autogen.agentchat.contrib.capabilities.transforms import TextMessageCompressor, MessageTransform
from autogen.agentchat.contrib.capabilities import transform_messages
from src.agent.compress import LLMTextCompressor, LLMMessagesCompressor
import copy

def setup_orchestration(architect, coder, reviewer, tester, user_proxy, manager_config):
    """注册工具并设置带有规范驱动流程的嵌套 GroupChat。"""
    
    # 设置实现子聊天组
    implementation_manager = setup_implementation_group_chat(coder, reviewer, tester,user_proxy, manager_config)
    
    def prepare_task_message(recipient, messages, sender, config):
        full_content = messages[-1].get("content", "")
        # 如果你想把 "TODO:" 之前的内容（通常是思考过程）过滤掉
        if "TODO:" in full_content:
            return full_content.split("TODO:", 1)[-1].strip()
        return full_content
    def task_trigger_condition(sender, messages=None):
        # 1. 检查最新消息的内容
        try:
            if messages and len(messages) > 0:
                # 如果提供了messages参数，使用最新消息
                last_msg_content = messages[-1].get("content", "")
                return "TODO:" in last_msg_content
            else:
                # 如果没有messages参数，尝试从sender获取最后一条消息
                last_msg_content = sender.last_message().get("content", "")
                return "TODO:" in last_msg_content
        except Exception as e:
            # 如果发生任何异常，返回False
            return False


    user_proxy.register_nested_chats(
        chat_queue=[
            {
                "recipient": implementation_manager,
                "message": prepare_task_message,
                "summary_method": "last_msg",
            }
        ],
        trigger=task_trigger_condition
    )

    compressor = LLMMessagesCompressor(
        llm_config=manager_config,
        max_tokens=5000,  
        keep_first_n=1,  
        recent_rounds=5,  
        compression_prompt="你是一个专业的文本压缩专家。请将以下对话压缩到约 {target_token} 个token，保留核心信息、关键细节和重要结论, 对于已经完成的任务, 你可以一笔带过,对于工具调用及其结果,你可以忽略, 对于还未解决的报错, 你需要简单描述下什么行为导致了什么错误,发生了多少次等关键信息",
        target_token=500  # 压缩目标 token 数
    )
    compressor.agent_name = "ImplementationGroup"

    architectCompressor = LLMMessagesCompressor(
        llm_config=manager_config,
        max_tokens=5000,  
        keep_first_n=1,  
        recent_rounds=1,  
        compression_prompt="你是一个专业的文本压缩专家。请将以下对话压缩到约 {target_token} 个token，保留核心信息、关键细节和重要结论。",
        target_token=500  # 压缩目标 token 数
    )
    architectCompressor.agent_name = "Architect"

    # 包装并注入 Agent
    context_handler = transform_messages.TransformMessages(transforms=[compressor])
    context_handler.add_to_agent(implementation_manager)
    context_handler.add_to_agent(coder)
    context_handler.add_to_agent(reviewer)
    context_handler.add_to_agent(tester)
    architect_context_handler = transform_messages.TransformMessages(transforms=[architectCompressor])
    architect_context_handler.add_to_agent(architect)

    return architect

def setup_implementation_group_chat(coder, reviewer, tester, user_proxy, manager_config):

    # --- 1. 关键优化：剥离 Manager 的工具权限 ---
    # 深度拷贝配置，并清空 tools/functions，防止 Manager 尝试“亲自下场”干活
    selector_config = copy.deepcopy(manager_config)
    if "tools" in selector_config:
        print("remove tools", selector_config["tools"])
        del selector_config["tools"]
    if "functions" in selector_config:
        print("remove functions", selector_config["tools"])
        del selector_config["functions"]

    # --- 2. 状态机定义 ---
    implementation_graph_dict = {
        coder: [reviewer],
        reviewer: [coder, tester],
        tester: [coder],
    }

    # --- 3. 增强的选择指令 ---
    # 定义选择时的系统引导词，防止它输出“我需要使用工具...”这种废话
    select_speaker_prompt = (
        "You are the orchestration manager. Your ONLY job is to look at the conversation "
        "and select the next role from the list. \n"
        "Rules:\n"
        "1. If code is written, select Reviewer to check.\n"
        "2. If Reviewer found bugs, select Coder to fix.\n"
        "3. If Reviewer passed, select Tester.\n"
        "4. ONLY return the name of the next agent. DO NOT perform any tasks yourself."
    )

    implementation_groupchat = GroupChat(
        agents=[coder, reviewer, tester],
        messages=[],
        max_round=50,
        speaker_selection_method="auto", 
        allowed_or_disallowed_speaker_transitions=implementation_graph_dict,
        speaker_transitions_type="allowed",
        select_speaker_prompt_template=select_speaker_prompt 
    )

    # --- 4. 构建 Manager ---
    implementation_manager = GroupChatManager(
        groupchat=implementation_groupchat,
        llm_config=selector_config, 
        is_termination_msg=lambda x: "TERMINATE" in x.get("content", ""),
        description="A manager who ONLY orchestrates the workflow between Coder, Reviewer, and Tester.",
        system_message="You are the manager of a coding group chat. Your role is to select the next speaker."
    )

    return implementation_manager

def start_multi_agent_session(manager, user_proxy, user_input: str):
    """启动协作会话。"""
    user_proxy.initiate_chat(manager, message=user_input)
