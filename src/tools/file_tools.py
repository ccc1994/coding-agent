import os
import re
import shutil
from rich.prompt import Confirm
from rich.console import Console

console = Console()

def read_file(path: str) -> str:
    """读取文件内容"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
read_file.tool_type = "read"  # 添加工具类型标识

def write_file(path: str, content: str) -> str:
    """将内容写入文件。"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"文件 '{path}' 写入成功"
write_file.tool_type = "write"  # 添加工具类型标识

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
insert_code.tool_type = "write"  # 添加工具类型标识

def search_code(query: str, path: str = ".", max_matches: int = 50) -> str:
    """
    在文件中搜索特定模式。
    Args:
        query: 搜索关键词
        path: 搜索路径
        max_matches: 最大返回匹配数，防止上下文溢出
    """
    try:
        from ripgrepy import Ripgrepy, RipGrepNotFound
        
        # 使用 ripgrepy 构造搜索
        # fixed_strings(): 固定字符串搜索 (保持原函数行为，非正则)
        # line_number(): 显示行号
        # no_heading(): 不按文件分组，方便每行显示文件名
        # with_filename(): 强制每行显示文件名
        # max_columns(500): 忽略超长行
        rg = Ripgrepy(query, path)
        rg.fixed_strings().line_number().no_heading().with_filename().max_columns(500)
        
        # 执行搜索并获取结果列表
        # 注意：ripgrep 的 max_count 是指每个文件的最大匹配数，
        # 而我们的 max_matches 是全局最大匹配数。
        # 所以我们先不设限地运行，然后在 Python 层截断。
        # 如果担心性能，可以设一个较大的全局上限。
        out = rg.run()
        results = out.as_list
        
        if not results:
            return "未找到匹配项。"
            
        count = len(results)
        if count > max_matches:
            results = results[:max_matches]
            results.append(f"\n[系统提示] 搜索结果过多，已截断。仅显示前 {max_matches} 条。请尝试更精确的关键词或指定具体目录。")
            
        return "\n".join(results)

    except (ImportError, RipGrepNotFound):
        # 如果未安装 ripgrepy 或找不到 rg 引擎，回退到原生 Python 实现
        pass
    except Exception as e:
        # 其他异常也回退
        pass

    # === 原生 Python 回退实现 ===
    results = []
    matches_count = 0
    # 定义要忽略的目录和文件后缀
    ignore_dirs = {".git", ".idea", ".vscode", "__pycache__", "node_modules", "dist", "build", "venv", ".chaos", ".venv"}
    ignore_exts = {".exe", ".dll", ".so", ".bin", ".jpg", ".png", ".zip", ".pyc"}
    
    # 遍历文件
    for root, dirs, files in os.walk(path, topdown=True):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        
        for file in files:
            if any(file.endswith(ext) for ext in ignore_exts):
                continue
                
            file_path = os.path.join(root, file)
            
            try:
                with open(file_path, "r", encoding="utf-8", errors='ignore') as f:
                    for i, line in enumerate(f, 1):
                        if len(line) > 500: 
                            continue
                            
                        if query in line:
                            matches_count += 1
                            results.append(f"{file_path}:{i}: {line.strip()}")
                            
                            if matches_count >= max_matches:
                                results.append(f"\n[系统提示] 搜索结果过多，已截断。仅显示前 {max_matches} 条。请尝试更精确的关键词或指定具体目录。")
                                return "\n".join(results)
                                
            except (PermissionError, OSError):
                continue

    return "\n".join(results) if results else "未找到匹配项。"

search_code.tool_type = "read"

