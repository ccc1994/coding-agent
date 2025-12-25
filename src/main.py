import os
import sys

# 确保项目根目录在 sys.path 中，以解决 'src' 导入问题
import sys
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
import logging

try:
    import readline
except ImportError:
    pass

from src.agent.manager import ensure_project_setup
from src.agent.agents import create_agents
from src.agent.orchestrator import setup_orchestration, start_multi_agent_session
from src.agent.context import get_level1_context

console = Console()

def main():
    # 1. 初始化
    load_dotenv()
    project_root =os.getcwd()
    # todo 没必要?
    ensure_project_setup(project_root)

    # 2. 配置检查
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    
    if not api_key:
        console.print("[bold red]错误：[/bold red] .env 中未找到 DASHSCOPE_API_KEY。")
        sys.exit(1)

    # 3. Agent 与编排设置
    with console.status("[bold green]正在初始化多 Agent 系统...[/bold green]"):
        try:
            architect, coder, reviewer, tester, user_proxy, manager_config = create_agents(api_key, base_url)
            manager = setup_orchestration(architect, coder, reviewer, tester, user_proxy, manager_config)
        except Exception as e:
            console.print(f"[bold red]系统初始化出错：[/bold red] {e}")
            sys.exit(1)

    # 4. 欢迎词
    console.print(Panel.fit(
        "[bold cyan]AI 编码助手 (高级多 Agent 系统)[/bold cyan]\n"
        "[dim]由 AutoGen 编排 | 由 DashScope 提供动力[/dim]",
        border_style="bright_blue"
    ))
    console.print("[yellow]输入 'exit' 退出。输入 '/settings' 查看设置。规范驱动开发已激活。[/yellow]\n")

    # 设置状态
    settings = {"verbose_llm": False}
    
    def toggle_verbose_logging():
        settings["verbose_llm"] = not settings["verbose_llm"]
        if settings["verbose_llm"]:
            logging.basicConfig(level=logging.INFO, force=True)
            os.environ["AUTOGEN_VERBOSE"] = "1"
            console.print("[green]✓[/green] 已启用 LLM 输入日志（详细模式）")
        else:
            logging.basicConfig(level=logging.WARNING, force=True)
            os.environ["AUTOGEN_VERBOSE"] = "0"
            console.print("[yellow]✓[/yellow] 已禁用 LLM 输入日志（简洁模式）")
    
    def show_settings():
        console.print("\n[bold cyan]⚙️  设置[/bold cyan]")
        console.print(f"1. LLM 输入日志: [{'green' if settings['verbose_llm'] else 'red'}]{'开启' if settings['verbose_llm'] else '关闭'}[/]")
        console.print("\n[dim]输入数字切换设置，或按回车返回[/dim]")
        choice = console.input("[bold cyan]>[/bold cyan] ").strip()
        if choice == "1":
            toggle_verbose_logging()
            show_settings()

    # 5. 交互循环
    while True:
        try:
            user_input = console.input("[bold green]>[/bold green] ")
            
            if user_input.lower() in ["exit", "quit"]:
                console.print("[yellow]正在关闭... 再见！[/yellow]")
                break
            
            if not user_input.strip():
                continue

            # 自动注入第一级上下文 (Level 1 Context)
            l1_context = get_level1_context(project_root)
            full_prompt = f"{l1_context}\n[用户需求]\n{user_input}"

            # 启动会话
            console.print(f"\n[bold blue]正在启动群聊...[/bold blue]\n")
            start_multi_agent_session(manager, user_proxy, full_prompt)

        except KeyboardInterrupt:
            console.print("\n[yellow]正在关闭...[/yellow]")
            break
        except Exception as e:
            console.print(f"[bold red]发生意外错误：[/bold red] {e}")

if __name__ == "__main__":
    main()
