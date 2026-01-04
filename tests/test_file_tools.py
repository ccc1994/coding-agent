import unittest
import os
import shutil
import tempfile
from src.tools.file_tools import (
    read_file, write_file, insert_code, search_code, edit_block,
    create_directory, delete_file, list_directory, get_file_tree,
    move_file, file_exists, get_file_tools
)

class TestFileTools(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for safe testing of write operations
        self.test_dir = tempfile.mkdtemp(prefix="test_file_tools_")
        self.project_root = os.getcwd()

    def tearDown(self):
        # Clean up the temporary directory
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_write_and_read_file(self):
        file_path = os.path.join(self.test_dir, "test.txt")
        content = "Hello, World!"
        
        # Test write
        result_write = write_file(file_path, content)
        self.assertIn("成功", result_write)
        self.assertTrue(os.path.exists(file_path))
        
        # Test read
        read_content = read_file(file_path)
        self.assertEqual(read_content, content)

    def test_file_exists(self):
        file_path = os.path.join(self.test_dir, "exist.txt")
        write_file(file_path, "content")
        
        self.assertIn("存在", file_exists(file_path))
        self.assertIn("不存在", file_exists(os.path.join(self.test_dir, "non_existent.txt")))

    def test_insert_code(self):
        file_path = os.path.join(self.test_dir, "code.py")
        initial_content = "line1\nline3"
        write_file(file_path, initial_content)
        
        # Insert "line2" at line 2
        result = insert_code(file_path, 2, "line2")
        self.assertIn("成功插入", result)
        
        content = read_file(file_path)
        expected_content = "line1\nline2\nline3"
        # file_tools.insert_code appends \n, so let's check split lines
        lines = content.splitlines()
        self.assertEqual(lines, ["line1", "line2", "line3"])

    def test_edit_block(self):
        file_path = os.path.join(self.test_dir, "replace.txt")
        content = "Hello old_world!"
        write_file(file_path, content)
        
        # String replacement
        result = edit_block(file_path, "old_world", "new_world")
        self.assertIn("成功替换", result)
        self.assertEqual(read_file(file_path), "Hello new_world!")
        
        # Regex replacement
        result_regex = edit_block(file_path, r"new_\w+", "regex_world", is_regex=True)
        self.assertIn("成功替换", result_regex)
        self.assertEqual(read_file(file_path), "Hello regex_world!")

    def test_directory_operations(self):
        sub_dir = os.path.join(self.test_dir, "subdir")
        
        # Create directory
        result_create = create_directory(sub_dir)
        self.assertIn("创建成功", result_create)
        self.assertTrue(os.path.isdir(sub_dir))
        
        # List directory
        write_file(os.path.join(sub_dir, "file1.txt"), "content")
        result_list = list_directory(sub_dir)
        self.assertIn("file1.txt", result_list)
        
        # Delete directory
        result_delete = delete_file(sub_dir)
        self.assertIn("已删除", result_delete)
        self.assertFalse(os.path.exists(sub_dir))

    def test_move_file(self):
        src = os.path.join(self.test_dir, "src.txt")
        dst = os.path.join(self.test_dir, "dst.txt")
        write_file(src, "data")
        
        result = move_file(src, dst)
        self.assertIn("已移动", result)
        self.assertFalse(os.path.exists(src))
        self.assertTrue(os.path.exists(dst))

    def test_search_code_real_project(self):
        """
        Test search_code using the actual project files to verify ripgrep integration.
        We search for a known string likely to exist in this file itself or main.py.
        """
        # Search for a unique string in existing codebase
        query = "def main():" 
        # Search in the src directory
        search_path = os.path.join(self.project_root, "src")
        
        result = search_code(query, path=search_path)
        
        # Expect to find "def main():" in src/main.py
        self.assertIn("src/main.py", result)
        self.assertIn("def main():", result)

    def test_search_code_local(self):
        """
        Test search_code in the temp directory to verify it works on created files.
        """
        file_path = os.path.join(self.test_dir, "search_me.py")
        write_file(file_path, "def target_function():\n    pass")
        
        result = search_code("target_function", path=self.test_dir)
        self.assertIn("search_me.py", result)
        self.assertIn("target_function", result)

    def test_get_file_tree(self):
        # Create a nested structure
        # dir/
        #   file1
        #   sub/
        #     file2
        os.makedirs(os.path.join(self.test_dir, "sub"))
        write_file(os.path.join(self.test_dir, "file1"), "c")
        write_file(os.path.join(self.test_dir, "sub", "file2"), "c")
        
        tree = get_file_tree(self.test_dir)
        self.assertIn("file1", tree)
        self.assertIn("sub/", tree)
        self.assertIn("file2", tree)

    def test_get_file_tools(self):
        tools = get_file_tools()
        self.assertTrue(len(tools) > 0)
        
        read_tools = get_file_tools("read")
        for t in read_tools:
            self.assertEqual(t.tool_type, "read")
            
        write_tools = get_file_tools("write")
        for t in write_tools:
            self.assertEqual(t.tool_type, "write")

if __name__ == "__main__":
    unittest.main()
