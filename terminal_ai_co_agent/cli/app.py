"""Terminal AI Co-Agent — CLI Application Entry Point (Updated with CoAgent integration)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn

from terminal_ai_co_agent import __version__
from terminal_ai_co_agent.app import CoAgent
from terminal_ai_co_agent.config.loader import load_config, write_default_config
from terminal_ai_co_agent.logging.logger import get_logger

# ── CLI Application ──────────────────────────────────────────────────

app = typer.Typer(
    name="coagent",
    help="Terminal AI Co-Agent — Intelligent software engineering partner",
    add_completion=False,
    no_args_is_help=True,
)

console = Console()
logger = get_logger(__name__)

# Global agent instance
_agent: CoAgent | None = None


async def get_agent() -> CoAgent:
    """Get or create the CoAgent instance."""
    global _agent
    if _agent is None or not _agent._initialized:
        _agent = CoAgent()
        await _agent.initialize()
    return _agent


async def shutdown_agent() -> None:
    """Shutdown the agent if running."""
    global _agent
    if _agent and _agent._initialized:
        await _agent.shutdown()
        _agent = None


# ── Callbacks ────────────────────────────────────────────────────────


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option("--version", "-V", help="Show version and exit"),
    ] = False,
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Path to configuration file"),
    ] = None,
) -> None:
    """Terminal AI Co-Agent — Intelligent software engineering partner."""
    if version:
        console.print(f"coagent v{__version__}")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        _show_welcome()


def _show_welcome() -> None:
    """Display welcome panel."""
    config = load_config()
    provider = config.general.default_provider
    mode = "single-model" if config.general.single_model_mode else "multi-model"

    panel = Panel.fit(
        f"[bold cyan]Terminal AI Co-Agent[/bold cyan] v{__version__}\n\n"
        f"[dim]Mode:[/dim] {mode}\n"
        f"[dim]Provider:[/dim] {provider}\n"
        f"[dim]Orchestrator:[/dim] {'enabled' if config.orchestrator.enabled else 'disabled'}\n"
        f"[dim]Safety:[/dim] {config.safety.approval_mode}\n\n"
        f"[dim]Run[/dim] [bold]coagent --help[/bold] [dim]for available commands[/dim]",
        title="Welcome",
        border_style="cyan",
    )
    console.print(panel)


# ── Commands ─────────────────────────────────────────────────────────


@app.command()
def init(
    path: Annotated[
        Path,
        typer.Argument(help="Directory to initialize"),
    ] = Path("."),
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite existing config"),
    ] = False,
) -> None:
    """Initialize coagent in a project directory."""
    config_file = path / ".coagent.toml"

    if config_file.exists() and not force:
        console.print(f"[yellow]Config already exists: {config_file}[/yellow]")
        console.print("Use --force to overwrite.")
        raise typer.Exit(1)

    write_default_config(config_file)
    console.print(f"[green]✓[/green] Initialized coagent config at {config_file}")

    dirs = [".coagent/cache", ".coagent/memory", ".coagent/logs", ".coagent/vectors"]
    for d in dirs:
        (path / d).mkdir(parents=True, exist_ok=True)
        console.print(f"[green]✓[/green] Created {d}")

    console.print("\n[bold]Next:[/bold] Run [cyan]coagent ask 'your question'[/cyan]")


@app.command()
def ask(
    query: Annotated[
        str,
        typer.Argument(help="Natural language query or task description"),
    ],
    files: Annotated[
        Optional[list[Path]],
        typer.Option("--file", "-f", help="Specific files to include in context"),
    ] = None,
    no_rag: Annotated[
        bool,
        typer.Option("--no-rag", help="Disable RAG augmentation"),
    ] = False,
) -> None:
    """Ask the Co-Agent a question or request a task."""
    async def _ask():
        agent = await get_agent()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Thinking...[/cyan]", total=None)
            result = await agent.ask(query, files=files, use_rag=not no_rag)
            progress.remove_task(task)

        if result["success"]:
            console.print(Markdown(result["response"]))
            console.print(
                f"\n[dim]{result['tokens']} tokens • "
                f"{result['elapsed_ms']}ms • "
                f"{result['pipeline_stages']} pipeline stages[/dim]"
            )
        else:
            console.print(f"[red]Error:[/red] {result.get('error', 'Unknown error')}")

    asyncio.run(_ask())


@app.command()
def plan(
    task: Annotated[
        str,
        typer.Argument(help="Task to plan"),
    ],
    auto_approve: Annotated[
        bool,
        typer.Option("--auto-approve", "-y", help="Auto-approve the generated plan"),
    ] = False,
) -> None:
    """Generate an execution plan for a task."""
    async def _plan():
        agent = await get_agent()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task_id = progress.add_task("[cyan]Planning...[/cyan]", total=None)
            result = await agent.plan(task)
            progress.remove_task(task_id)

        # Display plan
        console.print(f"\n[bold cyan]Plan:[/bold cyan] {result['summary']}\n")

        # Risk assessment
        risk = result["risk_assessment"]
        risk_color = {
            "none": "green", "low": "green", "medium": "yellow",
            "high": "red", "critical": "red",
        }.get(risk["overall"], "white")

        console.print(f"[bold]Overall Risk:[/bold] [{risk_color}]{risk['overall'].upper()}[/{risk_color}]")
        console.print(f"[dim]Score: {risk['average_score']}/4.0[/dim]\n")

        # Steps table
        table = Table(title="Execution Steps")
        table.add_column("ID", style="dim")
        table.add_column("Type", style="cyan")
        table.add_column("Description")
        table.add_column("Risk")
        table.add_column("Depends On", style="dim")

        for step in result["steps"]:
            risk_style = {
                "none": "dim", "low": "green", "medium": "yellow",
                "high": "red", "critical": "bold red",
            }.get(step["risk"], "white")

            table.add_row(
                step["id"],
                step["type"],
                step["description"][:80],
                f"[{risk_style}]{step['risk']}[/{risk_style}]",
                ", ".join(step["dependencies"]) if step["dependencies"] else "—",
            )

        console.print(table)

        # Assumptions and alternatives
        if result["assumptions"]:
            console.print("\n[bold]Assumptions:[/bold]")
            for a in result["assumptions"]:
                console.print(f"  • {a}")

        if result["alternatives"]:
            console.print("\n[bold]Alternatives Considered:[/bold]")
            for a in result["alternatives"]:
                console.print(f"  • {a}")

        # Warnings
        if result["analysis"]["warnings"]:
            console.print("\n[yellow]⚠ Warnings:[/yellow]")
            for w in result["analysis"]["warnings"]:
                console.print(f"  [yellow]• {w}[/yellow]")

        # High risk steps
        if risk.get("high_risk_steps"):
            console.print("\n[red]⚠ High Risk Steps:[/red]")
            for s in risk["high_risk_steps"]:
                console.print(f"  [red]• {s['step_id']}: {s['description']}[/red]")

        # Approval
        if auto_approve:
            await agent.approve_plan(result["plan_id"])
            console.print(f"\n[green]✓ Plan {result['plan_id']} auto-approved[/green]")
        else:
            console.print(f"\n[dim]Plan ID: {result['plan_id']}[/dim]")
            console.print("[dim]Run[/dim] [cyan]coagent execute {plan_id}[/cyan] [dim]to execute[/dim]")

    asyncio.run(_plan())


@app.command()
def execute(
    plan_id: Annotated[
        str,
        typer.Argument(help="Plan ID to execute"),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview changes without executing"),
    ] = False,
    confirm: Annotated[
        bool,
        typer.Option("--confirm", "-y", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Execute an approved plan."""
    async def _execute():
        agent = await get_agent()

        if not confirm:
            confirmed = typer.confirm(f"Execute plan {plan_id}?")
            if not confirmed:
                console.print("[yellow]Execution cancelled.[/yellow]")
                return

        if dry_run:
            console.print("[bold yellow]DRY RUN — No changes will be made[/bold yellow]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Executing...[/cyan]", total=None)
            result = await agent.execute_plan(plan_id, dry_run=dry_run)
            progress.remove_task(task)

        if result["success"]:
            console.print(f"\n[green]✓ Plan executed successfully[/green]")
            console.print(f"[dim]{len(result['results'])} operations completed[/dim]")
        else:
            console.print(f"\n[red]✗ Execution failed[/red]")

        # Show operation results
        for r in result["results"]:
            status_icon = "✓" if r["success"] else "✗"
            color = "green" if r["success"] else "red"
            console.print(f"  [{color}]{status_icon} {r['operation_id']}[/{color}]")
            if r["output"]:
                console.print(f"    [dim]{r['output'][:200]}[/dim]")
            if r["error"]:
                console.print(f"    [red]{r['error'][:200]}[/red]")

    asyncio.run(_execute())


