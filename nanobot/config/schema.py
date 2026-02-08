"""Configuration schema using Pydantic."""

from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class WhatsAppConfig(BaseModel):
    """WhatsApp channel configuration."""
    enabled: bool = False
    bridge_url: str = "ws://localhost:3001"
    allow_from: list[str] = Field(default_factory=list)  # Allowed phone numbers


class TelegramConfig(BaseModel):
    """Telegram channel configuration."""
    enabled: bool = False
    token: str = ""  # Bot token from @BotFather
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs or usernames
    proxy: str | None = None  # HTTP/SOCKS5 proxy URL, e.g. "http://127.0.0.1:7890" or "socks5://127.0.0.1:1080"


class FeishuConfig(BaseModel):
    """Feishu/Lark channel configuration using WebSocket long connection."""
    enabled: bool = False
    app_id: str = ""  # App ID from Feishu Open Platform
    app_secret: str = ""  # App Secret from Feishu Open Platform
    encrypt_key: str = ""  # Encrypt Key for event subscription (optional)
    verification_token: str = ""  # Verification Token for event subscription (optional)
    allow_from: list[str] = Field(default_factory=list)  # Allowed user open_ids


class DiscordConfig(BaseModel):
    """Discord channel configuration."""
    enabled: bool = False
    token: str = ""  # Bot token from Discord Developer Portal
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs
    gateway_url: str = "wss://gateway.discord.gg/?v=10&encoding=json"
    intents: int = 37377  # GUILDS + GUILD_MESSAGES + DIRECT_MESSAGES + MESSAGE_CONTENT


class ChannelsConfig(BaseModel):
    """Configuration for chat channels."""
    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)


class AgentDefaults(BaseModel):
    """Default agent configuration."""
    workspace: str = "~/.nanobot/workspace"
    model: str = "anthropic/claude-opus-4-5"
    max_tokens: int = 8192
    temperature: float = 0.7
    max_tool_iterations: int = 20


class AgentsConfig(BaseModel):
    """Agent configuration."""
    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(BaseModel):
    """LLM provider configuration."""
    api_key: str = ""
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None  # Custom headers (e.g. APP-Code for AiHubMix)


class ProvidersConfig(BaseModel):
    """Configuration for LLM providers."""
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)
    deepseek: ProviderConfig = Field(default_factory=ProviderConfig)
    groq: ProviderConfig = Field(default_factory=ProviderConfig)
    zhipu: ProviderConfig = Field(default_factory=ProviderConfig)
    dashscope: ProviderConfig = Field(default_factory=ProviderConfig)  # 阿里云通义千问
    vllm: ProviderConfig = Field(default_factory=ProviderConfig)
    gemini: ProviderConfig = Field(default_factory=ProviderConfig)
    moonshot: ProviderConfig = Field(default_factory=ProviderConfig)
    aihubmix: ProviderConfig = Field(default_factory=ProviderConfig)  # AiHubMix API gateway
    
    # Allow additional dynamic providers (lc147, lc157, etc.)
    model_config = {"extra": "allow"}
    
    def __getattr__(self, name):
        """Dynamic access to provider configs."""
        # Check if this is a provider in extra fields
        if name in self.__dict__.get('__pydantic_extra__', {}):
            return self.__dict__['__pydantic_extra__'][name]
        # Return default empty provider for undefined providers
        return ProviderConfig()


class GatewayConfig(BaseModel):
    """Gateway/server configuration."""
    host: str = "0.0.0.0"
    port: int = 18790


class WebSearchConfig(BaseModel):
    """Web search tool configuration."""
    searxng_url: str | None = None  # SearXNG实例URL，如 "http://localhost:8080"
    max_results: int = 5  # 最多返回结果数（1-10）


class WebToolsConfig(BaseModel):
    """Web tools configuration."""
    search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ExecToolConfig(BaseModel):
    """Shell exec tool configuration."""
    timeout: int = 60


class ToolsConfig(BaseModel):
    """Tools configuration."""
    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    restrict_to_workspace: bool = False  # If true, restrict all tool access to workspace directory


