import os
import re
import shutil
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

def edit_block(path: str, pattern: str, replacement: str, is_regex: bool = False) -> str:
    """
    使用正则或字符串匹配替换文件中的代码块。
    
    使用场景：
    - 局部修改文件，避免全量重写
    - 批量替换相同模式的代码
    - 重构函数名、变量名
    
    Args:
        path: 文件路径
        pattern: 要匹配的模式（字符串或正则表达式）
        replacement: 替换内容
        is_regex: 是否使用正则表达式（默认 False）
    
    Returns:
        操作结果描述，包含替换次数
    
    示例：
        >>> edit_block("app.py", "old_function", "new_function")
        "成功替换 3 处匹配项"
    """
    try:
        if not os.path.exists(path):
            return f"错误：文件 '{path}' 不存在。"
        
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 备份原文件
        backup_path = f"{path}.bak"
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        # 执行替换
        if is_regex:
            new_content, count = re.subn(pattern, replacement, content)
        else:
            count = content.count(pattern)
            new_content = content.replace(pattern, replacement)
        
        if count == 0:
            return f"警告：未找到匹配项 '{pattern}'。文件未修改。"
        
        # 写入修改后的内容
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        return f"成功替换 {count} 处匹配项。备份已保存为 '{backup_path}'。"
    except re.error as e:
        return f"正则表达式错误：{str(e)}"
    except Exception as e:
        return f"编辑失败：{str(e)}"

def create_directory(path: str) -> str:
    """创建目录（包括父目录）。"""
    try:
        os.makedirs(path, exist_ok=True)
        return f"目录 '{path}' 创建成功。"
    except Exception as e:
        return f"创建目录失败：{str(e)}"

def delete_file(path: str) -> str:
    """删除文件或目录。"""
    try:
        if os.path.isfile(path):
            os.remove(path)
            return f"文件 '{path}' 已删除。"
        elif os.path.isdir(path):
            shutil.rmtree(path)
            return f"目录 '{path}' 已删除。"
        else:
            return f"错误：'{path}' 不存在。"
    except Exception as e:
        return f"删除失败：{str(e)}"

def list_directory(path: str = ".") -> str:
    """列出目录内容。"""
    try:
        if not os.path.exists(path):
            return f"错误：目录 '{path}' 不存在。"
        
        items = os.listdir(path)
        if not items:
            return f"目录 '{path}' 为空。"
        
        result = []
        for item in sorted(items):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                result.append(f"[DIR]  {item}/")
            else:
                size = os.path.getsize(item_path)
                result.append(f"[FILE] {item} ({size} bytes)")
        
        return "\n".join(result)
    except Exception as e:
        return f"列出目录失败：{str(e)}"

def move_file(src: str, dst: str) -> str:
    """移动或重命名文件/目录。"""
    try:
        if not os.path.exists(src):
            return f"错误：源路径 '{src}' 不存在。"
        
        shutil.move(src, dst)
        return f"'{src}' 已移动到 '{dst}'。"
    except Exception as e:
        return f"移动失败：{str(e)}"

def file_exists(path: str) -> str:
    """检查文件或目录是否存在。"""
    if os.path.exists(path):
        if os.path.isfile(path):
            size = os.path.getsize(path)
            return f"文件 '{path}' 存在 ({size} bytes)。"
        elif os.path.isdir(path):
            return f"目录 '{path}' 存在。"
    return f"'{path}' 不存在。"

def get_file_tools():
    """返回用于文件操作的工具列表。"""
    return [
        read_file, 
        write_file, 
        insert_code, 
        search_code,
        edit_block,
        create_directory,
        delete_file,
        list_directory,
        move_file,
        file_exists
    ]