@app.command()
def review() -> None:
    """Review current changes in the project."""
    async def _review():
        agent = await get_agent()
        result = await agent.review_changes()

        if "git" in result:
            git = result["git"]
            console.print(f"[bold]Branch:[/bold] {git['branch']}")
            console.print(f"[bold]Status:[/bold] {'Clean' if git['clean'] else 'Modified'}")
            console.print(f"  Staged: {git['staged']} | Unstaged: {git['unstaged']} | Untracked: {git['untracked']}")

            if git.get("diff"):
                console.print("\n[bold cyan]Changes:[/bold cyan]")
                syntax = Syntax(git["diff"][:3000], "diff", theme="monokai")
                console.print(syntax)

        if "security" in result:
            console.print("\n[bold yellow]Security Review:[/bold yellow]")
            for finding in result["security"]:
                icon = "⚠" if finding["critical"] > 0 else "•"
                console.print(f"  {icon} {finding['file']}: {finding['findings']} findings ({finding['critical']} critical)")

    asyncio.run(_review())


@app.command()
def rollback(
    steps: Annotated[
        int,
        typer.Argument(help="Number of steps to rollback", min=1),
    ] = 1,
    confirm: Annotated[
        bool,
        typer.Option("--confirm", "-y", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Rollback recent changes."""
    async def _rollback():
        if not confirm:
            confirmed = typer.confirm(f"Rollback {steps} step(s)?")
            if not confirmed:
                console.print("[yellow]Rollback cancelled.[/yellow]")
                return

        agent = await get_agent()
        result = await agent.rollback(steps)

        if result["success"]:
            console.print(f"[green]✓ Rolled back {result['operations_rolled_back']} operation(s)[/green]")
        else:
            console.print(f"[red]✗ Rollback partially failed[/red]")

        for detail in result["details"]:
            icon = "✓" if detail["success"] else "✗"
            console.print(f"  {icon} {detail['operation_id']}: {detail['output'][:100]}")

    asyncio.run(_rollback())


@app.command()
def context(
    action: Annotated[
        str,
        typer.Argument(help="Action: show, refresh, clear"),
    ] = "show",
) -> None:
    """View and manage project context."""
    async def _context():
        agent = await get_agent()

        if action == "show":
            status = await agent.get_status()

            table = Table(title="Project Context")
            table.add_column("Source", style="cyan")
            table.add_column("Details", style="dim")

            table.add_row("Project Root", status["project_root"])
            table.add_row("Provider", status["config"]["provider"])
            table.add_row("Mode", "Single" if status["config"]["single_model"] else "Multi-model orchestration")

            if status.get("git"):
                git = status["git"]
                table.add_row("Git Branch", git["branch"])
                table.add_row("Git Status", "Clean" if git["clean"] else "Modified")

            if status.get("memory"):
                mem = status["memory"]
                table.add_row("Memory Entries", str(mem["total_entries"]))

            if status.get("rag"):
                rag = status["rag"]
                table.add_row("RAG Documents", str(rag.get("total_documents", 0)))
                table.add_row("RAG Chunks", str(rag.get("total_chunks", 0)))

            console.print(table)

        elif action == "refresh":
            agent.context_collector.invalidate_cache()
            await agent.context_collector.collect_full()
            console.print("[green]✓ Context refreshed[/green]")

        elif action == "clear":
            agent.context_collector.invalidate_cache()
            console.print("[green]✓ Context cleared[/green]")

        else:
            console.print(f"[red]Unknown action: {action}[/red]")
            raise typer.Exit(1)

    asyncio.run(_context())


@app.command()
def status() -> None:
    """Show current project and agent status."""
    async def _status():
        agent = await get_agent()
        status = await agent.get_status()

        # Main status table
        table = Table(title="Co-Agent Status")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details", style="dim")

        table.add_row("Version", __version__, f"session: {status['session_id']}")
        table.add_row("Provider", status["config"]["provider"],
                      "single" if status["config"]["single_model"] else "orchestrated")
        table.add_row("Safety", status["config"]["approval_mode"],
                      str(status.get("safety", {})))

        if status.get("git"):
            g = status["git"]
            table.add_row("Git", f"branch: {g['branch']}",
                          f"{'clean' if g['clean'] else 'dirty'}, ahead={g['ahead']}, behind={g['behind']}")

        if status.get("memory"):
            m = status["memory"]
            table.add_row("Memory", f"{m['total_entries']} entries",
                          str(m.get("entries_by_type", {})))

        if status.get("plugins"):
            p = status["plugins"]
            table.add_row("Plugins", f"{p['active']} active",
                          "enabled" if p["enabled"] else "disabled")

        if status.get("rag"):
            r = status["rag"]
            table.add_row("RAG", f"{r.get('total_chunks', 0)} chunks",
                          r.get("embedding_model", "N/A"))

        console.print(table)

        # Provider health
        if status.get("providers"):
            console.print("\n[bold]Provider Health:[/bold]")
            for provider, health in status["providers"].items():
                icon = "✓" if health.get("healthy") else "✗"
                color = "green" if health.get("healthy") else "red"
                models = health.get("models", [])
                console.print(f"  [{color}]{icon} {provider}[/{color}] — {len(models)} models")

    asyncio.run(_status())


@app.command()
def config_cmd(
    action: Annotated[
        str,
        typer.Argument(help="Action: show, path, edit"),
    ] = "show",
) -> None:
    """View and manage coagent configuration."""
    config = load_config()

    if action == "show":
        import json
        console.print_json(json.dumps(config.model_dump(mode="json"), indent=2, default=str))
    elif action == "path":
        from terminal_ai_co_agent.config.loader import _find_config_file
        path = _find_config_file()
        if path:
            console.print(str(path))
        else:
            console.print("[yellow]No config file found — using defaults[/yellow]")
    elif action == "edit":
        from terminal_ai_co_agent.config.loader import _find_config_file
        path = _find_config_file()
        if path:
            console.print(f"Config file: {path}")
            console.print("[dim]Open this file in your editor to modify.[/dim]")
        else:
            console.print("[yellow]No config file found. Run 'coagent init' first.[/yellow]")


@app.command()
def plugin(
    action: Annotated[
        str,
        typer.Argument(help="Action: list, enable, disable"),
    ] = "list",
    plugin_name: Annotated[
        Optional[str],
        typer.Argument(help="Plugin name"),
    ] = None,
) -> None:
    """Manage coagent plugins."""
    async def _plugin():
        agent = await get_agent()
        mgr = agent.plugin_manager

        if mgr is None:
            console.print("[yellow]Plugin system is disabled[/yellow]")
            return

        if action == "list":
            plugins = mgr.get_status()
            if not plugins:
                console.print("[dim]No plugins discovered[/dim]")
                return

            table = Table(title="Plugins")
            table.add_column("Name", style="cyan")
            table.add_column("Status")
            table.add_column("Loaded")

            for p in plugins:
                status_color = {
                    "active": "green", "disabled": "red", "error": "red",
                    "discovered": "yellow", "loaded": "blue",
                }.get(p["status"], "white")

                table.add_row(
                    p["name"],
                    f"[{status_color}]{p['status']}[/{status_color}]",
                    "✓" if p["loaded"] else "—",
                )

            console.print(table)

        elif action == "enable" and plugin_name:
            await mgr.enable_plugin(plugin_name)
            console.print(f"[green]✓ Enabled plugin: {plugin_name}[/green]")

        elif action == "disable" and plugin_name:
            await mgr.disable_plugin(plugin_name)
            console.print(f"[yellow]Disabled plugin: {plugin_name}[/yellow]")

        else:
            console.print("[red]Invalid action or missing plugin name[/red]")

    asyncio.run(_plugin())


@app.command()
def analyze(
    target: Annotated[
        Optional[str],
        typer.Argument(help="Analysis type: static, dependency, security, all"),
    ] = "all",
) -> None:
    """Run code analysis on the project."""
    async def _analyze():
        agent = await get_agent()

        types = ["static", "dependency", "security"] if target == "all" else [target]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Analyzing...[/cyan]", total=None)
            result = await agent.analyze_project(types)
            progress.remove_task(task)

        for analysis_type, data in result.items():
            console.print(f"\n[bold cyan]{analysis_type.upper()} Analysis[/bold cyan]")
            console.print(f"Score: {data.get('score', 'N/A')}")

            if "top_issues" in data:
                for issue in data["top_issues"]:
                    console.print(f"  • {issue['file']}:{issue['line']} — {issue['message']}")

            if "issues" in data:
                for issue in data["issues"]:
                    sev_color = {"critical": "red", "error": "red", "warning": "yellow"}.get(
                        issue.get("severity", ""), "dim"
                    )
                    console.print(f"  [{sev_color}]• {issue['message']}[/{sev_color}]")

            if "critical" in data:
                console.print(f"  [red]Critical findings: {data['critical']}[/red]")

    asyncio.run(_analyze())


@app.command()
def test_gen(
    target: Annotated[
        Optional[str],
        typer.Argument(help="File or module to generate tests for"),
    ] = None,
) -> None:
    """Generate tests for specified target."""
    async def _test_gen():
        agent = await get_agent()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Generating tests...[/cyan]", total=None)
            result = await agent.generate_tests(target)
            progress.remove_task(task)

        if result["success"]:
            console.print("\n[green]✓ Tests generated[/green]")
            console.print(Markdown(result["tests"][:5000]))
            console.print(f"\n[dim]{result['tokens']} tokens used[/dim]")
        else:
            console.print("[red]✗ Test generation failed[/red]")

    asyncio.run(_test_gen())


@app.command()
def explain(
    target: Annotated[
        str,
        typer.Argument(help="File, function, or concept to explain"),
    ],
) -> None:
    """Explain code, architecture, or decisions."""
    async def _explain():
        agent = await get_agent()
        result = await agent.ask(
            f"Explain the following in detail. What does it do, how does it work, "
            f"and what design decisions are evident: {target}",
            use_rag=True,
        )

        if result["success"]:
            console.print(Markdown(result["response"]))
        else:
            console.print(f"[red]Error:[/red] {result.get('error', 'Unknown')}")

    asyncio.run(_explain())


# ── Cleanup ──────────────────────────────────────────────────────────

import atexit

@atexit.register
def _cleanup() -> None:
    """Cleanup agent on exit."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(shutdown_agent())
        else:
            loop.run_until_complete(shutdown_agent())
    except Exception:
        pass


# ── Entry Point ──────────────────────────────────────────────────────


def main_cli() -> None:
    """Entry point for the CLI application."""
    try:
        app()
    except typer.Exit:
        raise
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(130)
    except Exception as exc:
        logger.exception("cli.fatal_error", error=str(exc))
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main_cli()
