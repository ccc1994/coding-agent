import subprocess
import re
import os
import sys
import logging
from rich.console import Console
from rich.prompt import Confirm

logger = logging.getLogger("CodingAgent")
console = Console()

def analyze_command_with_llm(command: str) -> dict:
    # 基础启发式规则
    is_blocking_heuristic = any(kw in command.lower() for kw in ["start", "serve", "dev", "watch", "tail -f"])
    is_interactive_heuristic = any(kw in command.lower() for kw in ["npx", "npm init", "npm create", "yarn create", "pnpm create", "create-", "git clone"])

    try:
        from openai import OpenAI
        
        api_key = os.getenv("DASHSCOPE_API_KEY")
        base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        
        if not api_key:
            return {"is_blocking": is_blocking_heuristic, "is_interactive": is_interactive_heuristic, "reason": "未配置 API，使用启发式规则"}
        
        client = OpenAI(api_key=api_key, base_url=base_url)
        
        prompt = f"""分析以下 shell 命令的特征，返回 JSON 格式：

命令：{command}

请判断：
1. is_blocking: 该命令是否会长期运行不退出（如开发服务器、监听进程、日志跟踪）？
2. is_interactive: 该命令是否需要用户交互输入？
   注意：
   - 'npm create', 'npm init', 'npx', 'yarn create' 等命令在创建项目或首次安装包时通常需要用户确认（y/n）或输入项目信息，应视为 is_interactive: true。
   - 即使命令带有参数，也可能因为包未安装而触发 npx 的安装确认提示。
3. reason: 简短说明原因

只返回 JSON，格式：{{"is_blocking": true/false, "is_interactive": true/false, "reason": "原因"}}"""

        # 从环境变量获取 coder 模型配置
        model_id = os.getenv("CODER_MODEL_ID")
        
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        
        result_text = response.choices[0].message.content.strip()
        import json
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()
        
        result = json.loads(result_text)
        
        # 将 LLM 结果与启发式规则结合 (取并集)
        result["is_blocking"] = result.get("is_blocking", False) or is_blocking_heuristic
        result["is_interactive"] = result.get("is_interactive", False) or is_interactive_heuristic
        
        return result
    except Exception as e:
        logger.error(f"LLM 分析失败: {e}，使用默认规则")
        return {"is_blocking": is_blocking_heuristic, "is_interactive": is_interactive_heuristic, "reason": "降级到启发式规则"}


