import subprocess
import re
import os
from rich.console import Console
from rich.prompt import Confirm

console = Console()

def analyze_command_with_llm(command: str) -> dict:
    """使用 LLM 分析命令是否会阻塞、是否需要交互"""
    try:
        from openai import OpenAI
        
        api_key = os.getenv("DASHSCOPE_API_KEY")
        base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        
        if not api_key:
            # 如果没有配置，使用默认规则
            return {"is_blocking": False, "is_interactive": False, "reason": "未配置 API"}
        
        client = OpenAI(api_key=api_key, base_url=base_url)
        
        prompt = f"""分析以下 shell 命令的特征，返回 JSON 格式：

命令：{command}

请判断：
1. is_blocking: 该命令是否会长期运行不退出（如开发服务器、监听进程）？
2. is_interactive: 该命令是否需要用户交互输入（如 npx 首次安装、npm init）？
3. reason: 简短说明原因

只返回 JSON，格式：{{"is_blocking": true/false, "is_interactive": true/false, "reason": "原因"}}"""

        response = client.chat.completions.create(
            model="qwen-flash-2025-07-28",  # 使用快速模型
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        
        result_text = response.choices[0].message.content.strip()
        # 提取 JSON
        import json
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()
        
        result = json.loads(result_text)
        return result
    except Exception as e:
        console.print(f"[dim]LLM 分析失败: {e}，使用默认规则[/dim]")
        # 降级到简单规则
        is_blocking = any(kw in command.lower() for kw in ["start", "serve", "dev", "watch"])
        is_interactive = any(kw in command.lower() for kw in ["npx", "npm init", "create-"])
        return {"is_blocking": is_blocking, "is_interactive": is_interactive, "reason": "降级规则"}


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
        # 使用 LLM 分析命令特征
        analysis = analyze_command_with_llm(command)
        is_blocking = analysis.get("is_blocking", False)
        is_interactive = analysis.get("is_interactive", False)
        reason = analysis.get("reason", "")
        
        console.print(f"[dim]命令分析: {reason}[/dim]")
        
        if is_blocking:
            # 服务器命令：后台启动，等待几秒检查是否成功
            console.print(f"[bold yellow]检测到服务器命令，将在后台启动并验证[/bold yellow]")
            console.print(f"[dim]执行: {command}[/dim]\n")
            
            import time
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # 等待几秒，收集初始输出
            time.sleep(5)
            
            # 检查进程是否还在运行
            if process.poll() is None:
                # 进程仍在运行，说明服务器启动成功
                output_lines = []
                try:
                    # 非阻塞读取已有输出
                    import select
                    if sys.platform != 'win32':
                        readable, _, _ = select.select([process.stdout, process.stderr], [], [], 0)
                        for stream in readable:
                            while True:
                                line = stream.readline()
                                if not line:
                                    break
                                console.print(line, end='')
                                output_lines.append(line)
                except:
                    pass
                
                console.print(f"\n[green]✓[/green] 服务器已在后台启动（PID: {process.pid}）")
                console.print(f"[dim]提示：服务器将继续运行，您可以手动访问测试[/dim]\n")
                
                result = ''.join(output_lines) if output_lines else "服务器启动成功"
                return f"服务器已启动（PID: {process.pid}）\n{result}\n\n注意：服务器在后台运行，测试完成后请手动停止。"
            else:
                # 进程已退出，可能启动失败
                stdout, stderr = process.communicate()
                console.print(stdout)
                if stderr:
                    console.print(f"[red]{stderr}[/red]")
                return f"服务器启动失败（退出码: {process.returncode}）\n{stdout}\n{stderr}"
        
        elif is_interactive:
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
