from autogen import GroupChat, GroupChatManager, register_function
from src.tools.file_tools import get_file_tools
from src.tools.shell_tools import get_shell_tools
from src.tools.git_tools import get_git_tools

def setup_orchestration(architect, coder, reviewer, tester, user_proxy, manager_config):
    """注册工具并设置带有规范驱动流程的 GroupChat。"""
    
    # 1. 为 Coder 注册文件工具
    for tool in get_file_tools():
        register_function(
            tool,
            caller=coder,
            executor=coder,
            name=tool.__name__,
            description=tool.__doc__
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

    # 3. 为 Coder 注册 Git 工具（版本控制）
    for tool in get_git_tools():
        register_function(
            tool,
            caller=coder,
            executor=coder,
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

    # 3. 定义 FSM 状态机图 (Finite State Machine)
    # 硬编码跳转规则，无需 LLM 决策，实现零成本、零延迟的 Speaker 选择
    graph_dict = {
        user_proxy: [architect],           # 用户输入 -> 架构师规划
        architect: [coder, user_proxy],                # 架构师 -> 程序员实现
        coder: [reviewer],                 # 程序员 -> 审核员检查
        reviewer: [coder, tester, architect],         # 审核员 -> 不通过回程序员，通过去测试员
        tester: [coder, user_proxy],       # 测试员 -> 失败回程序员，成功结束
    }

    groupchat = GroupChat(
        agents=[user_proxy, architect, coder, reviewer, tester],
        messages=[],
        max_round=50,
        speaker_selection_method="auto",   # 使用 auto 模式配合 FSM 图
        allowed_or_disallowed_speaker_transitions=graph_dict,
        speaker_transitions_type="allowed"  # 指定 graph_dict 定义的是允许的转换
    )

    manager = GroupChatManager(
        groupchat=groupchat,
        llm_config=manager_config  # 使用轻量级 Flash 模型，降低成本和延迟
    )

    return manager

def start_multi_agent_session(manager, user_proxy, user_input: str):
    """启动协作会话。"""
    user_proxy.initiate_chat(manager, message=user_input)
