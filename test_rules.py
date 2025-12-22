#!/usr/bin/env python3
"""测试规则系统优化后的行为"""

import sys
import os
from src.agent.rules import initialize_rules
from src.tools.file_tools import write_file, insert_code
from src.tools.shell_tools import execute_shell

# 初始化规则系统
print("正在初始化规则系统...")
rules_manager = initialize_rules()
print(f"成功加载 {len(rules_manager.get_all_rules())} 条规则和 {len(rules_manager.get_all_workflows())} 个工作流")

# 测试 1: 文件写入操作
print("\n=== 测试 1: 文件写入操作 ===")
test_file = "test_write.txt"
content = "Hello, World!\n这是测试内容。"
result = write_file(test_file, content)
print(f"写入结果: {result}")

# 测试 2: 代码插入操作
print("\n=== 测试 2: 代码插入操作 ===")
insert_content = "这是插入的新内容。"
result = insert_code(test_file, 2, insert_content)
print(f"插入结果: {result}")

# 读取文件内容验证
with open(test_file, "r") as f:
    print(f"\n文件内容:")
    print(f.read())

# 测试 3: 安全命令执行
print("\n=== 测试 3: 安全命令执行 ===")
safe_commands = [
    "ls -la",
    "cat test_write.txt",
    "pwd",
    "whoami"
]

for cmd in safe_commands:
    print(f"\n执行命令: {cmd}")
    result = execute_shell(cmd)
    print(f"结果: {result}")

# 测试 4: 危险命令执行（这里不会真正执行，因为我们会在确认时取消）
print("\n=== 测试 4: 危险命令执行（应该要求确认） ===")
danger_commands = [
    "rm test_write.txt",
    "mv test_write.txt test_move.txt",
    "chmod 777 test_write.txt"
]

for cmd in danger_commands:
    print(f"\n执行命令: {cmd}")
    print("（注意：此命令会被要求确认，请输入 n 取消执行）")
    result = execute_shell(cmd)
    print(f"结果: {result}")

# 清理测试文件
print("\n=== 清理测试文件 ===")
for file in ["test_write.txt", "test_write.txt.bak"]:
    if os.path.exists(file):
        os.remove(file)
        print(f"已删除: {file}")

print("\n所有测试完成！")
