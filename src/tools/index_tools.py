import os
import config
import threading
import logging
import time
from typing import List, Optional
# 移除全局重型导入，改为函数内按需导入


# 配置日志
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# 保存索引的全局变量
_index = None
_index_lock = threading.Lock()
_observer = None  # watchdog observer
_last_update_time = 0  # 防抖：记录上次更新时间
_update_debounce_seconds = 2  # 防抖间隔

def _initialize_settings():
    """初始化 LlamaIndex 设置"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("DASHSCOPE_BASE_URL")
    embed_model = os.getenv("EMBEDDING_MODEL_ID")
    llm_model = os.getenv("DEFAULT_MODEL_ID")
    
    if not api_key:
        logger.error("DASHSCOPE_API_KEY 未设置，无法初始化 LlamaIndex")
        return False
        
    try:
        from llama_index.llms.openai_like import OpenAILike
        from llama_index.embeddings.openai import OpenAIEmbedding
        from llama_index.core import Settings
        
        Settings.llm = OpenAILike(
            model=str(llm_model),
            api_key=api_key,
            api_base=base_url,
            temperature=0.1,
            is_chat_model=True,
            is_function_calling_model=False,
            system_prompt="""
            You are an expert Q&A system that is trusted around the world.
            Always answer the query using the provided context information, and not prior knowledge.
            Some rules to follow:
            1. Never directly reference the given context in your answer.
            2. Avoid statements like 'Based on the context, ...' or 'The context information ...' or anything along those lines.
            3. list related files after your answer
            
            ** answer formate example **
            {your answer content}

            [related files]:
            src/dir1/dir2/filename
            """
        )
        Settings.embed_model = OpenAIEmbedding(
            model_name=str(embed_model),
            api_key=api_key,
            api_base=base_url,
            embed_batch_size=10
        )
        # DashScope 批量嵌入限制为 10
        Settings.embed_batch_size = 10
        return True
    except Exception as e:
        logger.error(f"LlamaIndex 设置初始化失败: {e}")
        return False

def load_ignore_patterns(project_root: str) -> List[str]:
    """从 .gitignore 加载忽略模式"""
    patterns = ['.venv', '.git', '.ca', '.cache', 'node_modules', '__pycache__']
    gitignore_path = os.path.join(project_root, ".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    # 去除路径末尾的斜杠
                    pattern = line.rstrip('/')
                    patterns.append(pattern)
    return list(set(patterns))


def _process_documents_to_nodes(documents: List):
    """
    通用函数：将 Documents 列表转换为 Nodes 列表，使用统一的分割逻辑。
    """
    # 动态解析器映射
    language_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".sh": "bash",
        ".go": "go",
        ".java": "java",
        ".html": "html",
        ".cpp": "cpp",
        ".c": "c",
    }
    splitter_cache = {}
    nodes = []
    
    for doc in documents:
        file_path = doc.metadata.get("file_path", "")
        if not file_path:
            # 尝试从 id_ 获取，如果 id_ 是路径
            if os.path.isabs(doc.id_):
                file_path = doc.id_
        
        file_ext = os.path.splitext(file_path)[1].lower()
        lang = language_map.get(file_ext)
        
        if lang:
            if lang not in splitter_cache:
                try:
                    from llama_index.core.node_parser import CodeSplitter, SentenceSplitter
                    from tree_sitter_languages import get_parser
                    # 显式传递 parser 以绕过 tree_sitter_language_pack 缺失的问题
                    parser = get_parser(lang)
                    splitter_cache[lang] = CodeSplitter(
                        language=lang,
                        chunk_lines=40,
                        chunk_lines_overlap=10,
                        max_chars=1500,
                        parser=parser
                    )
                except Exception as e:
                    logger.warning(f"为 {lang} 初始化 CodeSplitter 失败: {e}。将对 {file_path} 使用 SentenceSplitter。")
                    from llama_index.core.node_parser import SentenceSplitter
                    splitter_cache[lang] = SentenceSplitter()
            
            splitter = splitter_cache[lang]
            nodes.extend(splitter.get_nodes_from_documents([doc]))
        else:
            from llama_index.core.node_parser import SentenceSplitter
            nodes.extend(SentenceSplitter().get_nodes_from_documents([doc]))
            
    return nodes

def build_index(project_root: str):
    """
    构建项目的代码索引，并存储在 ChromaDB 中。
    如果索引已存在，则加载并检查增量更新。
    """
    global _index
    
    if not _initialize_settings():
        return
        
    db_path = os.path.join(project_root, ".ca", "chroma_db")
    
    with _index_lock:
        try:
            import chromadb
            from llama_index.vector_stores.chroma import ChromaVectorStore
            from llama_index.core import VectorStoreIndex, StorageContext
            from llama_index.core import SimpleDirectoryReader
            
            # 初始化 ChromaDB
            db = chromadb.PersistentClient(path=db_path)
            chroma_collection = db.get_or_create_collection("code_index")
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)

            ignore_patterns = load_ignore_patterns(project_root)

            # 检查是否已经有索引
            if chroma_collection.count() > 0:
                logger.info(f"正在从 {db_path} 加载现有 ChromaDB 索引 (count: {chroma_collection.count()})...")
                _index = VectorStoreIndex.from_vector_store(
                    vector_store, storage_context=storage_context
                )
                logger.info("索引加载成功。正在检查增量更新...")

                # === 启动时增量更新 ===
                try:
                    reader = SimpleDirectoryReader(
                        input_dir=project_root,
                        recursive=True,
                        required_exts=['.py', '.js', '.ts', '.tsx', '.md', '.sh', '.go', '.java', '.html'],
                        exclude=ignore_patterns,
                        filename_as_id=True
                    )
                    documents = reader.load_data()
                    
                    # refresh_ref_docs 能快速同步变更
                    refreshed_docs = _index.refresh_ref_docs(documents)
                    if any(refreshed_docs):
                        logger.info(f"检测到文件变更，已更新 {sum(refreshed_docs)} 个文档。")
                        _index.storage_context.persist(persist_dir=db_path)
                    else:
                        logger.info("未检测到文件变更。")
                except Exception as update_e:
                    logger.warning(f"启动时增量更新失败: {update_e}")

            else:
                logger.info("正在构建新索引并存入 ChromaDB...")
                
                reader = SimpleDirectoryReader(
                    input_dir=project_root,
                    recursive=True,
                    required_exts=['.py', '.js', '.ts', '.tsx', '.md', '.sh', '.go', '.java', '.html'],
                    exclude=ignore_patterns,
                    filename_as_id=True  # 关键：使用文件路径作为 ID，便于更新
                )
                documents = reader.load_data()
                
                nodes = _process_documents_to_nodes(documents)
                
                _index = VectorStoreIndex(nodes, storage_context=storage_context)
                _index.storage_context.persist(persist_dir=db_path)
                logger.info(f"索引构建完成并存入 ChromaDB，路径: {db_path}")
        except Exception as e:
            logger.error(f"构建或加载 ChromaDB 索引时出错: {e}")

def build_index_async(project_root: str):
    """
    异步构建索引，不阻塞主线程。
    """
    thread = threading.Thread(target=build_index, args=(project_root,), daemon=True)
    thread.start()
    logger.info("已启动异步索引构建任务 (使用 ChromaDB)。")

def update_index(project_root: str, changed_file: str = None):
    """
    增量更新索引。
    Args:
        project_root: 项目根目录
        changed_file: 变更的单个文件路径（可选）。如果提供，则仅更新该文件。
    """
    global _index, _last_update_time
    
    # 防抖逻辑 (仅针对全量扫描，单文件更新可以更实时)
    current_time = time.time()
    if changed_file is None:
        if current_time - _last_update_time < _update_debounce_seconds:
            return
        _last_update_time = current_time
    
    if _index is None:
        logger.warning("索引尚未初始化，无法执行增量更新。")
        return
    
    if not _initialize_settings():
        return
    
    with _index_lock:
        try:
            from llama_index.core import SimpleDirectoryReader
            
            # 持久化路径
            db_path = os.path.join(project_root, ".ca", "chroma_db")
            
            if changed_file:
                # === 单文件更新流程 ===
                logger.info(f"正在更新单文件索引: {changed_file}")
                
                # 1. 尝试从索引中删除旧文档
                try:
                    # 使用 filename_as_id=True，ID 即路径
                    _index.delete_ref_doc(changed_file, delete_from_docstore=True)
                    logger.info(f"已清理旧索引节点: {changed_file}")
                except Exception as del_err:
                    # 如果文档之前不在索引中，可能会报错，忽略
                    logger.debug(f"删除旧文档时提示: {del_err}")

                # 2. 如果文件仍存在（非删除操作），则加载并插入新节点
                if os.path.exists(changed_file):
                    reader = SimpleDirectoryReader(
                        input_files=[changed_file],
                        filename_as_id=True
                    )
                    documents = reader.load_data()
                    
                    if documents:
                        nodes = _process_documents_to_nodes(documents)
                        _index.insert_nodes(nodes)
                        logger.info(f"已插入新索引节点: {len(nodes)} 个")
                
                # 3. 持久化
                _index.storage_context.persist(persist_dir=db_path)
                
            else:
                # === 全量扫描更新流程 (Startup用) ===
                logger.info("正在执行全量扫描增量更新...")
                ignore_patterns = load_ignore_patterns(project_root)
                
                reader = SimpleDirectoryReader(
                    input_dir=project_root,
                    recursive=True,
                    required_exts=['.py', '.js', '.ts', '.tsx', '.md', '.sh', '.go', '.java', '.html'],
                    exclude=ignore_patterns,
                    filename_as_id=True
                )
                documents = reader.load_data()
                
                # refresh_ref_docs 仅在 filename_as_id=True 且 index 对接了 docstore 时有效
                # 这里我们假设 VectorStoreIndex 背后有 standard docstore。
                # 但 LlamaIndex 默认 refresh_ref_docs 可能不走自定义 splitter。
                # 为了稳妥，依然使用 refresh_ref_docs，但要注意它可能退化为 SentenceSplitter。
                # 鉴于构建时用了自定义 splitter，这里最好手动 diff。
                # 为简单起见，启动时仍用 refresh_ref_docs 快速过一遍，
                # 但更推荐用户依赖实时单文件更新来保证质量。
                
                refreshed_docs = _index.refresh_ref_docs(documents)
                if any(refreshed_docs):
                    logger.info(f"检测到文件变更，已更新 {sum(refreshed_docs)} 个文档。")
                    _index.storage_context.persist(persist_dir=db_path)
                else:
                    logger.info("未检测到文件变更。")
                    
        except Exception as e:
            logger.error(f"增量更新索引时出错: {e}")

class IndexUpdateHandler:
    """
    文件系统事件处理器基类，定义核心逻辑。
    """
    def __init__(self, project_root: str):
        self.project_root = project_root
        self.watched_extensions = {'.py', '.js', '.ts', '.tsx', '.md', '.sh', '.go', '.java', '.html'}
    
    def _should_process(self, file_path: str) -> bool:
        if os.path.exists(file_path) and os.path.isdir(file_path):
            return False
        # 处理删除事件时文件可能不存在，仅检查后缀
        ext = os.path.splitext(file_path)[1].lower()
        return ext in self.watched_extensions
    
    def handle_event(self, event, event_type: str):
        if hasattr(event, 'is_directory') and event.is_directory:
            return
            
        src = event.src_path
        if self._should_process(src):
            logger.info(f"检测到文件{event_type}: {src}")
            self._trigger_update(changed_file=src)
            
    def _trigger_update(self, changed_file: str = None):
        thread = threading.Thread(target=update_index, args=(self.project_root, changed_file), daemon=True)
        thread.start()

def start_index_watcher(project_root: str):
    """
    启动文件系统监听器，实时监控文件变化并触发增量更新。
    """
    global _observer
    
    if _observer is not None:
        logger.warning("索引监听器已在运行中。")
        return
    
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        
        # 创建一个继承自 FileSystemEventHandler 的具体类
        class WatchdogHandler(FileSystemEventHandler):
            def __init__(self, handler_logic):
                super().__init__()
                self.logic = handler_logic
                
            def on_modified(self, event):
                self.logic.handle_event(event, "修改")
                
            def on_created(self, event):
                self.logic.handle_event(event, "创建")
                
            def on_deleted(self, event):
                self.logic.handle_event(event, "删除")
                
            def on_moved(self, event):
                # 处理重命名/移动
                if not event.is_directory:
                    self.logic.handle_event(event, "移动/重命名")
        
        # 实例化逻辑类和适配器类
        logic = IndexUpdateHandler(project_root)
        handler = WatchdogHandler(logic)
        
        _observer = Observer()
        _observer.schedule(handler, project_root, recursive=True)
        _observer.start()
        
        logger.info(f"已启动索引监听器，监控目录: {project_root}")
    except Exception as e:
        logger.error(f"启动索引监听器失败: {e}")

def stop_index_watcher():
    """
    停止文件系统监听器。
    """
    global _observer
    
    if _observer is not None:
        _observer.stop()
        _observer.join()
        _observer = None
        logger.info("已停止索引监听器。")


def semantic_code_search(query: str) -> str:
    """
    语义化代码库搜索工具。基于向量索引和 LLM 总结，通过自然语言查询代码/询问实现细节。
    
    适用场景:
    1. 查找特定功能（如“退款”、“鉴权”）的具体实现位置。
    2. 跨文件分析逻辑关系（如“支付接口是如何被调用的”）。
    3. 了解项目中未知的类、函数或变量的用途和工作原理。
    
    参数说明:
    - query (str): 描述你想要查找内容的自然语言指令或问题。
    
    调用示例:
    - "找到处理用户登录逻辑的代码片段"
    - "LLMMessagesCompressor 类的主要功能是什么？"
    - "项目中如何配置 ChromaDB 的持久化存储？"
    - "搜索快速排序(quick_sort)函数的定义及其所在文件"
    """
    global _index
    
    if _index is None:
        return "ERROR: 索引尚未就绪，系统正在后台扫描项目目录，请等待约 1-2 分钟后再试。"

    base_prefix = os.path.join(config.project_root, "")
    
    try:
        from llama_index.core.postprocessor import SimilarityPostprocessor
        processor = SimilarityPostprocessor(similarity_cutoff=0.1)
        
        query_engine = _index.as_query_engine(
            similarity_top_k=5,
            node_postprocessors=[processor]
        )
        
        response_obj = query_engine.query(query)
        
        # 1. 处理回答正文：将回答中出现的绝对路径前缀删掉
        final_response_text = str(response_obj).replace(base_prefix, "")
        
        return final_response_text

    except Exception as e:
        return f"搜索执行出错: {str(e)}" 