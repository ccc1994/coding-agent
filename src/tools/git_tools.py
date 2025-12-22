import subprocess
from rich.console import Console

console = Console()

def git_status() -> str:
    """
    获取 git 仓库状态。
    
    使用场景：
    - 检查哪些文件被修改
    - 查看暂存区状态
    - 确认当前分支
    
    Returns:
        git status 的输出结果
    
    示例：
        >>> git_status()
        "On branch main\\nChanges not staged..."
    """
    try:
        result = subprocess.run(
            ["git", "status"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return f"错误：{result.stderr}"
        return result.stdout
    except Exception as e:
        return f"执行 git status 失败：{str(e)}"

def git_diff(file_path: str = "") -> str:
    """
    查看文件差异。
    
    使用场景：
    - 查看修改了什么内容
    - 对比工作区和暂存区
    
    Args:
        file_path: 可选，指定文件路径。为空则显示所有差异
    
    Returns:
        git diff 的输出结果
    
    示例：
        >>> git_diff("src/main.py")
        "diff --git a/src/main.py..."
    """
    try:
        cmd = ["git", "diff"]
        if file_path:
            cmd.append(file_path)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return f"错误：{result.stderr}"
        return result.stdout if result.stdout else "无差异"
    except Exception as e:
        return f"执行 git diff 失败：{str(e)}"

def git_add(file_path: str) -> str:
    """
    添加文件到暂存区。
    
    使用场景：
    - 准备提交修改
    - 暂存新文件
    
    Args:
        file_path: 文件路径（支持通配符，如 "." 表示所有文件）
    
    Returns:
        操作结果
    
    示例：
        >>> git_add("src/main.py")
        "已添加 'src/main.py' 到暂存区"
    """
    try:
        result = subprocess.run(
            ["git", "add", file_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return f"错误：{result.stderr}"
        return f"已添加 '{file_path}' 到暂存区。"
    except Exception as e:
        return f"执行 git add 失败：{str(e)}"

def git_commit(message: str) -> str:
    """
    提交暂存区的更改。
    
    使用场景：
    - 保存代码快照
    - 创建版本历史
    
    Args:
        message: 提交信息
    
    Returns:
        提交结果
    
    示例：
        >>> git_commit("Fix bug in login")
        "已提交：Fix bug in login"
    """
    try:
        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return f"错误：{result.stderr}"
        return f"已提交：{message}\\n{result.stdout}"
    except Exception as e:
        return f"执行 git commit 失败：{str(e)}"

def get_git_tools():
    """返回用于 Git 操作的工具列表。"""
    return [git_status, git_diff, git_add, git_commit]
