from autogen import GroupChat, GroupChatManager, register_function
from src.tools.file_tools import get_file_tools
from src.tools.shell_tools import get_shell_tools
from src.tools.git_tools import get_git_tools

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
        max_round=30,
        speaker_selection_method="auto",
        allowed_or_disallowed_speaker_transitions=implementation_graph_dict,
        speaker_transitions_type="allowed"
    )

    implementation_manager = GroupChatManager(
        groupchat=implementation_groupchat,
        llm_config=manager_config,
        is_termination_msg=lambda x: "TERMINATE" in x.get("content", ""),
        description="负责接受并完成 architect 的任务"
    )

    return implementation_manager

def setup_orchestration(architect, coder, reviewer, tester, user_proxy, manager_config):
    """注册工具并设置带有规范驱动流程的嵌套 GroupChat。"""
    
    # 1. 为 Coder 注册文件工具
    for tool in get_file_tools():
        register_function(
            tool,
            caller=coder,
            executor=user_proxy,
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

    # 2. 为 Coder 注册 Shell 工具（用于运行构建、测试等命令）
    for tool in get_shell_tools():
        register_function(
            tool,
            caller=coder,
            executor=user_proxy,
            name=tool.__name__,
            description=tool.__doc__
        )
        register_function(
            tool,
            caller=reviewer,
            executor=user_proxy,
            name=tool.__name__,
            description=tool.__doc__
        )

    # 3. 为 Coder 注册 Git 工具（版本控制）
    for tool in get_git_tools():
        register_function(
            tool,
            caller=coder,
            executor=user_proxy,
            name=tool.__name__,
            description=tool.__doc__
        )

    # 4. 为 Tester 注册 Shell 工具
    for tool in get_shell_tools():
        register_function(
            tool,
            caller=tester,
            executor=user_proxy,
            name=tool.__name__,
            description=tool.__doc__
        )

    # 设置实现子聊天组
    implementation_manager = setup_implementation_group_chat(coder, reviewer, tester,user_proxy, manager_config)
    
    def prepare_task_message(recipient, messages, sender, config):
        full_content = messages[-1].get("content", "")
        # 如果你想把 "TODO:" 之前的内容（通常是思考过程）过滤掉
        if "TODO:" in full_content:
            return full_content.split("TODO:", 1)[-1].strip()
        return full_content
    def task_trigger_condition(sender):
        # 1. 获取发送者（Architect）最后收发的消息
        # 在 GroupChatManager 转发时，last_message(recipient) 是最准确的
        try:
            # 尝试获取最后一条消息的内容
            last_msg_content = sender.last_message().get("content", "")
            return "TODO" in last_msg_content
        except Exception:
            # 如果存在多个对话导致异常，备选方案：从消息历史列表判断
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

    return architect

def start_multi_agent_session(manager, user_proxy, user_input: str):
    """启动协作会话。"""
    user_proxy.initiate_chat(manager, message=user_input)