def replace_in_file(path: str, pattern: str, replacement: str, is_regex: bool = False) -> str:
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
        >>> replace_in_file("app.py", "old_function", "new_function")
        "成功替换 3 处匹配项"
    """
    try:
        if not os.path.exists(path):
            return f"错误：文件 '{path}' 不存在。"
        
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
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
        
        return f"成功替换 {count} 处匹配项"
    except re.error as e:
        return f"正则表达式错误：{str(e)}"
    except Exception as e:
        return f"编辑失败：{str(e)}"
replace_in_file.tool_type = "write"  # 添加工具类型标识

def create_directory(path: str) -> str:
    """创建目录（包括父目录）。"""
    try:
        os.makedirs(path, exist_ok=True)
        return f"目录 '{path}' 创建成功。"
    except Exception as e:
        return f"创建目录失败：{str(e)}"
create_directory.tool_type = "write"  # 添加工具类型标识

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
delete_file.tool_type = "write"  # 添加工具类型标识

def get_file_tree(path: str = ".", max_depth: int = 2) -> str:
    """
    以树状结构列出目录内容，支持限制递归深度。
    
    Args:
        path: 目标目录路径，默认为当前目录 "."
        max_depth: 最大递归深度，默认为 2。
    """
    try:
        if not os.path.exists(path):
            return f"错误：路径 '{path}' 不存在。"
        
        tree = []
        ignore_dirs = {".git", ".chaos", "node_modules", "__pycache__", ".venv", "build", "dist", ".cache"}
        
        # 记录起始路径的深度
        start_path = os.path.abspath(path)
        
        for root, dirs, files in os.walk(path, topdown=True):
            # 剪枝：原地修改 dirs 列表
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            
            # 计算相对于 path 的深度
            rel_path = os.path.relpath(root, path)
            if rel_path == ".":
                depth = 0
            else:
                depth = rel_path.count(os.sep) + 1
            
            if depth > max_depth:
                dirs[:] = [] # 停止进一步递归
                continue
            
            if depth == 0:
                # 只列出根目录下的文件，跳过目录名本身
                for f in sorted(files):
                    tree.append(f"├── {f}")
                continue

            # 对于子目录 (depth >= 1)
            # 缩进根据深度调整，depth=1 时无缩进
            indent = "  " * (depth - 1)
            folder_name = os.path.basename(root)
            tree.append(f"{indent}└── {folder_name}/")
            
            # 列出该目录下的文件
            if depth < max_depth:
                sub_indent = "  " * depth
                for f in sorted(files):
                    tree.append(f"{sub_indent}└── {f}")
            elif dirs:
                # 如果有子目录但达到深度限制
                sub_indent = "  " * depth
                tree.append(f"{sub_indent}└── ... (max depth reached)")

        return "\n".join(tree)
    except Exception as e:
        return f"获取文件树失败：{str(e)}"
get_file_tree.tool_type = "read"

def move_file(src: str, dst: str) -> str:
    """移动或重命名文件/目录。"""
    try:
        if not os.path.exists(src):
            return f"错误：源路径 '{src}' 不存在。"
        
        shutil.move(src, dst)
        return f"'{src}' 已移动到 '{dst}'。"
    except Exception as e:
        return f"移动失败：{str(e)}"
move_file.tool_type = "write"  # 添加工具类型标识

def file_exists(path: str) -> str:
    """检查文件或目录是否存在。"""
    if os.path.exists(path):
        if os.path.isfile(path):
            size = os.path.getsize(path)
            return f"文件 '{path}' 存在 ({size} bytes)。"
        elif os.path.isdir(path):
            return f"目录 '{path}' 存在。"
    return f"'{path}' 不存在。"
file_exists.tool_type = "read"  # 添加工具类型标识

def get_file_tools(tool_type: str = None) -> list:
    """
    返回用于文件操作的工具列表。
    
    Args:
        tool_type: 可选参数，指定工具类型。如果为 None，则返回所有工具；如果为 "read"，则返回只读工具；如果为 "write"，则返回写入工具。
    
    Returns:
        工具函数列表
    """
    all_tools = [
        read_file, 
        write_file, 
        insert_code, 
        search_code,
        replace_in_file,
        create_directory,
        delete_file,
        get_file_tree,
        move_file,
        file_exists
    ]
    
    if tool_type is None:
        return all_tools
    else:
        return [tool for tool in all_tools if hasattr(tool, 'tool_type') and tool.tool_type == tool_type]
