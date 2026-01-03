# AI 编码助手 CHAOS

> 🚀 个人练手项目 - 基于多 Agent 协作的智能编码助手

## 项目简介

这是一个基于 AutoGen 框架的多 Agent CLI 工具，旨在通过 AI 驱动的方式自动化软件开发流程。系统采用有限状态机（FSM）编排多个专业化 Agent，实现从需求分析、代码编写、审核到测试的完整开发闭环。

## 技术栈

### 核心框架
- **AutoGen 0.10.3** - 微软开源的多 Agent 编排框架
- **Python 3.x** - 主要开发语言
- **Rich** - 终端 UI 美化库
- **Phoenix** - AI 可观测性平台

### 工具集成
- **文件操作**: 读写、编辑、搜索、目录管理
- **代码编辑**: 正则替换、行号插入、块编辑
- **版本控制**: Git status/diff/add/commit
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
   - 无工具权限，仅负责规划

2. **Coder (开发工程师)**
   - 执行代码编写和文件操作
   - 拥有完整工具集：文件、Shell、Git
   - 支持批量工具调用，减少对话轮次

3. **Reviewer (代码审核专家)**
   - 检查代码质量、安全性、一致性
   - 无工具权限，仅提供审核反馈
   - 检测错误循环并触发熔断机制

4. **Tester (测试工程师)**
   - 执行测试命令，验证功能
   - 拥有 Shell 工具权限
   - 有权终止会话

### FSM 状态机编排

采用确定性状态转换图，零 LLM 调用成本：

```python
graph_dict = {
    user_proxy: [architect],           # 用户 → 架构师
    architect: [coder, user_proxy],    # 架构师 → 程序员/用户
    coder: [reviewer],                 # 程序员 → 审核员
    reviewer: [coder, tester, architect], # 审核员 → 程序员/测试员/架构师
    tester: [coder, user_proxy],       # 测试员 → 程序员/用户
}
```

### 成本优化策略

1. **FSM 替代 LLM 选择器**: Speaker 选择延迟从 1-3 秒降至 <10ms
2. **轻量级 Manager 模型**: 使用 qwen-flash，成本降低 5.3 倍
3. **批量工具调用**: 减少对话轮次，降低 Token 消耗
4. **错误循环检测**: 自动识别重复错误，避免无效重试
5. **智能上下文压缩**: 仅压缩必要的历史对话，保留关键信息，显著降低 Token 消耗
6. **缓存复用机制**: 避免重复压缩相同内容，减少不必要的 LLM 调用

## 使用方式

### 1. 环境配置

创建 `.env` 文件：

```bash
DASHSCOPE_API_KEY=your_api_key_here
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# 可选：指定各 Agent 使用的模型
ARCHITECT_MODEL_ID=qwen-plus-2025-07-28
CODER_MODEL_ID=qwen-plus-2025-07-28
REVIEWER_MODEL_ID=qwen-plus-2025-07-28
TESTER_MODEL_ID=qwen-plus-2025-07-28
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动系统

```bash
./run.sh
```

### 4. 交互命令

- **普通对话**: 直接输入需求，如 "帮我创建一个 React 项目"
- **多行输入**: 使用 `Alt+Enter` 换行，`Enter` 提交完整需求
- **退出系统**: 输入 `exit` 或 `quit`
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

- [x] FSM 状态机编排（零延迟 Speaker 选择）
- [x] 轻量级 Manager 模型（成本优化）
- [x] 完整工具集（文件、Shell、Git）
- [x] 实时命令输出流
- [x] 交互式命令支持（npx, npm init）
- [x] 错误循环检测与熔断
- [x] 正则表达式代码编辑
- [x] 版本控制集成
- [x] 智能上下文压缩（支持 `keep_first_n` 参数，保留最前面 N 条消息不参与压缩，优化 Token 消耗）
- [x] 工具调用消息对完整性保护（确保 `assistant` 与 `tool` 消息成对出现，避免 API 错误）
- [x] 多行输入支持（Alt+Enter 换行，Enter 提交）
- [x] 美化控制台界面（ASCII 艺术字、颜色渐变）
- [x] OpenTelemetry 分布式跟踪
- [x] Phoenix 可观测性集成

### 🚧 待优化

- [ ] 添加 HTTP 请求工具（API 测试）
- [ ] LSP 集成（符号查找）
- [ ] 依赖分析工具
- [ ] Web 内容获取（文档查询）
- [ ] 运行时 REPL（代码实验）

## 项目结构

```
coding-agent/
├── .agent/                    # Agent 工作空间配置
│   ├── rules/                 # 规则配置
│   │   └── security-rule.md   # 安全规则
│   └── workflows/             # 工作流配置
│       └── instructions.md    # 指令模板
├── src/
│   ├── agent/
│   │   ├── agents.py          # Agent 定义和配置
│   │   ├── orchestrator.py    # FSM 编排逻辑
│   │   ├── compress.py        # 上下文压缩功能
│   │   ├── state.py           # 状态管理
│   │   ├── prompts/           # Agent 提示词
│   │   │   ├── architect.md
│   │   │   ├── coder.md
│   │   │   ├── reviewer.md
│   │   │   └── tester.md
│   │   ├── manager.py         # 项目管理
│   │   └── context.py         # 上下文注入
│   ├── cli/
│   │   └── banner.py          # 控制台美化
│   ├── tools/
│   │   ├── file_tools.py      # 文件操作工具
│   │   ├── shell_tools.py     # Shell 执行工具
│   │   └── git_tools.py       # Git 版本控制工具
│   └── main.py                # 主入口
├── .env                       # 环境变量配置
├── .gitignore                 # Git 忽略文件
├── phoenix.sh                 # Phoenix 启动脚本
├── pyproject.toml             # Python 项目配置
├── README.md                  # 项目文档
├── requirements.txt           # Python 依赖
├── run.sh                     # 启动脚本
├── specs.md                   # 项目规范
└── uv.lock                    # 依赖锁定文件
```

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

### OpenTelemetry 跟踪

系统使用 **OpenTelemetry** 进行分布式跟踪：
- 自动记录所有 LLM 调用和 Agent 交互
- 支持自定义 Span 和属性
- 仅在实际发生上下文压缩时记录 `llm_context_compression` 跟踪节点
- 可导出到其他 APM 系统进行进一步分析

## 安全策略

### 命令执行安全

- **硬阻断**: `rm -rf /`, `curl | sh` 等极危险命令
- **确认提示**: `rm`, `sudo`, `chmod` 等危险操作需用户确认
- **直接执行**: 安全命令（npm install, git status）无需确认

### 文件操作安全

- **自动备份**: 所有文件修改前自动创建 `.bak` 备份
- **沙箱隔离**: 所有操作限定在 `playground/` 目录

## 性能指标

- **Speaker 选择延迟**: <10ms（FSM 图查找）
- **Manager 成本**: 降低 ~80%（使用 Flash 模型）
- **对话轮次**: 减少 30-50%（批量工具调用）

## 开发笔记

这是一个个人学习项目，用于探索：
- 多 Agent 协作模式
- LLM 在软件工程中的应用
- 成本优化与性能调优
- 工具设计与安全策略

欢迎提出建议和改进意见！

## License

MIT License - 仅供学习交流使用
