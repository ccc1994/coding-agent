import subprocess
import re
from rich.console import Console
from rich.prompt import Confirm

console = Console()

def execute_shell(command: str, timeout: int = None, cwd: str = ".") -> str:
    """
    执行 shell 命令（支持实时输出和工作目录）。
    
    使用场景：
    - 运行构建命令（npm install, pip install）
    - 执行测试（pytest, npm test）
    - 运行脚本和工具
    
    Args:
        command: 要执行的命令
        timeout: 超时时间（秒），默认 None（无限制，用户可手动中断）
        cwd: 工作目录，默认为当前目录
    
    Returns:
        命令输出（包含 stdout 和 stderr）
    
    示例：
        >>> execute_shell("npm install", cwd="frontend")
        "added 234 packages..."
    """
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

    # 定义需要确认的危险命令模式
    confirm_patterns = [
        r"\brm\b", r"\bmv\b", r"\bsudo\b", r"\bdd\b",
        r"\bkill\b", r"\bchmod\b", r"\bchown\b", 
        r"\breboot\b", r"\bshutdown\b", r"\binit\b",
        r"\bmkfs\b", r"\bformat\b"
    ]
    
    # 检查是否为危险命令
    is_dangerous = any(re.search(pattern, command) for pattern in confirm_patterns)
    
    if is_dangerous:
        console.print(f"\n[bold red]安全警示：[/bold red] Agent 想要执行危险命令：[cyan]{command}[/cyan]")
        if not Confirm.ask("[bold yellow]确定执行此命令吗？[/bold yellow]"):
            return "用户取消了命令执行。"
    else:
        # 安全命令直接执行，仅显示提示
        console.print(f"[dim]执行命令：{command}[/dim]")

    try:
        # 检测是否为交互式命令（npx, npm init等）
        interactive_patterns = [r"\bnpx\b", r"\bnpm\s+init\b", r"\bcreate-react-app\b", r"\bcreate-vite\b"]
        is_interactive = any(re.search(pattern, command) for pattern in interactive_patterns)
        
        if is_interactive:
            # 交互式命令：直接使用系统调用，允许用户输入
            console.print(f"[bold yellow]交互式命令检测到，将直接在终端执行[/bold yellow]")
            console.print(f"[dim]执行: {command}[/dim]\n")
            
            import sys
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                stdin=sys.stdin,   # 允许用户输入
                stdout=sys.stdout, # 直接输出到终端
                stderr=sys.stderr  # 错误也直接输出
            )
            
            if result.returncode == 0:
                return "命令执行成功。"
            else:
                return f"命令执行失败，退出码：{result.returncode}"
        
        else:
            # 非交互式命令：使用 Popen 实现实时输出
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=cwd,
                bufsize=1,
                universal_newlines=True
            )
            
            output_lines = []
            error_lines = []
            
            # 实时读取并显示输出
            import select
            import sys
            
            # 设置非阻塞读取（仅Unix系统）
            if sys.platform != 'win32':
                import fcntl
                import os as os_module
                
                for stream in [process.stdout, process.stderr]:
                    fd = stream.fileno()
                    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
                    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os_module.O_NONBLOCK)
            
            # 读取输出直到进程结束
            while True:
                try:
                    returncode = process.wait(timeout=0.1)
                    # 进程已结束，读取剩余输出
                    remaining_out = process.stdout.read()
                    remaining_err = process.stderr.read()
                    if remaining_out:
                        console.print(remaining_out, end='')
                        output_lines.append(remaining_out)
                    if remaining_err:
                        console.print(f"[red]{remaining_err}[/red]", end='')
                        error_lines.append(remaining_err)
                    break
                except subprocess.TimeoutExpired:
                    # 进程仍在运行，读取可用输出
                    if sys.platform != 'win32':
                        readable, _, _ = select.select([process.stdout, process.stderr], [], [], 0)
                        for stream in readable:
                            line = stream.readline()
                            if line:
                                if stream == process.stdout:
                                    console.print(line, end='')
                                    output_lines.append(line)
                                else:
                                    console.print(f"[red]{line}[/red]", end='')
                                    error_lines.append(line)
                    else:
                        # Windows系统简化处理
                        line = process.stdout.readline()
                        if line:
                            console.print(line, end='')
                            output_lines.append(line)
            
            # 组合输出
            full_output = ''.join(output_lines)
            full_errors = ''.join(error_lines)
            
            result_text = full_output
            if full_errors:
                result_text += f"\nErrors:\n{full_errors}"
            
            return result_text or "命令执行成功（无输出）。"
        
    except Exception as e:
        return f"执行命令时出错：{str(e)}"

def get_shell_tools():
    """返回用于 Shell 操作的工具列表。"""
    return [execute_shell]
