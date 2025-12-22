import os

def ensure_project_setup(project_root: str):
    """
    确保必需的目录（.ca, playground）存在，
    并且 .ca 文件夹被 git 忽略。
    """
    ca_dir = os.path.join(project_root, ".ca")
    if not os.path.exists(ca_dir):
        os.makedirs(ca_dir)
        print(f"已创建元数据目录：{ca_dir}")

    playground_dir = os.path.join(project_root, "playground")
    if not os.path.exists(playground_dir):
        os.makedirs(playground_dir)
        print(f"已创建游乐场 (playground) 目录：{playground_dir}")

    gitignore_path = os.path.join(project_root, ".gitignore")
    ignore_entries = [".ca/", "playground/"]
    
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r") as f:
            content = f.read()
        
        needed_entries = [e for e in ignore_entries if e not in content]
        
        if needed_entries:
            with open(gitignore_path, "a") as f:
                f.write("\n# Coding Agent 存储空间和游乐场\n")
                for entry in needed_entries:
                    f.write(f"{entry}\n")
            print(f"已更新 .gitignore，添加了：{', '.join(needed_entries)}")
    else:
        with open(gitignore_path, "w") as f:
            f.write("# Coding Agent 存储空间和游乐场\n")
            for entry in ignore_entries:
                f.write(f"{entry}\n")
        print("已创建包含存储条目的 .gitignore 文件。")

if __name__ == "__main__":
    ensure_project_setup(os.getcwd())
