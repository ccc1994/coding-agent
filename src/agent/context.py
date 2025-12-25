import os
import json

def get_file_tree(path: str = ".") -> str:
    """生成简单的文件树字符串。（第一级上下文）"""
    tree = []
    # 获取path的绝对路径，用于比较
    abs_path = os.path.abspath(path)
    for root, dirs, files in os.walk(path):
        if any(x in root for x in [".git", ".ca", "node_modules", "__pycache__"]):
            continue
        # 检查当前root是否是初始path
        if os.path.abspath(root) == abs_path:
            # 如果是root目录，直接添加其下的文件和子目录，不显示root目录本身
            for f in files:
                tree.append(f"{f}")
            # 继续下一次循环
            continue
        # 对于子目录，正常处理
        level = root.replace(path, "").count(os.sep)
        indent = " " * 4 * (level - 1)  # 调整缩进级别，因为去掉了root目录
        tree.append(f"{indent}{os.path.basename(root)}/")
        sub_indent = " " * 4 * level
        for f in files:
            tree.append(f"{sub_indent}{f}")
    return "\n".join(tree)

def get_level1_context(project_root: str) -> str:
    """编译第一级必需的上下文。"""
    tree = get_file_tree(project_root)
    # 检查 .ca 目录下是否存在活跃的待办事项列表
    todo_list = ""
    ca_todo = os.path.join(project_root, ".ca", "todo_list.md")
    if os.path.exists(ca_todo):
        with open(ca_todo, "r") as f:
            todo_list = f.read()
            
    context = f"--- Level 1 Context ---\n[Project Structure]\n{tree}\n"
    if todo_list:
        context += f"\n[Todo List]\n{todo_list}\n"
    context += "-----------------------\n"
    return context
