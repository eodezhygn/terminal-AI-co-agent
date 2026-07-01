"""LSP integration interface for IDE communication."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from terminal_ai_co_agent.logging.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class LSPBridge:
    """Bridge between Co-Agent and Language Server Protocol.

    Enables:
    - Receiving diagnostics from language servers
    - Requesting completions/hover/definitions
    - Sending code actions and suggestions
    - File change notifications

    Note: Full LSP implementation requires pygls or similar.
    This provides the interface and basic functionality.
    """

    def __init__(self) -> None:
        self._connected = False
        self._capabilities: dict[str, Any] = {}
        self._diagnostics: dict[str, list[dict[str, Any]]] = {}

    async def connect(self) -> bool:
        """Establish LSP connection."""
        try:
            from pygls.server import LanguageServer
            self._connected = True
            logger.info("lsp.connected")
            return True
        except ImportError:
            logger.warning("lsp.no_pygls", message="Install pygls for full LSP support")
            self._connected = False
            return False

    async def get_diagnostics(self, file_uri: str) -> list[dict[str, Any]]:
        """Get diagnostics for a file."""
        return self._diagnostics.get(file_uri, [])

    async def publish_diagnostics(
        self,
        file_uri: str,
        diagnostics: list[dict[str, Any]],
    ) -> None:
        """Publish diagnostics from Co-Agent analysis to IDE."""
        self._diagnostics[file_uri] = diagnostics
        logger.debug("lsp.diagnostics_published", file=file_uri, count=len(diagnostics))

    async def request_completion(
        self,
        file_uri: str,
        line: int,
        character: int,
    ) -> list[dict[str, Any]]:
        """Request code completion at a position."""
        # Placeholder: integrate with Co-Agent's AI for intelligent completions
        logger.debug("lsp.completion_requested", file=file_uri, line=line, char=character)
        return []

    async def disconnect(self) -> None:
        """Disconnect from LSP."""
        self._connected = False
        logger.info("lsp.disconnected")

    @property
    def is_connected(self) -> bool:
        """Check if LSP is connected."""
        return self._connected
