from autogen import GroupChat, GroupChatManager, register_function
from src.tools.file_tools import get_file_tools
from src.tools.shell_tools import get_shell_tools
from src.tools.git_tools import get_git_tools
from autogen.agentchat.contrib.capabilities.transforms import TextMessageCompressor, MessageTransform
from autogen.agentchat.contrib.capabilities import transform_messages
from src.agent.compress import LLMTextCompressor, LLMMessagesCompressor
import copy
import os

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
    def task_trigger_condition(sender):
        # 1. 检查最新消息的内容
        try:
            # 如果没有messages参数，尝试从sender获取最后一条消息
            last_msg = sender.last_message()
            last_msg_content = last_msg.get("content", "")
            return "TODO:" in last_msg_content and len(last_msg.get("tool_calls",[])) < 1
        except Exception as e:
            # 如果发生任何异常，返回False
            return False
        return False


    user_proxy.register_nested_chats(
        chat_queue=[
            {
                "recipient": implementation_manager,
                "message": prepare_task_message,
                "summary_method": "reflection_with_llm",
            }
        ],
        trigger=task_trigger_condition
    )

    compressor = LLMMessagesCompressor(
        llm_config=manager_config,
        max_tokens=int(os.getenv("COMPRESS_MAX_TOKENS_IMPLEMENTATION", "10000")),  
        keep_first_n=1,  
        recent_rounds=5,  
        compression_prompt="""
        你是一个专业的大模型对话压缩专家, 下面是 coder, reviewer, tester 三个角色的对话。请将以下对话压缩到约 {target_token} 个token.
        请以**对话摘要**的形式进行总结，保留核心信息、关键细节和重要结论。格式要求如下：\n- User: [用户的主要需求及最新指令]\n- Assistant: [Agent 的核心进展、已执行的关键操作及目前状态]\n对于已完成的任务，请简要概括；对于未解决的错误，请详细说明其行为和报错信息。不要包含具体的工具调用明细或代码段。
        """,
        target_token=500  # 压缩目标 token 数
    )
    compressor.agent_name = "ImplementationGroup"

    architectCompressor = LLMMessagesCompressor(
        llm_config=manager_config,
        max_tokens=int(os.getenv("COMPRESS_MAX_TOKENS_ARCHITECT", "30000")),  
        keep_first_n=1,  
        recent_rounds=2,  
        compression_prompt="""你是一个专业的大模型对话压缩专家, 下面是 architect 正在调研项目或者是正在推进开发计划。请将以下对话压缩到约 {target_token} 个token。
        请简要介绍当前的工作内容及最新进度，**重点关注任务进度而非具体文件细节**。要求：以对话摘要的形式呈现，清晰说明目前完成了什么，下一步计划是什么。不要包含具体的代码内容。
        """,
        target_token=2000  # 压缩目标 token 数
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
    
    # --- 1. 剥离 Manager 工具权限 (保持不变) ---
    selector_config = copy.deepcopy(manager_config)
    selector_config.pop("tools", None)
    selector_config.pop("functions", None)

    # --- 2. 状态机定义 ---
    implementation_graph_dict = {
        coder: [reviewer, coder],
        reviewer: [coder, tester, reviewer],
        tester: [coder, tester],
    }

  # --- 3. 增强的选择指令 ---
    # 定义选择时的系统引导词，防止它输出“我需要使用工具...”这种废话
    select_speaker_prompt = (
        "You are the orchestration manager. Your ONLY job is to look at the conversation "
        "and select the next role from the list. \n"
        "Rules:\n"
        "1. If code is written, select Reviewer to check.\n"
        "2. If Reviewer found bugs or errors, select Coder to fix.\n"
        "3. If Reviewer APPROVE, select Tester.\n"
        "4. ONLY return the name of the next agent. DO NOT perform any tasks yourself."
    )

    def custom_speaker_selection(last_speaker, groupchat):
        """
        这个函数会在每一轮决定下一个是谁。
        """
        messages = groupchat.messages
        if not messages or len(messages) == 1:
            return coder # 初始发言者

        last_msg = messages[-1]

        # 检查点：如果上一条消息发起了工具调用
        if last_msg["role"] == "tool":
            return last_speaker

        # 如果没有工具调用，则使用传统的 'auto' 逻辑 (即让 Manager LLM 决定)
        return "auto"

    # --- 4. 构建 GroupChat ---
    implementation_groupchat = GroupChat(
        agents=[coder, reviewer, tester],
        messages=[],
        max_round=50,
        speaker_selection_method=custom_speaker_selection, 
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
    user_proxy.initiate_chat(manager, message=user_input, clear_history=False)
