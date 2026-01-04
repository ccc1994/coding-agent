import os

def ensure_project_setup(project_root: str):
    """
    确保必需的目录（.chaos）存在，
    并且 .chaos 文件夹被 git 忽略。
    """
    if not os.path.exists(project_root):
        os.makedirs(project_root)
        print(f"已创建项目根目录：{project_root}")

    chaos_dir = os.path.join(project_root, ".chaos")
    if not os.path.exists(chaos_dir):
        os.makedirs(chaos_dir)
        print(f"已创建元数据目录：{chaos_dir}")

    gitignore_path = os.path.join(project_root, ".gitignore")
    ignore_entries = [".chaos/"]
    
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r") as f:
            content = f.read()
        
        needed_entries = [e for e in ignore_entries if e not in content]
        
        if needed_entries:
            with open(gitignore_path, "a") as f:
                f.write("\n# Coding Agent 存储空间\n")
                for entry in needed_entries:
                    f.write(f"{entry}\n")
            print(f"已更新 .gitignore，添加了：{', '.join(needed_entries)}")
    else:
        with open(gitignore_path, "w") as f:
            f.write("# Coding Agent 存储空间\n")
            for entry in ignore_entries:
                f.write(f"{entry}\n")
        print("已创建包含存储条目的 .gitignore 文件。")

if __name__ == "__main__":
    ensure_project_setup(os.getcwd())
