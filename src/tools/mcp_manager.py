import os
import json
import logging
from typing import Dict, Any, Callable, List
from contextlib import AsyncExitStack

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.types import Tool
except ImportError:
    # Fallback/Mock for environments where mcp might fail to install (though we just installed it)
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None
    Tool = None

logger = logging.getLogger(__name__)

class MCPManager:
    def __init__(self, project_root: str):
        self.project_root = project_root
        self.config_path = os.path.join(project_root, ".chaos", "mcp.json")
        self.exit_stack = AsyncExitStack()
        self.sessions: Dict[str, ClientSession] = {}
        self.tools: List[Dict[str, Any]] = [] # List of OpenAI-compatible tool definitions
        self.tool_functions: Dict[str, Callable] = {} # Map of name -> callable

    async def initialize(self):
        """Read config and connect to servers."""
        if not ClientSession:
            logger.warning("MCP library not available.")
            return

        if not os.path.exists(self.config_path):
            return

        try:
            with open(self.config_path, "r") as f:
                content = f.read().strip()
                if not content:
                    return
                config = json.loads(content)
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            return

        mcp_servers = config.get("mcp_servers", {})
        
        for name, server_config in mcp_servers.items():
            try:
                command = server_config.get("command")
                args = server_config.get("args", [])
                env_vars = server_config.get("env")
                
                if not command:
                    continue
                
                # Merge current env with provided env
                env = os.environ.copy()
                if env_vars:
                    env.update(env_vars)

                server_params = StdioServerParameters(
                    command=command,
                    args=args,
                    env=env
                )
                
                # Enter the context manager and keep it alive
                read, write = await self.exit_stack.enter_async_context(stdio_client(server_params))
                session = await self.exit_stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                
                self.sessions[name] = session
                logger.info(f"Connected to MCP server: {name}")
                
                # Fetch tools
                result = await session.list_tools()
                for tool in result.tools:
                    self._register_tool(name, session, tool)
                    
            except Exception as e:
                logger.error(f"Failed to connect to MCP server {name}: {e}")

    def _register_tool(self, server_name: str, session: Any, tool_model: Any):
        """Register an MCP tool."""
        # Ensure unique name
        # We prefix with server name to avoid collisions if multiple servers have same tool names
        # But for UX, maybe we check if it's unique first?
        # Let's use name directly if unique, else prefix.
        
        tool_name = tool_model.name
        if tool_name in self.tool_functions:
            tool_name = f"{server_name}_{tool_model.name}"
            
        async def wrapped_tool(**kwargs):
            # MCP expects a dictionary of arguments
            result = await session.call_tool(tool_model.name, arguments=kwargs)
            # Result is a CallToolResult, usually has content list (TextContent or ImageContent)
            # We return the text content
            output = []
            if hasattr(result, 'content'):
                for content in result.content:
                    if content.type == 'text':
                        output.append(content.text)
                    elif content.type == 'image':
                        output.append(f"[Image: {content.mimeType}]")
            return "\n".join(output)

        # Store the callable
        self.tool_functions[tool_name] = wrapped_tool
        
        # Store the definition (convert to OpenAI schema)
        # MCP inputSchema IS JSON Schema, which OpenAI tools format accepts in `parameters`
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_model.description or f"Tool {tool_name}",
                "parameters": tool_model.inputSchema
            }
        }
        self.tools.append(openai_tool)

    async def cleanup(self):
        await self.exit_stack.aclose()