"""Configuration type definitions using Pydantic models."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GeneralConfig(BaseModel):
    """General application configuration."""

    default_provider: str = "ollama"
    single_model_mode: bool = False
    project_root: Path = Path(".")


class OrchestratorCacheConfig(BaseModel):
    """Orchestrator cache settings."""

    enabled: bool = True
    directory: Path = Path(".coagent/cache")
    ttl: int = Field(default=3600, ge=0, description="TTL in seconds")


class OrchestratorConfig(BaseModel):
    """Orchestration pipeline configuration."""

    enabled: bool = True
    context_budget: int = Field(default=4096, ge=512, le=32768)
    compression: Literal["minimal", "moderate", "aggressive"] = "moderate"
    cache: OrchestratorCacheConfig = Field(default_factory=OrchestratorCacheConfig)


class ModelConfig(BaseModel):
    """Configuration for a specific model role."""

    provider: str
    model: str
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=32768)
    system_prompt: str = ""


class ModelsConfig(BaseModel):
    """Complete model configuration."""

    context: ModelConfig
    reasoning: ModelConfig
    verification: ModelConfig
    default: ModelConfig


class ProviderConfig(BaseModel):
    """Configuration for a specific AI provider."""

    base_url: str
    api_key: str | None = None
    timeout: float = 60.0
    retry_attempts: int = 3
    retry_delay: float = 1.0
    model_path: Path | None = None
    server_base_url: str | None = None


class SafetyConfig(BaseModel):
    """Safety and security configuration."""

    approval_mode: Literal["all", "dangerous", "none"] = "dangerous"
    dangerous_commands: list[str] = Field(default_factory=lambda: [
        "rm -rf", "git push --force", "sudo", "chmod 777",
        "DROP TABLE", "DELETE FROM", "shutdown", "reboot",
    ])
    protected_patterns: list[str] = Field(default_factory=lambda: [
        ".env", ".env.*", "*.key", "*.pem", "secrets.*",
        "credentials.*", ".gitignore",
    ])
    auto_rollback: bool = True
    rollback_history: int = Field(default=50, ge=1, le=500)


class MemoryVectorConfig(BaseModel):
    """Vector memory configuration."""

    embedding_model: str = "all-MiniLM-L6-v2"
    dimension: int = 384


class MemoryConfig(BaseModel):
    """Memory subsystem configuration."""

    backend: Literal["file", "sqlite", "qdrant"] = "sqlite"
    path: Path = Path(".coagent/memory")
    session_persistence: bool = True
    max_project_entries: int = 10000
    vector: MemoryVectorConfig = Field(default_factory=MemoryVectorConfig)


class RAGConfig(BaseModel):
    """RAG subsystem configuration."""

    enabled: bool = True
    document_paths: list[str] = Field(default_factory=lambda: ["docs/", "*.md"])
    chunk_size: int = Field(default=1000, ge=100, le=8000)
    chunk_overlap: int = Field(default=200, ge=0, le=1000)
    embedding_model: str = "all-MiniLM-L6-v2"
    vector_backend: str = "chromadb"
    vector_path: Path = Path(".coagent/vectors")


class GitConfig(BaseModel):
    """Git integration configuration."""

    auto_commit: bool = False
    auto_branch: bool = True
    branch_pattern: str = "coagent/{task_slug}-{timestamp}"
    sign_commits: bool = False


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    directory: Path = Path(".coagent/logs")
    audit: bool = True
    json_format: bool = False
    metrics: bool = True


class PluginsConfig(BaseModel):
    """Plugin system configuration."""

    enabled: bool = True
    directories: list[Path] = Field(default_factory=lambda: [
        Path("~/.config/coagent/plugins"),
        Path("./.coagent/plugins"),
    ])
    disabled: list[str] = Field(default_factory=list)


class ExecutionConfig(BaseModel):
    """Execution engine configuration."""

    command_timeout: int = Field(default=300, ge=1)
    max_parallel_ops: int = Field(default=4, ge=1, le=32)
    dry_run: bool = False
    preserve_permissions: bool = True
    respect_gitignore: bool = True


class DocsConfig(BaseModel):
    """Documentation generation configuration."""

    format: Literal["markdown", "rst"] = "markdown"
    output_dir: Path = Path("docs/generated")
    api_docs: bool = True
    architecture_docs: bool = True
    diagrams: bool = True


class TestingConfig(BaseModel):
    """Test generation configuration."""

    framework: str = "pytest"
    test_dir: Path = Path("tests")
    coverage_target: float = Field(default=0.8, ge=0.0, le=1.0)
    auto_run: bool = False


# ── Root Config ─────────────────────────────────────────────────────


class CoAgentConfig(BaseModel):
    """Root configuration model for the Terminal AI Co-Agent."""

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    models: ModelsConfig | None = None  # Required in config, validated at load time
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    docs: DocsConfig = Field(default_factory=DocsConfig)
    testing: TestingConfig = Field(default_factory=TestingConfig)

    @field_validator("providers", mode="before")
    @classmethod
    def resolve_env_vars(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Resolve ${ENV_VAR} patterns in provider configs."""
        import os
        import re

        pattern = re.compile(r"\$\{(\w+)\}")

        def _resolve(v: Any) -> Any:
            if isinstance(v, str):
                def _replace(match: re.Match) -> str:
                    return os.environ.get(match.group(1), "")
                return pattern.sub(_replace, v)
            if isinstance(v, dict):
                return {k: _resolve(val) for k, val in v.items()}
            if isinstance(v, list):
                return [_resolve(item) for item in v]
            return v

        return _resolve(value)
