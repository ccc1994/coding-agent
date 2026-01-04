import os
import sys
import re
import time
import fcntl
import select
import logging
import threading
import pexpect
import signal
from typing import Dict, Optional, Union, List
from rich.console import Console
from rich.prompt import Confirm

# Configure logging
logger = logging.getLogger(__name__)
console = Console()

class JobManager:
    """Manages background processes."""
    def __init__(self):
        self.jobs: Dict[int, pexpect.spawn] = {}
        self.outputs: Dict[int, str] = {}

    def register(self, process: pexpect.spawn, initial_output: str = ""):
        self.jobs[process.pid] = process
        self.outputs[process.pid] = initial_output

    def get_job(self, pid: int) -> Optional[pexpect.spawn]:
        return self.jobs.get(pid)

    def kill_job(self, pid: int) -> str:
        if pid not in self.jobs:
            return f"Error: No job found with PID {pid}."
        
        process = self.jobs[pid]
        try:
            if process.isalive():
                process.close(force=True)
            
            del self.jobs[pid]
            if pid in self.outputs:
                del self.outputs[pid]
            return f"Process {pid} killed."
        except Exception as e:
            return f"Error killing process {pid}: {str(e)}"

    def send_input(self, pid: int, text: str) -> str:
        if pid not in self.jobs:
            return f"Error: No job found with PID {pid}."
        
        process = self.jobs[pid]
        if not process.isalive():
            output = self.outputs.pop(pid, "")
            if pid in self.jobs:
                del self.jobs[pid]
            return f"Error: Process {pid} is no longer running.\nFinal Output:\n{output}"
            
        try:
            if not text.endswith('\n'):
                text += '\n'
            process.send(text)
            
            # Monitor for result after sending input
            executor = ShellExecutor(self)
            return executor._monitor_loop(process, timeout=10, is_continuation=True)
        except Exception as e:
            return f"Error sending input to {pid}: {str(e)}"

    def read_output(self, pid: int) -> str:
        if pid not in self.jobs:
            return f"Error: No job found with PID {pid}."
            
        process = self.jobs[pid]
        try:
            text = process.read_nonblocking(size=4096, timeout=0.1)
            self.outputs[pid] += text
            return text
        except (pexpect.TIMEOUT, pexpect.EOF):
            return "" 
        except Exception as e:
            return f"[Error reading log: {e}]"

# Global job manager instance
_job_manager = JobManager()

