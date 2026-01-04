import os
import config
import threading
import logging
from typing import List, Optional
# 移除全局重型导入，改为函数内按需导入


# 配置日志
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# 保存索引的全局变量
_index = None
_index_lock = threading.Lock()

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

def build_index(project_root: str):
    """
    构建项目的代码索引，并存储在 ChromaDB 中。
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
            
            # 初始化 ChromaDB
            db = chromadb.PersistentClient(path=db_path)
            chroma_collection = db.get_or_create_collection("code_index")
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)

            # 检查是否已经有索引
            if chroma_collection.count() > 0:
                logger.info(f"正在从 {db_path} 加载现有 ChromaDB 索引 (count: {chroma_collection.count()})...")
                _index = VectorStoreIndex.from_vector_store(
                    vector_store, storage_context=storage_context
                )
                logger.info("索引加载成功。")
            else:
                logger.info("正在构建新索引并存入 ChromaDB...")
                
                from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
                
                ignore_patterns = load_ignore_patterns(project_root)

                reader = SimpleDirectoryReader(
                    input_dir=project_root,
                    recursive=True,
                    required_exts=['.py', '.js', '.ts', '.tsx', '.md', '.sh', '.go', '.java', '.html'],
                    exclude=ignore_patterns
                )
                documents = reader.load_data()
                
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
                                splitter_cache[lang] = SentenceSplitter()
                        
                        splitter = splitter_cache[lang]
                        nodes.extend(splitter.get_nodes_from_documents([doc]))
                    else:
                        from llama_index.core.node_parser import SentenceSplitter
                        nodes.extend(SentenceSplitter().get_nodes_from_documents([doc]))
                _index = VectorStoreIndex(nodes, storage_context=storage_context)
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