def truncate_output(text: str, max_length: int = 5000) -> str:
    if len(text) <= max_length:
        return text
    return f"...(前略 {len(text) - max_length} 字符)...\n" + text[-max_length:]


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
        logger.info(f"执行命令：{command}")

    try:
        # 使用 LLM 分析命令特征
        analysis = analyze_command_with_llm(command)
        is_blocking = analysis.get("is_blocking", False)
        is_interactive = analysis.get("is_interactive", False)
        reason = analysis.get("reason", "")
        
        logger.info(f"命令分析: {reason}")
        
        if is_interactive:
            # 交互式命令：先在前台运行完成交互
            console.print(f"[bold yellow]检测到交互式命令，将在前台执行完成交互[/bold yellow]")
            console.print(f"[dim]执行: {command}[/dim]\n")
            
            import sys
            import time
            
            # 对于交互式命令，我们需要特殊处理
            # 1. 先在前台运行，允许用户交互
            # 2. 如果交互后命令仍然阻塞运行，询问用户是否放入后台
            
            try:
                # 运行命令并设置超时，用于检测是否会长期阻塞
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=cwd,
                    stdin=sys.stdin,   # 允许用户输入
                    stdout=sys.stdout, # 直接输出到终端
                    stderr=sys.stderr, # 错误也直接输出
                    timeout=30 if is_blocking else None  # 如果是阻塞命令，设置30秒超时
                )
                
                if result.returncode == 0:
                    return "命令执行成功。"
                elif result.returncode in [-2, 130]: # SIGINT
                    return "命令被用户中断。如果该命令启动了长驻服务，这通常意味着服务已成功启动并随后被手动停止, 请先检查命令是否已正确执行。"
                else:
                    return f"命令执行失败，退出码：{result.returncode}"
            except subprocess.TimeoutExpired:
                # 命令在交互后仍然阻塞运行
                console.print(f"\n[bold yellow]检测到命令在交互后仍然阻塞运行[/bold yellow]")
                if Confirm.ask("是否将命令放到后台继续运行？"):
                    # 在后台重新启动命令
                    console.print(f"[dim]将命令放到后台继续运行: {command}[/dim]")
                    import os
                    import fcntl
                    
                    process = subprocess.Popen(
                        command,
                        shell=True,
                        cwd=cwd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        stdin=subprocess.DEVNULL,  # 后台命令不需要标准输入
                        bufsize=1,
                        universal_newlines=True
                    )
                    
                    # 设置非阻塞读取
                    for stream in [process.stdout, process.stderr]:
                        fd = stream.fileno()
                        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
                        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                    
                    # 持续收集初始输出，最多等待 5 秒
                    initial_output = []
                    start_time = time.time()
                    while time.time() - start_time < 5:
                        if process.poll() is not None:
                            break
                        for stream in [process.stdout, process.stderr]:
                            try:
                                content = stream.read()
                                if content:
                                    initial_output.append(content)
                            except (IOError, TypeError):
                                pass
                        time.sleep(0.2)
                    
                    if process.poll() is None:
                        console.print(f"[green]✓[/green] 命令已在后台运行（PID: {process.pid}）")
                        initial_output_str = ''.join(initial_output) if initial_output else "暂无初始输出"
                        return truncate_output(f"命令已移至后台继续运行（PID: {process.pid}）\n初始输出：\n{initial_output_str}\n注意：您可以使用 'kill {process.pid}' 停止它。")
                    else:
                        stdout, stderr = process.communicate()
                        return truncate_output(f"命令在后台运行结束（退出码: {process.returncode}）\n输出：\n{''.join(initial_output) + stdout}\n错误：\n{stderr}")
                else:
                    return "用户取消了命令的后台运行。"
        elif is_blocking:
            # 非交互式但阻塞的命令：直接后台启动
            console.print(f"[bold yellow]检测到阻塞命令，将在后台启动[/bold yellow]")
            console.print(f"[dim]执行: {command}[/dim]\n")
            
            import time
            import os
            import fcntl
            
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # 设置非阻塞读取
            for stream in [process.stdout, process.stderr]:
                fd = stream.fileno()
                flags = fcntl.fcntl(fd, fcntl.F_GETFL)
                fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            
            # 持续收集初始输出，最多等待 5 秒
            output_lines = []
            start_time = time.time()
            while time.time() - start_time < 5:
                if process.poll() is not None:
                    break
                for stream in [process.stdout, process.stderr]:
                    try:
                        content = stream.read()
                        if content:
                            console.print(content, end='')
                            output_lines.append(content)
                    except (IOError, TypeError):
                        pass
                time.sleep(0.2)
            
            if process.poll() is None:
                console.print(f"\n[green]✓[/green] 命令已在后台启动（PID: {process.pid}）")
                result = ''.join(output_lines) if output_lines else "暂无初始输出"
                return truncate_output(f"命令已在后台启动（PID: {process.pid}）\n初始输出：\n{result}\n\n注意：命令将继续运行，您可以使用 'kill {process.pid}' 停止它。")
            else:
                stdout, stderr = process.communicate()
                full_out = "".join(output_lines) + stdout
                console.print(full_out)
                if stderr:
                    console.print(f"[red]{stderr}[/red]")
                return truncate_output(f"命令启动后立即退出（退出码: {process.returncode}）\n输出：\n{full_out}\n错误：\n{stderr}")
        else:
            # 非交互式非阻塞命令：正常前台运行
            logger.info(f"执行命令：{command}")
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
                    
                    if returncode in [-2, 130]:
                        return "命令执行被用户中断 (SIGINT)。"
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
            
            return truncate_output(result_text) or "命令执行成功（无输出）。"
        
    except Exception as e:
        return f"执行命令时出错：{str(e)}"

def get_shell_tools():
    """返回用于 Shell 操作的工具列表。"""
    return [execute_shell]
