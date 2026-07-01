"""Type definitions for IDE integration subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IDEType(str, Enum):
    """Supported IDE types."""

    VSCODE = "vscode"
    INTELLIJ = "intellij"
    NEOVIM = "neovim"
    EMACS = "emacs"
    SUBLIME = "sublime"
    GENERIC = "generic"


class LSPMethod(str, Enum):
    """Common LSP methods."""

    COMPLETION = "textDocument/completion"
    HOVER = "textDocument/hover"
    DEFINITION = "textDocument/definition"
    REFERENCES = "textDocument/references"
    FORMATTING = "textDocument/formatting"
    CODE_ACTION = "textDocument/codeAction"
    DIAGNOSTICS = "textDocument/diagnostic"
    WORKSPACE_SYMBOL = "workspace/symbol"


@dataclass
class IDECapabilities:
    """Capabilities an IDE supports."""

    type: IDEType
    supports_lsp: bool = False
    supports_diff_preview: bool = False
    supports_inline_suggestions: bool = False
    supports_terminal_integration: bool = True
    supports_file_watching: bool = False


@dataclass
class LSPPosition:
    """Position in a text document."""

    line: int
    character: int = 0


@dataclass
class LSPRange:
    """Range in a text document."""

    start: LSPPosition
    end: LSPPosition


@dataclass
class IDEDiagnostic:
    """A diagnostic message from the IDE/LSP."""

    file: str
    range: LSPRange
    message: str
    severity: int  # 1=Error, 2=Warning, 3=Info, 4=Hint
    source: str = "coagent"
    code: str = ""
