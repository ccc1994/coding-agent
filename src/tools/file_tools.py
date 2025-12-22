import os
import re
from rich.prompt import Confirm
from rich.console import Console

console = Console()

def read_file(path: str) -> str:
    """读取文件内容。（第二级上下文）"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write_file(path: str, content: str) -> str:
    """将内容写入文件。"""

    # 安全策略：写入前先备份
    backup_path = f"{path}.bak"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            old_content = f.read()
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(old_content)
            
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"文件 '{path}' 写入成功。备份已创建为 '{backup_path}'。"

def insert_code(path: str, line_number: int, content: str) -> str:
    """在特定行号插入代码。"""

    if not os.path.exists(path):
        return f"错误：文件 '{path}' 不存在。"
    
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    idx = max(0, min(line_number - 1, len(lines)))
    lines.insert(idx, content + "\n")
    
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return f"代码已成功插入到 '{path}' 的第 {line_number} 行。"

def search_code(query: str, path: str = ".") -> str:
    """在文件中搜索特定模式。（第三级上下文）"""
    results = []
    for root, dirs, files in os.walk(path):
        if any(x in root for x in [".git", ".ca", "node_modules", "__pycache__"]):
            continue
        for file in files:
            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        if query in line:
                            results.append(f"{file_path}:{i}: {line.strip()}")
            except (UnicodeDecodeError, PermissionError):
                continue
    return "\n".join(results) if results else "未找到匹配项。"

def get_file_tools():
    """返回用于文件操作的工具列表。"""
    return [read_file, write_file, insert_code, search_code]
