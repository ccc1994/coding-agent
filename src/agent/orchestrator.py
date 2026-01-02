from autogen import GroupChat, GroupChatManager, register_function
from src.tools.file_tools import get_file_tools
from src.tools.shell_tools import get_shell_tools
from src.tools.git_tools import get_git_tools
from autogen.agentchat.contrib.capabilities.transforms import TextMessageCompressor, MessageTransform
from autogen.agentchat.contrib.capabilities import transform_messages
from src.agent.compress import LLMTextCompressor, LLMMessagesCompressor

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

    # 创建 LLMMessagesCompressor 实例（直接实现 MessageTransform 接口）
    compressor = LLMMessagesCompressor(
        llm_config=manager_config,
        max_tokens=10000,  # 触发压缩的最大 token 数阈值
        keep_first_n=1,  # 保留最前面的消息数量，不参与压缩（默认 0）
        recent_rounds=5,  # 保留最近的轮数
        compression_prompt="你是一个专业的文本压缩专家。请将以下对话压缩到约 {target_token} 个token，保留核心信息、关键细节和重要结论, 对于已经完成的任务, 你可以一笔带过,对于工具调用及其结果,你可以忽略, 对于还未解决的报错, 你需要简单描述下什么行为导致了什么错误,发生了多少次等关键信息",
        target_token=500  # 压缩目标 token 数
    )

    # 创建 LLMMessagesCompressor 实例（直接实现 MessageTransform 接口）
    architectCompressor = LLMMessagesCompressor(
        llm_config=manager_config,
        max_tokens=5000,  # 触发压缩的最大 token 数阈值
        keep_first_n=1,  # 保留最前面的消息数量，不参与压缩（默认 0）
        recent_rounds=1,  # 保留最近的轮数
        compression_prompt="你是一个专业的文本压缩专家。请将以下对话压缩到约 {target_token} 个token，保留核心信息、关键细节和重要结论。",
        target_token=500  # 压缩目标 token 数
    )

    # 包装并注入 Agent
    context_handler = transform_messages.TransformMessages(transforms=[compressor])
    context_handler.add_to_agent(implementation_manager)
    architect_context_handler = transform_messages.TransformMessages(transforms=[architectCompressor])
    architect_context_handler.add_to_agent(architect)

    return architect


def setup_implementation_group_chat(coder, reviewer, tester, user_proxy,manager_config):
    """设置实现子聊天组，负责代码实现、审查和测试。"""
    # 定义实现子聊天组的 FSM 状态机图
    implementation_graph_dict = {
        user_proxy: [coder, reviewer, tester],
        coder: [reviewer,user_proxy],                 # 程序员 -> 审核员检查
        reviewer: [coder, tester,user_proxy],         # 审核员 -> 不通过回程序员，通过去测试员
        tester: [coder, user_proxy],           # 测试员 -> 失败回程序员，成功结束
    }

    implementation_groupchat = GroupChat(
        agents=[coder, reviewer, tester, user_proxy],
        messages=[],
        max_round=50,
        speaker_selection_method="auto",
        allowed_or_disallowed_speaker_transitions=implementation_graph_dict,
        speaker_transitions_type="allowed"
    )

    implementation_manager = GroupChatManager(
        groupchat=implementation_groupchat,
        llm_config=manager_config,
        is_termination_msg=lambda x: "TERMINATE" in x.get("content", ""),
        description="负责接受并完成 architect 的任务",
    )

    return implementation_manager

def start_multi_agent_session(manager, user_proxy, user_input: str):
    """启动协作会话。"""
    user_proxy.initiate_chat(manager, message=user_input)