class Config(BaseSettings):
    """Root configuration for nanobot."""
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    
    @property
    def workspace_path(self) -> Path:
        """Get expanded workspace path."""
        return Path(self.agents.defaults.workspace).expanduser()
    
    # Default base URLs for API gateways
    _GATEWAY_DEFAULTS = {"openrouter": "https://openrouter.ai/api/v1", "aihubmix": "https://aihubmix.com/v1"}

    def get_provider(self, model: str | None = None) -> ProviderConfig | None:
        """Get matched provider config (api_key, api_base, extra_headers). Falls back to first available."""
        model = (model or self.agents.defaults.model).lower()
        p = self.providers
        
        # Collect all available providers with API keys
        all_providers = []
        
        # Add predefined providers
        keyword_map = {
            "aihubmix": p.aihubmix, "openrouter": p.openrouter,
            "deepseek": p.deepseek, "anthropic": p.anthropic, "claude": p.anthropic,
            "openai": p.openai, "gpt": p.openai, "gemini": p.gemini,
            "zhipu": p.zhipu, "glm": p.zhipu, "zai": p.zhipu,
            "dashscope": p.dashscope, "qwen": p.dashscope,
            "groq": p.groq, "moonshot": p.moonshot, "kimi": p.moonshot, "vllm": p.vllm,
        }
        
        # Add keyword-matched providers first (higher priority)
        for kw, provider in keyword_map.items():
            # Use exact prefix matching to avoid partial matches
            if model.startswith(kw + '/') and provider.api_key:
                all_providers.append(provider)
        
        # Add dynamic providers (lc147, lc157, etc.)  
        extra_fields = getattr(p, '__pydantic_extra__', {})
        for provider_name, provider_data in extra_fields.items():
            if isinstance(provider_data, dict) and provider_data.get('api_key'):
                provider_config = ProviderConfig(**provider_data)
                # Add to keyword map for exact prefix matching
                keyword_map[provider_name] = provider_config
                # Check if this provider matches the model exactly
                if model.startswith(provider_name + '/'):
                    all_providers.append(provider_config)
        
        # Fallback to any provider with API key
        if not all_providers:
            all_providers = [p.openrouter, p.aihubmix, p.anthropic, p.openai, p.deepseek,
                             p.gemini, p.zhipu, p.dashscope, p.moonshot, p.vllm, p.groq]
            extra_fields = getattr(p, '__pydantic_extra__', {})
            for provider_name, provider_data in extra_fields.items():
                if isinstance(provider_data, dict) and provider_data.get('api_key'):
                    all_providers.append(ProviderConfig(**provider_data))
        
        # Return the first provider with an API key
        return next((pr for pr in all_providers if pr and pr.api_key), None)
    
    def get_all_providers(self, model: str | None = None) -> list[tuple[str, ProviderConfig]]:
        """Get all available providers with API keys for debugging."""
        model = (model or self.agents.defaults.model).lower()
        p = self.providers
        
        available = []
        
        # Keyword → provider mapping
        keyword_map = {
            "aihubmix": p.aihubmix, "openrouter": p.openrouter,
            "deepseek": p.deepseek, "anthropic": p.anthropic, "claude": p.anthropic,
            "openai": p.openai, "gpt": p.openai, "gemini": p.gemini,
            "zhipu": p.zhipu, "glm": p.zhipu, "zai": p.zhipu,
            "dashscope": p.dashscope, "qwen": p.dashscope,
            "groq": p.groq, "moonshot": p.moonshot, "kimi": p.moonshot, "vllm": p.vllm,
        }
        
        # Add predefined providers
        for kw, provider in keyword_map.items():
            if provider.api_key:
                available.append((kw, provider))
        
        # Add dynamic providers
        extra_fields = getattr(p, '__pydantic_extra__', {})
        for provider_name, provider_data in extra_fields.items():
            if isinstance(provider_data, dict) and provider_data.get('api_key'):
                provider_config = ProviderConfig(**provider_data)
                available.append((provider_name, provider_config))
        
        return available

    def get_api_key(self, model: str | None = None) -> str | None:
        """Get API key for the given model. Falls back to first available key."""
        p = self.get_provider(model)
        return p.api_key if p else None
    
    def get_api_base(self, model: str | None = None) -> str | None:
        """Get API base URL for the given model. Applies default URLs for known gateways."""
        p = self.get_provider(model)
        if p and p.api_base:
            return p.api_base
        # Default URLs for known gateways (openrouter, aihubmix)
        for name, url in self._GATEWAY_DEFAULTS.items():
            if p == getattr(self.providers, name):
                return url
        return None
    
    class Config:
        env_prefix = "NANOBOT_"
        env_nested_delimiter = "__"
