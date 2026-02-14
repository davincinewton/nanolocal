"""
SelfAgent - Intelligent co-pilot agent

Features:
- Independent provider and model configuration
- Real-time monitoring of main agent (messages + state)
- Safe memory modification through file locking
- Independent bootstrap file system (SOUL.md, etc.)
- Dedicated logging system with colored console output
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.text import Text

from nanobot.bus.queue import MessageBus
from nanobot.agent.loop import AgentLoop
from nanobot.agent.context import ContextBuilder
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.web import WebSearchTool, WebFetchTool
from nanobot.config.schema import SelfAgentConfig
from nanobot.providers.base import LLMProvider
from nanobot.bus.events import InboundMessage, OutboundMessage


class SelfAgent:
    """
    SelfAgent - Monitoring and influencing the main agent internally
    
    Characteristics:
    - Uses stronger/reasoning model than main agent
    - Autonomous operation with periodic reflection
    - Can monitor main agent's work in real-time
    - Proactively injects insights into main agent's memory
    - Main agent cannot directly invoke SelfAgent
    """
    
    def __init__(
        self,
        config: SelfAgentConfig,
        main_loop: AgentLoop,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
    ):
        self.config = config
        self.main_loop = main_loop
        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        
        # Rich console for colored output
        self.console = Console()
        
        # Setup colored logging
        self.logger = self._setup_colored_logging()
        
        # Observation buffers
        self._message_buffer: list[dict] = []
        self._state_buffer: list[dict] = []
        self._buffer_lock = asyncio.Lock()
        
        # Load bootstrap files
        self._load_bootstrap_files()
        
        # Create limited tool set
        self.tools = self._create_limited_tools()
        
        # Context builder
        self.context = ContextBuilder(workspace)
        
        # Running state
        self._running = False
        self._reflection_task: Optional[asyncio.Task] = None
    
    def _setup_colored_logging(self) -> logging.Logger:
        """Setup colored logging with dual output (file + console)"""
        logger = logging.getLogger("selfagent")
        logger.setLevel(getattr(logging, self.config.log_level))
        
        # Clear existing handlers
        logger.handlers.clear()
        
        # 1. File handler
        log_path = self.workspace / self.config.log_file
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logger.addHandler(file_handler)
        
        # 2. Console handler with Rich colors
        if self.config.console_output:
            class RichLogHandler(logging.Handler):
                def __init__(self, console):
                    super().__init__()
                    self.console = console
                
                def emit(self, record):
                    # Color mapping
                    level_colors = {
                        'DEBUG': 'dim',
                        'INFO': 'blue',
                        'WARNING': 'yellow',
                        'ERROR': 'red',
                        'CRITICAL': 'red',
                    }
                    color = level_colors.get(record.levelname, 'white')
                    
                    # Format: [SelfAgent] LEVEL: message
                    message = f"[cyan][SelfAgent][/cyan] [{color}]{record.levelname}:[/{color}] {record.getMessage()}"
                    self.console.print(message)
            
            logger.addHandler(RichLogHandler(self.console))
        
        return logger
    
    def _load_bootstrap_files(self):
        """Load SelfAgent's bootstrap files"""
        bootstrap_dir = self.workspace / self.config.bootstrap_dir
        
        files = {
            'identity': 'IDENTITY.md',
            'soul': 'SOUL.md',
            'agents': 'AGENTS.md',
            'tools': 'TOOLS.md',
        }
        
        for key, filename in files.items():
            filepath = bootstrap_dir / filename
            if filepath.exists():
                setattr(self, f'_{key}_content', filepath.read_text(encoding='utf-8'))
            else:
                setattr(self, f'_{key}_content', f"# {filename} not found")
                self.logger.warning(f"Bootstrap file not found: {filepath}")
    
    def _create_limited_tools(self) -> ToolRegistry:
        """
        Create SelfAgent's limited tool set
        
        Allowed:
        - File operations (with locking)
        - Web search
        """
        from nanobot.agent.tools.selfagent_tools import (
            LockedReadFileTool,
            LockedWriteFileTool,
            LockedEditFileTool,
            LockedListDirTool,
        )
        
        tools = ToolRegistry()
        
        # File tools (with locking, SelfAgent is not main agent)
        tools.register(LockedReadFileTool(self.workspace, is_main_agent=False))
        tools.register(LockedWriteFileTool(self.workspace, is_main_agent=False))
        tools.register(LockedEditFileTool(self.workspace, is_main_agent=False))
        tools.register(LockedListDirTool(self.workspace, is_main_agent=False))
        
        # Web tools
        tools.register(WebSearchTool())
        tools.register(WebFetchTool())
        
        # TODO: Load skills from config (reserved for future)
        
        return tools
    
    def _log_reflection(self, msg: str):
        """Special reflection log (magenta marker)"""
        self.console.print(f"[cyan][SelfAgent][/cyan] [magenta]⟳ Reflection:[/magenta] {msg}")
        self.logger.info(f"Reflection: {msg}")
    
    async def start(self) -> None:
        """Start SelfAgent"""
        if not self.config.enabled:
            self.logger.info("SelfAgent is disabled in config")
            return
        
        self._running = True
        self.logger.info("=" * 50)
        self.logger.info("SelfAgent starting...")
        self.logger.info(f"Provider: {self.config.provider}")
        self.logger.info(f"Model: {self.config.model or 'default'}")
        self.logger.info(f"Reflection interval: {self.config.reflection_interval}s")
        self.logger.info("=" * 50)
        
        # Register monitors
        self.bus.add_monitor(self._on_message)
        self.main_loop.add_observer(self._on_main_state_change)
        
        # Start reflection loop
        self._reflection_task = asyncio.create_task(self._reflection_loop())
        
        self.logger.info("SelfAgent started and monitoring")
    
    async def stop(self) -> None:
        """Stop SelfAgent"""
        self._running = False
        self.logger.info("SelfAgent stopping...")
        
        # Unregister monitors
        self.bus.remove_monitor(self._on_message)
        self.main_loop.remove_observer(self._on_main_state_change)
        
        # Cancel reflection task
        if self._reflection_task:
            self._reflection_task.cancel()
            try:
                await self._reflection_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("SelfAgent stopped")
    
    async def _on_message(self, direction: str, msg: Any) -> None:
        """Monitor messages"""
        async with self._buffer_lock:
            self._message_buffer.append({
                "timestamp": datetime.now().isoformat(),
                "direction": direction,
                "channel": getattr(msg, 'channel', 'unknown'),
                "preview": str(msg)[:300],
            })
            
            # Limit buffer size
            if len(self._message_buffer) > 1000:
                self._message_buffer = self._message_buffer[-500:]
    
    async def _on_main_state_change(self, event: str, data: dict) -> None:
        """Monitor main agent state"""
        async with self._buffer_lock:
            self._state_buffer.append({
                "timestamp": datetime.now().isoformat(),
                "event": event,
                "data": data,
            })
            
            # Limit buffer size
            if len(self._state_buffer) > 1000:
                self._state_buffer = self._state_buffer[-500:]
        
        # Reserved intervention interface (currently only logs)
        if event == "error":
            self.logger.warning(f"Main agent error detected: {data}")
            # await self._intervene(data)  # Reserved interface
    
    async def _intervene(self, trigger_data: dict) -> None:
        """Intervention interface (reserved)"""
        self.logger.info(f"Intervention interface called with: {trigger_data}")
        # Not implemented yet
        pass
    
    async def _reflection_loop(self) -> None:
        """Periodic reflection loop"""
        self.logger.info(f"Reflection loop started (interval: {self.config.reflection_interval}s)")
        
        while self._running:
            try:
                await asyncio.sleep(self.config.reflection_interval)
                await self._perform_reflection()
            except asyncio.CancelledError:
                self.logger.info("Reflection loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Reflection error: {e}", exc_info=True)
    
    async def _perform_reflection(self) -> None:
        """Perform reflection"""
        async with self._buffer_lock:
            messages = self._message_buffer.copy()
            states = self._state_buffer.copy()
            self._message_buffer.clear()
            self._state_buffer.clear()
        
        if not messages and not states:
            return
        
        self._log_reflection(f"Analyzing {len(messages)} messages, {len(states)} states")
        
        # Build system prompt
        system_prompt = self._build_system_prompt()
        
        # Build user prompt
        user_prompt = self._build_reflection_prompt(messages, states)
        
        # Execute agent loop
        result = await self._run_agent_loop(system_prompt, user_prompt)
        
        self._log_reflection(f"Completed: {result[:100]}...")
    
    def _build_system_prompt(self) -> str:
        """Build system prompt"""
        parts = [
            self._identity_content,
            self._soul_content,
            self._agents_content,
            self._tools_content,
            "",
            "# SelfAgent Instructions",
            "You are an internal monitoring agent.",
            "You observe the main agent's activities and can influence it through memory files.",
            "",
            "When writing insights to MEMORY.md, use this format:",
            "潜意识: [your insight here]",
            "",
            "Available tools: read_file, write_file, edit_file, list_dir, web_search, web_fetch",
        ]
        return "\n\n".join(parts)
    
    def _build_reflection_prompt(self, messages: list, states: list) -> str:
        """Build reflection prompt"""
        return f"""Please reflect on the main agent's recent activity:

## Messages Observed ({len(messages)} total)
{json.dumps(messages[-20:], indent=2, ensure_ascii=False)}

## State Changes ({len(states)} total)
{json.dumps(states[-20:], indent=2, ensure_ascii=False)}

## Your Task
1. Analyze patterns in the main agent's behavior
2. Identify any issues or inefficiencies
3. Consider if you should add insights to MEMORY.md
4. Use your tools to read files if needed

Remember: When writing to MEMORY.md, start with '潜意识:'"""
    
    async def _run_agent_loop(self, system_prompt: str, user_prompt: str) -> str:
        """Run agent loop"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        for iteration in range(self.config.max_iterations):
            try:
                response = await self.provider.chat(
                    messages=messages,
                    tools=self.tools.get_definitions(),
                    model=self.config.model,
                )
                
                self.logger.debug(f"Iteration {iteration + 1}: {response.content[:100] if response.content else 'no content'}...")
                
                if not response.has_tool_calls:
                    return response.content or ""
                
                # Execute tool calls
                for tool_call in response.tool_calls:
                    self.logger.info(f"Executing tool: {tool_call.name}")
                    
                    result = await self.tools.execute(
                        tool_call.name,
                        tool_call.arguments
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
                    
            except Exception as e:
                self.logger.error(f"Error in agent loop iteration {iteration + 1}: {e}")
                raise
        
        return "Max iterations reached"
