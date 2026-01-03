from autogen.agentchat.contrib.capabilities.transforms import MessageTransform
from typing import Any
from opentelemetry import trace 


class LLMTextCompressor:
    """
    使用大模型压缩文本的压缩器类。
    """
    
    def __init__(self, llm_config):
        """
        初始化 LLMTextCompressor。
        
        Args:
            llm_config: 大模型配置，包含 api_key、base_url、model 等信息
        """
        self.llm_config = llm_config
    
    def compress(self, text, **kwargs):
        """
        使用大模型压缩文本。
        
        Args:
            text: 要压缩的文本内容
            **kwargs: 额外的压缩参数，如 target_token
        
        Returns:
            压缩后的文本内容
        """
        try:
            from openai import OpenAI
            
            # 获取压缩参数
            target_token = kwargs.get("target_token", 500)
            print(f"开始压缩文本，目标 token 数：{target_token}")
            compression_prompt = kwargs.get("compression_prompt", "你是一个专业的文本压缩专家。请将以下文本压缩到约 {target_token} 个token，保留核心信息、关键细节和重要结论。")
            
            # 获取 LLM 配置
            config_list = self.llm_config.get("config_list", [])
            if not config_list:
                return f"[警告：LLM 配置为空，无法压缩文本]\n{text[:1000]}..."  # 返回截断文本
            
            # 使用第一个配置
            config = config_list[0]
            
            # 构建 OpenAI 客户端
            client_params = {
                "api_key": config.get("api_key"),
                "base_url": config.get("base_url")
            }
            # api_type 参数在新版本 OpenAI 客户端中不再支持
            client = OpenAI(**client_params)
            
            # 构建压缩请求
            system_prompt = compression_prompt.format(target_token=target_token)
            
            response = client.chat.completions.create(
                model=config.get("model"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.3,
                max_tokens=target_token * 2,  # 给予足够的生成空间
            )
            
            # 提取压缩后的文本
            if response and response.choices:
                compressed_text = response.choices[0].message.content.strip()
                return compressed_text
            
            # 如果生成失败，返回截断文本
            return text[:target_token * 4]  # 粗略估计每个token对应4个字符
        except Exception as e:
            # 如果发生任何异常，返回截断文本
            target_token = kwargs.get("target_token", 500)
            return f"[警告：压缩时出错 - {str(e)}]\n{text[:target_token * 4]}..."


class LLMMessagesCompressor(MessageTransform):
    """
    直接实现 MessageTransform 接口的消息压缩类。
    压缩策略：
    1. 当整个消息的 token 数超过一定长度时才触发压缩
    2. 压缩的 prompt 作为参数传入
    3. 保留最近的几轮消息
    4. 压缩时，会将需要压缩的 messages 列表，最终压缩成一个 message，并与最后几轮消息组成最终的 message 列表
    5. 缓存压缩后的消息，并且记录位置，后续压缩的时候，利用之前已经压缩好的缓存，而不是重复压缩
    6. 如果复用已经压缩好的缓存之后，没有超过大小，也不需要压缩
    """
    
    def __init__(self, llm_config, max_tokens=10000, recent_rounds=5, compression_prompt=None, target_token=500, keep_first_n=0):
        """
        初始化 LLMMessagesCompressor。
        
        Args:
            llm_config: 大模型配置，包含 api_key、base_url、model 等信息
            max_tokens: 触发压缩的最大 token 数阈值
            recent_rounds: 保留最近的轮数
            compression_prompt: 压缩时使用的 prompt
            target_token: 压缩目标 token 数
            keep_first_n: 保留最前面的消息数量，不参与压缩（默认 0）
        """
        self.llm_config = llm_config
        self.max_tokens = max_tokens
        self.recent_rounds = recent_rounds
        self.compression_prompt = compression_prompt or "你是一个专业的文本压缩专家。请将以下对话压缩到约 {target_token} 个token，保留核心信息、关键细节和重要结论。"
        self.target_token = target_token
        self.keep_first_n = keep_first_n
        self.agent_name = "Agent" # 默认值，由 orchestrator 设置
        
        # 缓存压缩后的消息和原始消息索引
        self._compression_cache = {
            "compressed_message": None,  # 压缩后的消息
            "compressed_up_to_index": 0,  # 压缩到的消息索引
            "compressed_token_count": 0  # 压缩后的 token 数
        }
        
        # 创建 LLMTextCompressor 实例用于实际压缩
        self.llm_compressor = LLMTextCompressor(llm_config=llm_config)
    
    def _count_tokens(self, message):
        """
        估算消息的 token 数。
        
        Args:
            message: 消息字典
        
        Returns:
            token 数估算值
        """
        content = message.get("content", "")
        # 粗略估计：1 个 token 约等于 3 个汉字或 4 个英文单词
        # 这里使用更通用的估算方式：(中文数 * 0.6 + 英文单词数 * 1.3)
        # 简化版：字符数 // 3 (对于混合文本较实用)
        return len(content) // 3
    
    def _count_total_tokens(self, messages):
        """
        估算消息列表的总 token 数。
        
        Args:
            messages: 消息列表
        
        Returns:
            总 token 数估算值
        """
        return sum(self._count_tokens(msg) for msg in messages)
    
    def apply_transform(self, messages):
        """
        实现 MessageTransform 接口的方法，应用压缩策略处理消息。
        
        Args:
            messages: 原始消息列表
        
        Returns:
            处理后的消息列表
        """
        if not messages:
            return messages
            
        print(f"[{getattr(self, 'agent_name', 'Agent')}] 检查上下文压缩...")
        
        # 1. 计算当前消息的总 token 数
        # 如果有缓存的压缩消息，计算方式是：压缩消息的 token 数 + 未压缩消息的 token 数
        if self._compression_cache["compressed_message"] is not None:
            # 复用缓存
            # 未压缩的消息是从上次压缩的位置到最新消息中除了最近几轮的部分
            # 考虑keep_first_n参数，确保最前面的消息不参与压缩
            uncompressed_start_index = max(self._compression_cache["compressed_up_to_index"], self.keep_first_n)
            uncompressed_end_index = len(messages) - self.recent_rounds
            
            # 计算未压缩消息的 token 数
            if uncompressed_start_index < uncompressed_end_index:
                uncompressed_messages = messages[uncompressed_start_index:uncompressed_end_index]
                uncompressed_token_count = self._count_total_tokens(uncompressed_messages)
            else:
                uncompressed_token_count = 0
            
            # 计算最近消息的范围
            recent_start_index = len(messages) - self.recent_rounds
            
            # 检查最近几轮消息的最后一条是否是工具调用结果
            if messages and messages[-1].get("role") == "tool":
                # 如果是工具调用结果，将其加入压缩范围，调整最近消息的起始索引
                recent_start_index += 1
            
            recent_messages = messages[recent_start_index:]
            recent_token_count = self._count_total_tokens(recent_messages)
            
            # 总 token 数 = 压缩消息的 token 数 + 未压缩消息的 token 数 + 最近几轮消息的 token 数
            total_token_count = self._compression_cache["compressed_token_count"] + uncompressed_token_count + recent_token_count
            
            # 如果总 token 数未超过阈值，直接返回原始消息
            if total_token_count <= self.max_tokens:
                print(f"  - [{self.agent_name}] 当前 token 数: {total_token_count} (阈值: {self.max_tokens}) -> 跳过压缩")
                return messages
            
            print(f"  - [{self.agent_name}] 当前 token 数: {total_token_count} (阈值: {self.max_tokens}) -> 触发压缩!")
            
            # 需要压缩，计算需要压缩的消息范围
            # 新的需要压缩的消息是从上次压缩的位置到最新消息中除了最近几轮的部分
            messages_to_compress = messages[uncompressed_start_index:recent_start_index]
            
            if messages_to_compress:
                # 获取tracer
                tracer = trace.get_tracer(__name__)
                
                # 开始压缩span
                with tracer.start_as_current_span("llm_context_compression") as span:
                    # 添加压缩前的属性
                    span.set_attribute("messages.original_count", len(messages))
                    span.set_attribute("messages.original_tokens", self._count_total_tokens(messages))
                    span.set_attribute("compression.max_tokens", self.max_tokens)
                    span.set_attribute("compression.recent_rounds", self.recent_rounds)
                    span.set_attribute("compression.target_token", self.target_token)
                    span.set_attribute("compression.use_cache", True)
                    
                    # 先将缓存中的压缩消息转换为可读文本
                    compressed_content = self._compression_cache["compressed_message"].get("content", "")
                    # 移除可能的标记
                    if "[历史对话摘要]: " in compressed_content:
                        compressed_content = compressed_content.replace("[历史对话摘要]: ", "")
                    
                    # 构建需要再次压缩的文本
                    text_to_compress = compressed_content + "\n"
                    text_to_compress += "\n".join([
                        f"[{msg.get('role', 'unknown')}]: {msg.get('content', '')}"
                        for msg in messages_to_compress
                    ])
                    
                    # 调用 LLM 压缩
                    compressed_text = self.llm_compressor.compress(
                        text=text_to_compress,
                        target_token=self.target_token,
                        compression_prompt=self.compression_prompt
                    )
                    
                    # 更新缓存
                    self._compression_cache["compressed_message"] = {
                        "role": "user",
                        "content": f"[历史对话摘要]: {compressed_text}",
                        "name": "compressed_history"
                    }
                    # 使用调整后的索引更新缓存
                    self._compression_cache["compressed_up_to_index"] = recent_start_index
                    self._compression_cache["compressed_token_count"] = self._count_tokens(
                        self._compression_cache["compressed_message"]
                    )
                    
                    # 构建最终的消息列表（使用已经计算好的recent_start_index）
                    recent_messages = messages[recent_start_index:]
                    # 确保包含最前面的keep_first_n条消息
                    keep_first_messages = messages[:self.keep_first_n]
                    compressed_result = keep_first_messages + [self._compression_cache["compressed_message"]] + recent_messages
                    
                    # 添加压缩后的属性
                    span.set_attribute("messages.compressed_count", len(compressed_result))
                    span.set_attribute("messages.compressed_tokens", self._count_total_tokens(compressed_result))
                    span.set_attribute("compression.saved_tokens", self._count_total_tokens(messages) - self._count_total_tokens(compressed_result))
                    span.set_attribute("compression.compressed", True)
                    span.set_attribute("compression.compression_ratio", 
                                      ((self._count_total_tokens(messages) - self._count_total_tokens(compressed_result)) / 
                                       self._count_total_tokens(messages)) * 100 if self._count_total_tokens(messages) > 0 else 0)
                    
                    return compressed_result
        else:
            # 没有缓存，计算所有消息的 token 数
            total_token_count = self._count_total_tokens(messages)
            
            # 如果总 token 数未超过阈值，直接返回原始消息
            if total_token_count <= self.max_tokens:
                print(f"  - [{self.agent_name}] 当前 token 数: {total_token_count} (阈值: {self.max_tokens}) -> 跳过压缩")
                return messages
            
            print(f"  - [{self.agent_name}] 当前 token 数: {total_token_count} (阈值: {self.max_tokens}) -> 触发压缩!")
            
            # 需要压缩，计算需要压缩的消息范围
            if len(messages) <= self.recent_rounds:
                # 消息数量不足，无法压缩（需要保留所有消息）
                return messages
            
            # 获取tracer
            tracer = trace.get_tracer(__name__)
            
            # 开始压缩span
            with tracer.start_as_current_span("llm_context_compression") as span:
                # 添加压缩前的属性
                span.set_attribute("messages.original_count", len(messages))
                span.set_attribute("messages.original_tokens", self._count_total_tokens(messages))
                span.set_attribute("compression.max_tokens", self.max_tokens)
                span.set_attribute("compression.recent_rounds", self.recent_rounds)
                span.set_attribute("compression.target_token", self.target_token)
                span.set_attribute("compression.use_cache", False)
                
                # 计算压缩消息和最近消息的范围
                recent_start_index = len(messages) - self.recent_rounds
                
                # 检查最近几轮消息的最后一条是否是工具调用结果
                if messages and messages[-1].get("role") == "tool":
                    # 如果是工具调用结果，将其加入压缩范围，调整最近消息的起始索引
                    recent_start_index += 1
                
                # 考虑keep_first_n参数，只压缩keep_first_n之后的消息
                messages_to_compress = messages[self.keep_first_n:recent_start_index]
                recent_messages = messages[recent_start_index:]
                
                # 构建需要压缩的文本
                text_to_compress = "\n".join([
                    f"[{msg.get('role', 'unknown')}]: {msg.get('content', '')}"
                    for msg in messages_to_compress
                ])
                
                # 调用 LLM 压缩
                compressed_text = self.llm_compressor.compress(
                    text=text_to_compress,
                    target_token=self.target_token,
                    compression_prompt=self.compression_prompt
                )
                
                # 创建压缩后的消息
                compressed_message = {
                    "role": "user",
                    "content": f"[历史对话摘要]: {compressed_text}",
                    "name": "compressed_history"
                }

                # 更新缓存
                self._compression_cache["compressed_message"] = compressed_message
                self._compression_cache["compressed_up_to_index"] = recent_start_index
                self._compression_cache["compressed_token_count"] = self._count_tokens(compressed_message)
                
                # 构建最终的消息列表，包含最前面的keep_first_n条消息
                keep_first_messages = messages[:self.keep_first_n]
                compressed_result = keep_first_messages + [compressed_message] + recent_messages
                
                # 添加压缩后的属性
                span.set_attribute("messages.compressed_count", len(compressed_result))
                span.set_attribute("messages.compressed_tokens", self._count_total_tokens(compressed_result))
                span.set_attribute("compression.saved_tokens", self._count_total_tokens(messages) - self._count_total_tokens(compressed_result))
                span.set_attribute("compression.compressed", True)
                span.set_attribute("compression.compression_ratio", 
                                  ((self._count_total_tokens(messages) - self._count_total_tokens(compressed_result)) / 
                                   self._count_total_tokens(messages)) * 100 if self._count_total_tokens(messages) > 0 else 0)
                
                return compressed_result
        
        # 默认返回原始消息
        return messages

    def get_logs(
        self, pre_transform_messages: list[dict[str, Any]], post_transform_messages: list[dict[str, Any]]
    ) -> tuple[str, bool]:
        """Creates the string including the logs of the transformation

        Alongside the string, it returns a boolean indicating whether the transformation had an effect or not.

        Args:
            pre_transform_messages: A list of dictionaries representing messages before the transformation.
            post_transform_messages: A list of dictionaries representing messages after the transformation.

        Returns:
            A tuple with a string with the logs and a flag indicating whether the transformation had an effect or not.
        """
        pre_transform_messages_len = len(pre_transform_messages)
        post_transform_messages_len = len(post_transform_messages)
        
        # 计算压缩前后的token数
        pre_transform_tokens = self._count_total_tokens(pre_transform_messages)
        post_transform_tokens = self._count_total_tokens(post_transform_messages)
        
        # 检查是否发生了压缩
        if post_transform_messages_len < pre_transform_messages_len or post_transform_tokens < pre_transform_tokens:
            # 计算压缩指标
            messages_removed = pre_transform_messages_len - post_transform_messages_len
            tokens_saved = pre_transform_tokens - post_transform_tokens
            
            # 构建日志字符串
            logs_parts = []
            
            if messages_removed > 0:
                logs_parts.append(
                    f"Removed {messages_removed} messages. "
                    f"Number of messages reduced from {pre_transform_messages_len} to {post_transform_messages_len}."
                )
            else:
                logs_parts.append(
                    f"Kept all {pre_transform_messages_len} messages."
                )
            
            if tokens_saved > 0:
                # 计算压缩率
                compression_ratio = (tokens_saved / pre_transform_tokens) * 100 if pre_transform_tokens > 0 else 0
                logs_parts.append(
                    f"Reduced token count from {pre_transform_tokens} to {post_transform_tokens} "
                    f"({tokens_saved} tokens saved, {compression_ratio:.1f}% compression)."
                )
            
            # 检查是否使用了缓存
            if self._compression_cache["compressed_message"] is not None:
                logs_parts.append(
                    f"Used cached compression (compressed up to message index {self._compression_cache['compressed_up_to_index']})."
                )
            
            logs_str = " ".join(logs_parts)
            return logs_str, True
            
        return "No compression applied. Number of messages and tokens remained unchanged.", False