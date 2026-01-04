#!/usr/bin/env python3
"""
测试增量索引功能的简单脚本。
创建一个新文件，检查索引是否自动更新。
"""
import os
import sys
import time

# 确保可以导入 src 模块
sys.path.append(os.getcwd())

from dotenv import load_dotenv
from src.tools.index_tools import build_index, update_index, start_index_watcher, stop_index_watcher, semantic_code_search

def test_incremental_indexing():
    # 1. 加载环境变量
    load_dotenv()
    
    project_root = os.getcwd()
    print(f"--- 测试增量索引功能 ---")
    print(f"项目根目录: {project_root}")
    
    # 2. 构建初始索引
    print("\n[步骤 1] 构建初始索引...")
    build_index(project_root)
    
    # 3. 启动文件监听器
    print("\n[步骤 2] 启动文件监听器...")
    start_index_watcher(project_root)
    
    # 4. 创建测试文件
    test_file = os.path.join(project_root, "test_incremental.py")
    print(f"\n[步骤 3] 创建测试文件: {test_file}")
    with open(test_file, "w") as f:
        f.write("""
def test_incremental_function():
    '''这是一个测试增量索引的函数'''
    return "增量索引测试成功"
""")
    
    # 5. 等待监听器检测并更新
    print("\n[步骤 4] 等待监听器检测文件变化...")
    # 增加等待时间，确保 async update 完成
    time.sleep(10)
    
    # 6. 测试搜索
    print("\n[步骤 5] 测试搜索新创建的函数...")
    result = semantic_code_search("test_incremental_function 函数的作用是什么")
    print(f"搜索结果:\n{result}")
    
    # 7. 清理
    print("\n[步骤 6] 清理测试文件...")
    if os.path.exists(test_file):
        os.remove(test_file)
    
    # 等待监听器检测删除
    time.sleep(3)
    
    # 8. 停止监听器
    print("\n[步骤 7] 停止监听器...")
    stop_index_watcher()
    
    print("\n--- 测试完成 ---")

if __name__ == "__main__":
    test_incremental_indexing()
