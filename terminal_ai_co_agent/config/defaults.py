"""Default configuration embedded in the application."""

DEFAULT_CONFIG_TOML = """\
# Terminal AI Co-Agent — Default Configuration
# Generated automatically. Override in .coagent.toml or ~/.config/coagent/config.toml

[general]
default_provider = "ollama"
single_model_mode = false
project_root = "."

[orchestrator]
enabled = true
context_budget = 4096
compression = "moderate"

[orchestrator.cache]
enabled = true
directory = ".coagent/cache"
ttl = 3600

[models.context]
provider = "ollama"
model = "qwen2.5:0.5b"
temperature = 0.0
max_tokens = 2048
system_prompt = "You are a precise context extraction engine. Read the provided files and produce structured summaries. Do not generate code. Do not make recommendations. Only extract and summarize."

[models.reasoning]
provider = "ollama"
model = "qwen2.5:1.5b"
temperature = 0.1
max_tokens = 4096
system_prompt = "You are an expert software engineer assistant. Analyze the provided structured context, produce clear plans, explain reasoning, identify risks, and generate precise code changes."

[models.verification]
provider = "ollama"
model = "qwen2.5:0.5b"
temperature = 0.0
max_tokens = 2048
system_prompt = "You are a code reviewer. Check the proposed changes for correctness, consistency, security issues, and adherence to project conventions. Identify any potential problems."

[models.default]
provider = "ollama"
model = "qwen2.5:1.5b"
temperature = 0.1
max_tokens = 4096

[providers.ollama]
base_url = "http://localhost:11434"
timeout = 120
retry_attempts = 3
retry_delay = 1.0

[providers.openai]
api_key = "${OPENAI_API_KEY}"
base_url = "https://api.openai.com/v1"
timeout = 60
retry_attempts = 3

[providers.anthropic]
api_key = "${ANTHROPIC_API_KEY}"
base_url = "https://api.anthropic.com"
timeout = 60
retry_attempts = 3

[providers.llama_cpp]
model_path = "~/.cache/coagent/models"
server_base_url = "http://localhost:8080"
timeout = 120

[providers.vllm]
base_url = "http://localhost:8000"
timeout = 120

[safety]
approval_mode = "dangerous"
auto_rollback = true
rollback_history = 50

[memory]
backend = "sqlite"
path = ".coagent/memory"
session_persistence = true
max_project_entries = 10000

[memory.vector]
embedding_model = "all-MiniLM-L6-v2"
dimension = 384

[rag]
enabled = true
chunk_size = 1000
chunk_overlap = 200
embedding_model = "all-MiniLM-L6-v2"
vector_backend = "chromadb"
vector_path = ".coagent/vectors"

[git]
auto_commit = false
auto_branch = true
branch_pattern = "coagent/{task_slug}-{timestamp}"
sign_commits = false

[logging]
level = "INFO"
directory = ".coagent/logs"
audit = true
json_format = false
metrics = true

[plugins]
enabled = true
disabled = []

[execution]
command_timeout = 300
max_parallel_ops = 4
dry_run = false
preserve_permissions = true
respect_gitignore = true

[docs]
format = "markdown"
output_dir = "docs/generated"
api_docs = true
architecture_docs = true
diagrams = true

[testing]
framework = "pytest"
test_dir = "tests"
coverage_target = 0.8
auto_run = false
"""
