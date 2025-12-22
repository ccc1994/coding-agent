import subprocess
import re
from rich.console import Console
from rich.prompt import Confirm

console = Console()

def execute_shell(command: str) -> str:
    """带有安全检查和用户确认的 Shell 命令执行。"""
    # 安全策略：硬阻断危险命令
    danger_patterns = [
        r"rm\s+-rf\s+/",
        r"curl.*\|\s*sh",
        r"wget.*\|\s*sh",
        r"chmod\s+.*777",
        r"\.git/"
    ]
    
    for pattern in danger_patterns:
        if re.search(pattern, command):
            return f"Error: Command '{command}' is blocked for security reasons (Safety Policy)."

    console.print(f"\n[bold red]安全警示：[/bold red] Agent 想要执行：[cyan]{command}[/cyan]")
    if not Confirm.ask("[bold yellow]确定执行此命令吗？[/bold yellow]"):
        return "用户取消了命令执行。"

    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=60
        )
        output = result.stdout or ""
        if result.stderr:
            output += f"\nErrors:\n{result.stderr}"
        return output or "命令执行成功（无输出）。"
    except subprocess.TimeoutExpired:
        return "错误：命令在 60 秒后超时。"
    except Exception as e:
        return f"执行命令时出错：{str(e)}"

def get_shell_tools():
    """返回用于 Shell 操作的工具列表。"""
    return [execute_shell]
