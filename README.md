# AI 编码助手 CHAOS

![Chaos Banner](chaos_banner.png)

> 🚀 个人练手项目 - 基于多 Agent 协作的智能编码助手

## 项目简介

这是一个基于 AutoGen 框架的多 Agent CLI 工具，旨在通过 AI 驱动的方式自动化软件开发流程。系统采用有限状态机（FSM）编排多个专业化 Agent，实现从需求分析、代码编写、审核到测试的完整开发闭环。

## 技术栈

### 核心框架
- **Python 3.x** - 主要开发语言
- **AutoGen 0.10.3** - 微软开源的多 Agent 编排框架
- **Rich** - 终端 UI 美化库
- **Phoenix** - AI 可观测性平台
- **LlamaIndex** - 代码库索引与 RAG 检索
- **ChromaDB** - 向量数据库
- **LSP (Language Server Protocol)** - 代码静态分析

### 工具集成
- **文件操作**: 读写、编辑、搜索 (Ripgrep)、目录管理
- **代码编辑**: 正则替换、行号插入、块编辑
- **Shell 执行**: 支持实时输出和交互式命令

## 架构设计

### 多 Agent 角色

```
User → Architect → Coder → Reviewer → Tester → User
         ↓           ↓        ↓          ↓
      规划设计    代码实现   质量审核   功能验证
```

1. **Architect (架构师)**
   - 分析需求，设计技术方案
   - 输出任务清单和文件结构规划
   - 拥有读工具权限，仅负责规划

2. **Coder (开发工程师)**
   - 执行代码编写和文件操作
   - 拥有完整工具集：文件、Shell、LSP、代码搜索

3. **Reviewer (代码审核专家)**
   - 检查代码质量、安全性、一致性
   - 无工具权限，仅提供审核反馈
   - 检测错误循环并触发熔断机制

4. **Tester (测试工程师)**
   - 执行测试命令，验证功能
   - 拥有 Shell 工具权限
   - 有权终止会话

### Agent 编排

Architect -> [Coder, Reviewer, Test], 其中 [Coder, Reviewer, Test] 是一个 NestedChat 的开发小组, Architect 生成好开发计划之后, 每次将一个任务分配给开发小组, 开发小组根据任务分配, 分别执行代码实现、质量审核、功能验证等任务。并反馈给 Architect, Architect 根据反馈, 继续推进或调整开发计划

### 成本优化策略

1. **轻量级 Manager 模型**: 使用 qwen-flash
2. **错误循环检测**: 自动识别重复错误，避免无效重试
3. **智能上下文压缩**: 仅压缩必要的历史对话，保留关键信息，显著降低 Token 消耗
4. **缓存复用机制**: 避免重复压缩相同内容，减少不必要的 LLM 调用

## 使用方式

### 1. 环境配置

创建 `.env` 文件：

```bash
DASHSCOPE_API_KEY=your_api_key_here
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# 完成一些简单任务, 速度较快的模型 
GENERAL_MODEL_ID=qwen-flash-2025-07-28

# 专用模型
ARCHITECT_MODEL_ID=qwen-plus-2025-07-28
CODER_MODEL_ID=qwen3-coder-plus
REVIEWER_MODEL_ID=qwen3-coder-plus
TESTER_MODEL_ID=qwen3-coder-plus
EMBEDDING_MODEL_ID=text-embedding-v4
```

### 2. 安装依赖

```bash
# 使用 uv (推荐)
uv sync
```

### 3. 启动系统
默认会在工程下的 `playground` 目录工作

```bash
./run.sh
```

### 4. 交互命令

- **普通对话**: 直接输入需求，如 "帮我创建一个 React 项目"
- **多行输入**: 使用 `Alt+Enter` 换行，`Enter` 提交完整需求
- **退出系统**: 输入 `exit`
- **上下文控制**: 系统会自动压缩历史对话，保留最近几轮和最前面的 N 条消息（可配置）

### 5. 工作流示例

```
> 请帮我初始化一个 React 项目，首页显示 Hello World

[Architect] 分析需求，输出任务清单
[Coder] 执行 npx create-react-app，创建文件
[Reviewer] 检查代码质量和结构
[Tester] 运行 npm start 验证功能
[User] 查看结果，提供反馈
```

## 核心特性

### ✅ 已实现

- [x] FSM 状态机编排, 通过大模型智能选择下一个 Speaker
- [x] 轻量级 Manager 模型（成本优化）
- [x] 完整工具集（文件、Shell、RAG、LSP）
- [x] 实时命令输出流
- [x] 交互式命令支持（npx, npm init）
- [x] 错误循环检测与熔断
- [x] 正则表达式代码编辑
- [x] 智能上下文压缩（支持 `keep_first_n` 参数，保留最前面 N 条消息不参与压缩，优化 Token 消耗）
- [x] 多行输入支持（Alt+Enter 换行，Enter 提交）
- [x] 美化控制台界面（ASCII 艺术字、颜色渐变）
- [x] Phoenix 可观测性集成
- [x] **LlamaIndex 代码索引与语义搜索**：基于向量数据库的代码库 RAG
- [x] **LSP (Language Server Protocol) 深度集成**：支持跳转定义、查找引用、获取符号信息

### 🚧 待优化

- [ ] 长期对话历史保存
- [ ] 长时间任务执行
- [ ] Skills 扩展机制
- [ ] 代码执行沙箱

## 可观测性

### Phoenix 集成

项目集成了 **Phoenix** 可观测性平台，用于监控和分析 Agent 行为：

- **启动方式**: 运行 `./phoenix.sh` 启动 Phoenix 服务器
- **访问地址**: http://localhost:6006
- **监控指标**:
  - 上下文压缩效果（消息数量、token数、压缩率）
  - LLM 调用延迟和成本
  - Agent 交互流程和状态转换
  - 工具调用统计和执行结果

## 安全策略

### 命令执行安全

- **硬阻断**: `rm -rf /`, `curl | sh` 等极危险命令
- **确认提示**: `rm`, `sudo`, `chmod` 等危险操作需用户确认
- **直接执行**: 安全命令（npm install, git status）无需确认
