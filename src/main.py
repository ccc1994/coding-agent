import os

# 抑制 transformers 库在未发现深度学习框架时的警告
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

import sys
from src.tools.file_tools import get_file_tree

# 确保项目根目录在 sys.path 中，以解决 'src' 导入问题
import sys
import pyfiglet
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box
from rich.padding import Padding
from prompt_toolkit import prompt
from prompt_toolkit.key_binding import KeyBindings

from src.agent.manager import ensure_project_setup, load_project_memory
from src.agent.agents import create_agents
from src.agent.orchestrator import setup_orchestration, start_multi_agent_session
from src.tools.index_tools import build_index_async, update_index, start_index_watcher

from openinference.instrumentation.autogen import AutogenInstrumentor
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from openinference.instrumentation.openai import OpenAIInstrumentor
from src.cli.banner import print_banner
from src.patch_autogen import patch_autogen_instrumentation
from src.tools.mcp_manager import MCPManager
import config
import asyncio

console = Console()

async def main():
    # 1. 初始化
    load_dotenv()
    
    # 检查 Phoenix 是否可用
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        # 尝试连接 Phoenix 端口
        is_phoenix_up = sock.connect_ex(('127.0.0.1', 6006)) == 0
        sock.close()
        
        if is_phoenix_up:
            resource = Resource.create({
                "service.name": "CodingAgent",  # 这个就是 Phoenix 中显示的 Project Name
                "environment": "development"
            })
            endpoint = "http://127.0.0.1:6006/v1/traces"
            tracer_provider = TracerProvider(resource=resource)
            tracer_provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
            )
            trace.set_tracer_provider(tracer_provider)
            OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
            patch_autogen_instrumentation() # Apply the patch
            AutogenInstrumentor().instrument()
        else:
            console.print("[bold red]错误：未检测到 Phoenix (127.0.0.1:6006)，跳过 OpenInference 初始化。[/bold red]")
    except Exception as e:
        console.print(f"[bold red]检查 Phoenix 时发生错误: {e}，跳过 OpenInference 初始化。[/bold red]")
    
    project_root =os.getcwd()
    config.project_root = project_root
    # todo 没必要?
    ensure_project_setup(project_root)
    
    # 初始化 MCP (Model Context Protocol)
    mcp_manager = MCPManager(project_root)
    await mcp_manager.initialize()
    
    # 构建或更新代码索引
    build_index_async(project_root)
    
    # 启动实时文件监听器
    start_index_watcher(project_root)

    # 2. 配置检查
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    
    if not api_key:
        console.print("[bold red]错误：[/bold red] .env 中未找到 DASHSCOPE_API_KEY。")
        sys.exit(1)

    # 3. Agent 与编排设置
    try:
        architect, coder, reviewer, tester, user_proxy, manager_config = create_agents(api_key, base_url, mcp_manager)
        manager = setup_orchestration(architect, coder, reviewer, tester, user_proxy, manager_config)
    except Exception as e:
        console.print(f"[bold red]系统初始化出错：[/bold red] {e}")
        sys.exit(1)
    

    print_banner()

    # 5. 交互循环
    first_time = True
    while True:
        try:
            user_input = get_advanced_input()
            
            if user_input.lower() in ["exit", "quit"]:
                console.print("[yellow]正在关闭...[/yellow]")
                break
            
            if not user_input.strip():
                continue

            full_prompt = user_input
            if first_time:
                # 第一次带上项目结构
                l1_context = get_file_tree(project_root)
                # 加载项目长期记忆
                project_memory = load_project_memory(project_root)
                
                full_prompt = f"[Project Structure]:\n{l1_context}\n{project_memory}\n[需求]\n{user_input}"
                first_time = False

            # 启动会话
            console.print(f"\n[bold blue]正在启动...[/bold blue]\n")
            start_multi_agent_session(manager, user_proxy, full_prompt)

        except KeyboardInterrupt:
            console.print("\n[yellow]正在关闭...[/yellow]")
            break
        except Exception as e:
            console.print(f"[bold red]发生意外错误：[/bold red] {e}")

def get_advanced_input():
    kb = KeyBindings()

    # 绑定 Alt+Enter 为换行符 (在终端中通常映射为 Esc+Enter)
    @kb.add('escape', 'enter')
    def _(event):
        event.current_buffer.insert_text('\n')

    # 绑定普通的 Enter 为提交
    @kb.add('enter')
    def _(event):
        # 如果当前内容为空，或者你定义了某些条件，可以不提交
        event.current_buffer.validate_and_handle()

    return prompt("> ", key_bindings=kb, multiline=True)



if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]正在关闭...[/yellow]")
        # 停止索引监听器
        from src.tools.index_tools import stop_index_watcher
        stop_index_watcher()
        sys.exit(0)