class ShellExecutor:
    def __init__(self, job_manager: JobManager):
        self.job_manager = job_manager

    def is_interactive_prompt(self, text: str) -> bool:
        """Heuristic to detect if the output ends with an interactive prompt."""
        text = text.strip()
        if not text:
            return False
        
        # Common prompt endings
        if text.endswith("?") or text.endswith(":") or text.endswith(">") or text.endswith("]"):
            return True
            
        # Common prompt keywords
        lower_text = text.lower()
        keywords = ["password", "confirmation", "[y/n]", "enter choice"]
        if any(kw in lower_text for kw in keywords):
            return True
            
        # TUI / UI indicators
        if any(c in text for c in ['❯', '◯', '●', '│', '└']):
             return True
            
        return False

    def _monitor_loop(self, process: pexpect.spawn, timeout: int, is_continuation: bool = False) -> str:
        """
        Internal monitoring loop used by both execute and send_input.
        """
        output_buffer = ""
        start_time = time.time()
        last_output_time = time.time()
        pid = process.pid

        while True:
            # 1. Check if process has finished
            if not process.isalive():
                try:
                    rest = process.read()
                    output_buffer += rest
                    sys.stdout.write(rest)
                    sys.stdout.flush()
                except:
                    pass
                
                result = f"Execution Finished. Exit Code: {process.exitstatus}\nOutput:\n{output_buffer}"
                if pid in self.job_manager.jobs:
                    del self.job_manager.jobs[pid]
                    if pid in self.job_manager.outputs:
                        del self.job_manager.outputs[pid]
                return result

            # 2. Try to read chunk
            try:
                chunk = process.read_nonblocking(size=1024, timeout=0.5)
                output_buffer += chunk
                last_output_time = time.time()
                
                sys.stdout.write(chunk)
                sys.stdout.flush()
                
                if pid in self.job_manager.outputs:
                    self.job_manager.outputs[pid] += chunk

                # 3. Check for Interactive Prompt
                lines = output_buffer.splitlines()
                while lines and not lines[-1].strip():
                    lines.pop()
                if lines:
                    recent_text = "\n".join(lines[-5:])
                    if self.is_interactive_prompt(recent_text):
                        if not is_continuation:
                            try:
                                # Start interaction without printing extra messages
                                process.interact()
                            except:
                                pass
                            
                            if not process.isalive():
                                return f"Interactive execution finished.\nOutput:\n{output_buffer}"
                            else:
                                self.job_manager.register(process, output_buffer)
                                return f"User detached. Process running in background (PID {process.pid})."
                        else:
                            # Programmatic input: return the prompt back to Agent
                            self.job_manager.register(process, output_buffer)
                            return (
                                f"PAUSED: Another Interactive Prompt Detected.\n"
                                f"PID: {process.pid}\n"
                                f"New Output:\n{output_buffer}\n"
                                f"ACTION REQUIRED: Use `send_shell_input` again or `kill_process`."
                            )
                            
            except pexpect.TIMEOUT:
                if time.time() - last_output_time > 5:
                    self.job_manager.register(process, output_buffer)
                    return (
                        f"BACKGROUND: Process is silent but still running (Silence Timeout).\n"
                        f"PID: {process.pid}\n"
                        f"Output so far:\n{output_buffer}\n"
                        f"NOTE: Process is continuing in background."
                    )
            except pexpect.EOF:
                continue

            if time.time() - start_time > timeout:
                self.job_manager.register(process, output_buffer)
                return (
                    f"BACKGROUND: Command timed out ({timeout}s) but still running.\n"
                    f"PID: {process.pid}\n"
                    f"Output so far:\n{output_buffer}"
                )

    def execute(self, command: str, timeout: int = 10, cwd: str = ".") -> str:
        """
        Execute command using pexpect for PTY support.
        """
        danger_patterns = [
            r"rm\s+-rf\s+/", r"curl.*\|\s*sh", r"wget.*\|\s*sh", 
            r"chmod\s+.*777", r"\.git/"
        ]
        for pattern in danger_patterns:
            if re.search(pattern, command):
                return f"Error: Command '{command}' is blocked for security reasons (Safety Policy)."

        confirm_patterns = [
            r"\brm\b", r"\bmv\b", r"\bsudo\b", r"\bdd\b", r"\bkill\b", 
            r"\bchmod\b", r"\bchown\b", r"\breboot\b", r"\bshutdown\b", 
            r"\binit\b", r"\bmkfs\b", r"\bformat\b"
        ]
        if any(re.search(pattern, command) for pattern in confirm_patterns):
            console.print(f"\n[bold red]安全警示：[/bold red] Agent 想要执行危险命令：[cyan]{command}[/cyan]")
            if not Confirm.ask("[bold yellow]确定执行此命令吗？[/bold yellow]"):
                return "用户取消了命令执行。"

        console.print(f"[dim]执行命令 (PTY) ：{command}[/dim]")

        try:
            process = pexpect.spawn(
                command,
                cwd=cwd,
                encoding='utf-8',
                timeout=timeout,
                dimensions=(24, 80)
            )
            return self._monitor_loop(process, timeout)
        except Exception as e:
            return f"Error executing command: {str(e)}"

# --- Tool Wrappers ---

def execute_shell_command(command: str, timeout: int = 10, cwd: str = ".") -> str:
    executor = ShellExecutor(_job_manager)
    return executor.execute(command, timeout, cwd)

def send_shell_input(pid: int, text: str) -> str:
    return _job_manager.send_input(pid, text)

def kill_process(pid: int) -> str:
    return _job_manager.kill_job(pid)

def list_background_jobs() -> str:
    if not _job_manager.jobs:
        return "No background jobs running."
    
    status = []
    for pid, proc in _job_manager.jobs.items():
        state = "Running" if proc.isalive() else "Finished"
        status.append(f"PID: {pid} | Status: {state} | Command: {proc.args}")
    return "\n".join(status)

def get_shell_tools():
    return [execute_shell_command, send_shell_input, kill_process, list_background_jobs]
