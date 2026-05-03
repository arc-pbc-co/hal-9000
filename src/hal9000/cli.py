"""HAL 9000 Command Line Interface."""

import logging
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()
SUPPORTED_ACQUISITION_SOURCES = {"semantic_scholar", "arxiv"}


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with rich handler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, console=console)],
    )


def _get_settings_from_context(ctx: click.Context):
    """Load settings honoring the CLI config path."""
    from hal9000.config import get_settings

    config_path = ctx.obj.get("config_path") if ctx.obj else None
    profile = ctx.obj.get("profile") if ctx.obj else None
    return get_settings(config_file=config_path, environment=profile)


def _build_rlm_processor(settings):
    """Create an RLM processor from settings."""
    from hal9000.rlm import RLMProcessor

    return RLMProcessor(
        api_key=settings.anthropic_api_key,
        chunk_size=settings.processing.chunk_size,
        max_concurrent_calls=settings.processing.max_concurrent_calls,
    )


def _parse_sources_option(raw_sources: str) -> list[str]:
    """Parse and validate `--sources` values."""
    sources = [source.strip().lower() for source in raw_sources.split(",") if source.strip()]
    if not sources:
        raise click.BadParameter("At least one source must be provided", param_hint="--sources")

    invalid_sources = [source for source in sources if source not in SUPPORTED_ACQUISITION_SOURCES]
    if invalid_sources:
        supported = ", ".join(sorted(SUPPORTED_ACQUISITION_SOURCES))
        invalid = ", ".join(sorted(invalid_sources))
        raise click.BadParameter(
            f"Unsupported source(s): {invalid}. Supported values: {supported}",
            param_hint="--sources",
        )
    return sources


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config file",
)
@click.option(
    "--profile",
    type=click.Choice(["local", "staging", "production"]),
    help="Environment profile to load",
)
@click.pass_context
def cli(
    ctx: click.Context,
    verbose: bool,
    config: Optional[Path],
    profile: Optional[str],
) -> None:
    """HAL 9000 - AI-powered research assistant.

    Process PDFs, organize knowledge, and generate research contexts.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["config_path"] = config
    ctx.obj["profile"] = profile

    setup_logging(verbose)
    _get_settings_from_context(ctx)


@cli.command()
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option("--recursive/--no-recursive", default=True, help="Scan recursively")
@click.pass_context
def scan(ctx: click.Context, paths: tuple[Path, ...], recursive: bool) -> None:
    """Scan directories for PDF files.

    PATHS: One or more directories to scan (uses config defaults if not specified)
    """
    from hal9000.ingest import LocalScanner

    settings = _get_settings_from_context(ctx)

    # Use provided paths or defaults
    if paths:
        scan_paths = list(paths)
    else:
        scan_paths = settings.get_local_paths()

    console.print(f"[bold]Scanning {len(scan_paths)} path(s)...[/bold]")

    scanner = LocalScanner(scan_paths, recursive=recursive)
    stats = scanner.get_stats()

    table = Table(title="Scan Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total PDFs Found", str(stats["total_files"]))
    table.add_row("Total Size", f"{stats['total_size_mb']} MB")
    table.add_row("Paths Configured", str(stats["paths_configured"]))
    table.add_row("Valid Paths", str(stats["paths_valid"]))

    console.print(table)


@cli.command()
@click.argument("pdf_path", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output JSON path")
@click.option("--no-obsidian", is_flag=True, help="Skip Obsidian note creation")
@click.pass_context
def process(
    ctx: click.Context,
    pdf_path: Path,
    output: Optional[Path],
    no_obsidian: bool,
) -> None:
    """Process a single PDF document.

    PDF_PATH: Path to the PDF file to process
    """
    import json

    from hal9000.categorize import Classifier
    from hal9000.categorize.taxonomy import create_materials_science_taxonomy
    from hal9000.db.models import Document, init_db
    from hal9000.ingest import MetadataExtractor, PDFProcessor
    from hal9000.obsidian import NoteGenerator, VaultManager

    settings = _get_settings_from_context(ctx)
    _, session_local = init_db(settings.database.url)
    session = session_local()

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Initialize database
            progress.add_task("Initializing database...", total=None)

            # Step 1: Extract PDF content
            task = progress.add_task("Extracting PDF content...", total=None)
            pdf_processor = PDFProcessor()
            pdf_content = pdf_processor.extract_text(pdf_path)
            progress.update(task, completed=True)

            console.print(f"  Extracted {pdf_content.page_count} pages, {pdf_content.char_count} chars")

            # Step 2: Extract metadata
            task = progress.add_task("Extracting metadata...", total=None)
            metadata_extractor = MetadataExtractor()
            metadata = metadata_extractor.extract(pdf_content.full_text, pdf_content.metadata)
            progress.update(task, completed=True)

            if metadata.title:
                console.print(f"  Title: {metadata.title}")
            if metadata.authors:
                console.print(f"  Authors: {', '.join(metadata.authors[:3])}")

            # Step 3: RLM Processing
            task = progress.add_task("Analyzing document with RLM...", total=None)
            rlm_processor = _build_rlm_processor(settings)
            analysis = rlm_processor.process_document(pdf_content.full_text)
            progress.update(task, completed=True)

            console.print(f"  Topics: {', '.join(analysis.primary_topics[:5])}")

            # Step 4: Classify
            task = progress.add_task("Classifying document...", total=None)
            taxonomy = create_materials_science_taxonomy()
            classifier = Classifier(taxonomy)
            classification = classifier.classify(analysis)
            progress.update(task, completed=True)

            console.print(f"  Categories: {classification.suggested_folder_path}")

            # Step 5: Create database record
            document = Document(
                source_path=str(pdf_path),
                source_type="local",
                file_hash=pdf_content.file_hash,
                title=metadata.title or analysis.title,
                authors=json.dumps(metadata.authors),
                year=metadata.year,
                doi=metadata.doi,
                abstract=metadata.abstract,
                summary=analysis.summary,
                key_concepts=json.dumps(analysis.keywords),
                full_text=pdf_content.full_text[:100000],  # Truncate for DB
                page_count=pdf_content.page_count,
                status="completed",
            )
            session.add(document)
            session.commit()

            # Step 6: Create Obsidian note
            if not no_obsidian:
                task = progress.add_task("Creating Obsidian note...", total=None)
                vault = VaultManager(settings.obsidian.vault_path)
                vault.initialize()

                note_generator = NoteGenerator(vault)
                note = note_generator.generate_paper_note(
                    document, metadata, analysis, classification
                )
                note_generator.write_note(note)
                progress.update(task, completed=True)

                console.print(f"  Note created: {note.path.name}")

            # Output results
            if output:
                result = {
                    "document_id": document.id,
                    "title": metadata.title or analysis.title,
                    "metadata": metadata.to_dict(),
                    "analysis": analysis.to_dict(),
                    "classification": {
                        "topics": classification.topic_slugs,
                        "folder_path": classification.suggested_folder_path,
                    },
                }
                with open(output, "w") as f:
                    json.dump(result, f, indent=2)
                console.print(f"\n[green]Results saved to: {output}[/green]")
    finally:
        session.close()

    console.print("\n[bold green]Processing complete![/bold green]")


@cli.command()
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option("--limit", "-n", default=10, help="Maximum PDFs to process")
@click.option("--context-name", "-c", default="research_context", help="Name for ADAM context")
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), help="Output directory")
@click.pass_context
def batch(
    ctx: click.Context,
    paths: tuple[Path, ...],
    limit: int,
    context_name: str,
    output_dir: Optional[Path],
) -> None:
    """Process multiple PDFs and generate ADAM context.

    PATHS: Directories containing PDFs to process
    """
    from hal9000.adam import ContextBuilder
    from hal9000.ingest import LocalScanner, MetadataExtractor, PDFProcessor

    settings = _get_settings_from_context(ctx)

    if paths:
        scan_paths = list(paths)
    else:
        scan_paths = settings.get_local_paths()

    output_dir = output_dir or Path(settings.adam.output_path)

    console.print(f"[bold]Processing PDFs from {len(scan_paths)} path(s)...[/bold]")

    # Scan for PDFs
    scanner = LocalScanner(scan_paths)
    pdf_files = list(scanner.scan())[:limit]

    if not pdf_files:
        console.print("[yellow]No PDF files found.[/yellow]")
        return

    console.print(f"Found {len(pdf_files)} PDFs (processing up to {limit})")

    # Process each PDF
    pdf_processor = PDFProcessor()
    metadata_extractor = MetadataExtractor()
    rlm_processor = _build_rlm_processor(settings)

    analyses = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for i, discovered in enumerate(pdf_files):
            task = progress.add_task(
                f"Processing [{i+1}/{len(pdf_files)}]: {discovered.path.name[:40]}...",
                total=None,
            )

            try:
                # Extract content
                pdf_content = pdf_processor.extract_text(discovered.path)

                # Extract metadata
                metadata = metadata_extractor.extract(
                    pdf_content.full_text, pdf_content.metadata
                )

                # Analyze with RLM
                analysis = rlm_processor.process_document(pdf_content.full_text)

                # Store title from metadata if available
                if not analysis.title and metadata.title:
                    analysis.title = metadata.title

                analyses.append(analysis)
                progress.update(task, completed=True)

            except Exception as e:
                console.print(f"[red]Error processing {discovered.path.name}: {e}[/red]")
                progress.update(task, completed=True)

    console.print(f"\n[green]Successfully processed {len(analyses)} documents[/green]")

    # Build ADAM context
    if analyses:
        console.print("\n[bold]Generating ADAM research context...[/bold]")

        context_builder = ContextBuilder(processor=rlm_processor)
        context = context_builder.build_context(
            analyses,
            name=context_name,
            generate_experiments=True,
        )

        # Save context
        output_path = context_builder.save_context(context, output_dir)

        console.print(f"\n[bold green]ADAM context saved to: {output_path}[/bold green]")

        # Show summary
        table = Table(title="Context Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Context ID", context.context_id[:8])
        table.add_row("Papers Analyzed", str(context.literature_summary.papers_analyzed))
        table.add_row("Key Findings", str(len(context.literature_summary.key_findings)))
        table.add_row("Experiment Suggestions", str(len(context.experiment_suggestions)))
        table.add_row("Materials Identified", str(len(context.materials_of_interest)))
        table.add_row("Knowledge Graph Nodes", str(len(context.nodes)))

        console.print(table)


@cli.command()
@click.argument("topic")
@click.option("--max-papers", "-n", default=20, help="Maximum papers to acquire")
@click.option(
    "--sources",
    "-s",
    default="semantic_scholar,arxiv",
    help="Comma-separated list of sources (semantic_scholar, arxiv)",
)
@click.option("--no-process", is_flag=True, help="Skip RLM processing after download")
@click.option("--no-notes", is_flag=True, help="Skip Obsidian note generation")
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), help="Override download directory")
@click.option("--dry-run", is_flag=True, help="Search only, don't download")
@click.option("--threshold", "-t", default=0.5, help="Minimum relevance score (0-1)")
@click.pass_context
def acquire(
    ctx: click.Context,
    topic: str,
    max_papers: int,
    sources: str,
    no_process: bool,
    no_notes: bool,
    output_dir: Optional[Path],
    dry_run: bool,
    threshold: float,
) -> None:
    """Acquire research papers on a topic.

    TOPIC: Research topic to search for papers on

    \b
    Examples:
        hal acquire "nickel superalloys creep resistance"
        hal acquire "battery cathode materials" --max-papers 50
        hal acquire "machine learning" --sources arxiv --dry-run
    """
    import asyncio

    from hal9000.db.models import init_db

    settings = _get_settings_from_context(ctx)
    selected_sources = _parse_sources_option(sources)

    # Override download dir if specified
    if output_dir:
        settings.acquisition.download_dir = str(output_dir)

    console.print(f"[bold]Acquiring papers on: {topic}[/bold]\n")

    # Initialize database
    _, session_local = init_db(settings.database.url)
    session = session_local()

    # Import acquisition components
    from hal9000.acquisition import AcquisitionOrchestrator
    from hal9000.ingest import PDFProcessor
    from hal9000.obsidian import VaultManager
    # Initialize processors if processing is enabled
    pdf_processor = None
    rlm_processor = None
    vault_manager = None

    if not no_process:
        pdf_processor = PDFProcessor()
        rlm_processor = _build_rlm_processor(settings)

    if not no_notes:
        vault_manager = VaultManager(settings.obsidian.vault_path)
        vault_manager.initialize()

    # Create orchestrator
    orchestrator = AcquisitionOrchestrator(
        settings=settings,
        db_session=session,
        pdf_processor=pdf_processor,
        rlm_processor=rlm_processor,
        vault_manager=vault_manager,
    )

    async def run_acquisition():
        if dry_run:
            # Dry run - just search and show results
            console.print("[yellow]Dry run mode - searching but not downloading[/yellow]\n")

            results = await orchestrator.acquire_dry_run(
                topic=topic,
                max_papers=max_papers,
                relevance_threshold=threshold,
                sources=selected_sources,
            )

            if not results:
                console.print("[yellow]No papers found matching the topic.[/yellow]")
                return

            # Display results
            table = Table(title=f"Papers Found ({len(results)})")
            table.add_column("#", style="dim", width=3)
            table.add_column("Title", style="cyan", max_width=50)
            table.add_column("Year", style="green", width=6)
            table.add_column("Source", style="magenta", width=12)
            table.add_column("PDF", style="green", width=4)
            table.add_column("Score", style="yellow", width=5)

            for i, result in enumerate(results[:max_papers], 1):
                title = result.title[:47] + "..." if len(result.title) > 50 else result.title
                year = str(result.year) if result.year else "-"
                has_pdf = "[green]Yes[/green]" if result.pdf_url else "[red]No[/red]"
                score = f"{result.relevance_score:.2f}"
                table.add_row(str(i), title, year, result.source, has_pdf, score)

            console.print(table)
            console.print("\n[dim]Use without --dry-run to download these papers[/dim]")

        else:
            # Full acquisition
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                current_task = None

                def progress_callback(stage: str, current: int, total: int):
                    nonlocal current_task
                    if current_task:
                        progress.update(current_task, completed=True)
                    current_task = progress.add_task(
                        f"{stage} [{current}/{total}]...", total=None
                    )

                result = await orchestrator.acquire(
                    topic=topic,
                    max_papers=max_papers,
                    sources=selected_sources,
                    process_papers=not no_process,
                    generate_notes=not no_notes,
                    relevance_threshold=threshold,
                    progress_callback=progress_callback,
                )

                if current_task:
                    progress.update(current_task, completed=True)

            # Display summary
            console.print("\n[bold green]Acquisition Complete![/bold green]\n")

            table = Table(title="Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Papers Found", str(result.papers_found))
            table.add_row("Papers Downloaded", str(result.papers_downloaded))
            table.add_row("Papers Processed", str(result.papers_processed))
            table.add_row("Duplicates Skipped", str(result.duplicates_skipped))
            table.add_row("Download Failures", str(result.download_failures))
            table.add_row("Session Directory", str(result.session_dir))

            console.print(table)

            if result.errors:
                console.print("\n[yellow]Errors encountered:[/yellow]")
                for error in result.errors[:5]:
                    console.print(f"  - {error}")

    # Run the async acquisition
    try:
        asyncio.run(run_acquisition())
    finally:
        session.close()


@cli.command()
@click.option("--topic", "-t", help="Filter by search topic")
@click.option("--status", "-s", help="Filter by status (pending, completed, failed)")
@click.option("--limit", "-n", default=20, help="Maximum records to show")
@click.pass_context
def acquisitions(
    ctx: click.Context,
    topic: Optional[str],
    status: Optional[str],
    limit: int,
) -> None:
    """List paper acquisition records.

    Shows history of paper acquisition sessions and their status.
    """
    from hal9000.db.models import AcquisitionRecord, init_db

    settings = _get_settings_from_context(ctx)

    # Initialize database
    _, session_local = init_db(settings.database.url)
    session = session_local()

    try:
        # Build query
        query = session.query(AcquisitionRecord)

        if topic:
            query = query.filter(AcquisitionRecord.search_topic.contains(topic))

        if status:
            query = query.filter(AcquisitionRecord.status == status)

        # Order by most recent first
        query = query.order_by(AcquisitionRecord.created_at.desc())

        records = query.limit(limit).all()

        if not records:
            console.print("[yellow]No acquisition records found.[/yellow]")
            return

        # Display table
        table = Table(title=f"Acquisition Records ({len(records)})")
        table.add_column("ID", style="dim", width=8)
        table.add_column("Topic", style="cyan", max_width=30)
        table.add_column("Title", style="white", max_width=35)
        table.add_column("Status", style="magenta", width=12)
        table.add_column("Source", style="green", width=10)
        table.add_column("Date", style="dim", width=12)

        for record in records:
            record_id = record.id[:8]
            topic_text = record.search_topic[:27] + "..." if len(record.search_topic) > 30 else record.search_topic
            title = (record.title[:32] + "...") if record.title and len(record.title) > 35 else (record.title or "-")
            date = record.created_at.strftime("%Y-%m-%d")

            # Color status
            status_text = record.status
            if record.status == "completed":
                status_text = f"[green]{record.status}[/green]"
            elif record.status == "failed":
                status_text = f"[red]{record.status}[/red]"
            elif record.status == "duplicate":
                status_text = f"[yellow]{record.status}[/yellow]"

            table.add_row(record_id, topic_text, title, status_text, record.provider, date)

        console.print(table)

        # Summary stats
        total = session.query(AcquisitionRecord).count()
        completed = session.query(AcquisitionRecord).filter(AcquisitionRecord.status == "completed").count()
        failed = session.query(AcquisitionRecord).filter(AcquisitionRecord.status == "failed").count()

        console.print(f"\n[dim]Total: {total} | Completed: {completed} | Failed: {failed}[/dim]")

    finally:
        session.close()


@cli.command()
@click.option("--vault-path", type=click.Path(path_type=Path), help="Override vault path")
@click.pass_context
def init_vault(ctx: click.Context, vault_path: Optional[Path]) -> None:
    """Initialize a new Obsidian vault for research."""
    from hal9000.obsidian import VaultManager

    settings = _get_settings_from_context(ctx)
    path = vault_path or Path(settings.obsidian.vault_path)

    console.print(f"[bold]Initializing Obsidian vault at: {path}[/bold]")

    vault = VaultManager(path)
    vault.initialize()

    console.print("[green]Vault initialized successfully![/green]")
    console.print(f"  Papers folder: {vault.config.papers_folder}")
    console.print(f"  Concepts folder: {vault.config.concepts_folder}")
    console.print(f"  Topics folder: {vault.config.topics_folder}")


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show HAL 9000 status and statistics."""
    from hal9000.db.models import Document, init_db
    from hal9000.obsidian import VaultManager

    settings = _get_settings_from_context(ctx)

    console.print("[bold]HAL 9000 Status[/bold]\n")

    # Config
    table = Table(title="Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Environment", settings.environment)
    table.add_row("Database", settings.database.url)
    table.add_row("Object Storage", settings.storage.backend)
    table.add_row("Vector Backend", settings.vector.backend)
    table.add_row("Obsidian Vault", settings.obsidian.vault_path)
    table.add_row("ADAM Output", settings.adam.output_path)
    table.add_row("Log Level", settings.log_level)

    console.print(table)
    readiness_issues = settings.profile_readiness_issues()
    if readiness_issues:
        console.print("\n[yellow]Profile readiness issues:[/yellow]")
        for issue in readiness_issues:
            console.print(f"  - {issue}")

    # Database stats
    try:
        _, session_local = init_db(settings.database.url)
        session = session_local()
        doc_count = session.query(Document).count()

        table = Table(title="Database")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Total Documents", str(doc_count))
        console.print(table)
        session.close()
    except Exception as e:
        console.print(f"[yellow]Database not initialized: {e}[/yellow]")

    # Vault stats
    try:
        vault = VaultManager(settings.obsidian.vault_path)
        if vault.vault_path.exists():
            stats = vault.get_vault_stats()
            table = Table(title="Obsidian Vault")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Papers", str(stats["papers"]))
            table.add_row("Concepts", str(stats["concepts"]))
            table.add_row("Topics", str(stats["topics"]))
            console.print(table)
        else:
            console.print("[yellow]Obsidian vault not initialized[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Could not read vault: {e}[/yellow]")


@cli.command()
@click.pass_context
def version(ctx: click.Context) -> None:
    """Show HAL 9000 version."""
    from hal9000 import __version__

    console.print(f"HAL 9000 v{__version__}")


# Gateway command group
@cli.group()
@click.pass_context
def gateway(ctx: click.Context) -> None:
    """Gateway server commands.

    Start and manage the WebSocket gateway server for real-time communication.
    """
    pass


@gateway.command("start")
@click.option("--host", "-h", default="127.0.0.1", help="Host address to bind to")
@click.option("--port", "-p", default=9000, type=int, help="Port number to listen on")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def gateway_start(ctx: click.Context, host: str, port: int, verbose: bool) -> None:
    """Start the WebSocket gateway server.

    The gateway server enables real-time communication with HAL-9000
    through WebSocket connections.

    \b
    Examples:
        hal gateway start
        hal gateway start --port 8080
        hal gateway start --host 0.0.0.0 --port 9000 --verbose
    """
    import asyncio

    from hal9000.gateway import HALGateway

    if verbose:
        setup_logging(verbose=True)

    # Show startup banner
    console.print("\n[bold blue]╔═══════════════════════════════════════════════════╗[/bold blue]")
    console.print("[bold blue]║[/bold blue]            [bold white]HAL-9000 Gateway Server[/bold white]               [bold blue]║[/bold blue]")
    console.print("[bold blue]╚═══════════════════════════════════════════════════╝[/bold blue]\n")

    console.print(f"[cyan]Starting server on[/cyan] [bold]ws://{host}:{port}[/bold]\n")
    console.print("[dim]Press Ctrl+C to stop the server[/dim]\n")

    # Create and run gateway
    gateway_server = HALGateway(host=host, port=port)

    try:
        asyncio.run(gateway_server.run_forever())
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutdown requested...[/yellow]")

    console.print("[green]Gateway server stopped.[/green]")


@cli.group()
@click.pass_context
def research(ctx: click.Context) -> None:
    """Research program commands."""
    pass


@research.command("init-program")
@click.argument("path", type=click.Path(path_type=Path))
@click.option("--name", default="HAL Research Program", help="Program name")
@click.option(
    "--objective",
    default="Run a bounded, source-backed research review.",
    help="Program objective",
)
@click.option("--owner", help="Program owner")
@click.option("--domain", default="materials_science", help="Research domain")
def research_init_program(
    path: Path,
    name: str,
    objective: str,
    owner: Optional[str],
    domain: str,
) -> None:
    """Create a starter autoresearch-style program.md file."""
    from hal9000.research import render_program_template

    if path.exists():
        raise click.ClickException(f"Refusing to overwrite existing file: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_program_template(
            name=name,
            objective=objective,
            owner=owner,
            domain=domain,
        )
    )
    console.print(f"[green]Research program created:[/green] {path}")


@research.command("validate-program")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def research_validate_program(path: Path) -> None:
    """Validate a research program Markdown file."""
    from pydantic import ValidationError

    from hal9000.research import ProgramParseError, load_program

    try:
        program = load_program(path)
    except (ProgramParseError, ValidationError) as exc:
        raise click.ClickException(str(exc)) from exc

    table = Table(title="Research Program")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Name", program.spec.name)
    table.add_row("Objective", program.spec.objective)
    table.add_row("Domain", program.spec.domain)
    table.add_row("Max Runtime", f"{program.spec.budget.max_runtime_minutes} minutes")
    table.add_row("Max Papers", str(program.spec.budget.max_papers))
    table.add_row("Outputs", ", ".join(program.spec.output_contract.required_outputs))
    console.print(table)
    console.print("[green]Research program is valid.[/green]")


@research.command("create-project")
@click.argument("slug")
@click.option("--name", help="Project display name")
@click.option("--owner", help="Project owner")
@click.option("--description", help="Project description")
@click.option("--visibility", default="firm", help="Project visibility")
@click.pass_context
def research_create_project(
    ctx: click.Context,
    slug: str,
    name: Optional[str],
    owner: Optional[str],
    description: Optional[str],
    visibility: str,
) -> None:
    """Create a shared research project."""
    from hal9000.db.models import init_db
    from hal9000.db.store import ResearchStore

    settings = _get_settings_from_context(ctx)
    _, session_local = init_db(settings.database.url)
    session = session_local()

    try:
        store = ResearchStore(session)
        if store.get_project_by_slug(slug):
            raise click.ClickException(f"Research project already exists: {slug}")

        project = store.create_project(
            name=name or slug.replace("-", " ").title(),
            slug=slug,
            owner=owner,
            description=description,
            visibility=visibility,
        )
        session.commit()
        console.print(f"[green]Research project created:[/green] {project.slug}")
        console.print(f"  id: {project.id}")
    finally:
        session.close()


@research.command("save-program")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--project-slug", help="Attach the program to a research project")
@click.pass_context
def research_save_program(
    ctx: click.Context,
    path: Path,
    project_slug: Optional[str],
) -> None:
    """Persist a validated research program into the shared store."""
    from pydantic import ValidationError

    from hal9000.db.models import init_db
    from hal9000.db.store import ResearchStore
    from hal9000.research import ProgramParseError, load_program

    try:
        program = load_program(path)
    except (ProgramParseError, ValidationError) as exc:
        raise click.ClickException(str(exc)) from exc

    settings = _get_settings_from_context(ctx)
    _, session_local = init_db(settings.database.url)
    session = session_local()

    try:
        store = ResearchStore(session)
        project = None
        if project_slug:
            project = store.get_project_by_slug(project_slug)
            if project is None:
                raise click.ClickException(f"Research project not found: {project_slug}")

        record = store.save_program(program, project=project)
        session.commit()
        console.print(f"[green]Research program saved:[/green] {record.name}")
        console.print(f"  id: {record.id}")
        if project:
            console.print(f"  project: {project.slug}")
    finally:
        session.close()


@research.command("bootstrap")
@click.option("--project-slug", default="firm-research", help="Project slug to create or reuse")
@click.option("--project-name", default="Firm Research", help="Project display name")
@click.option("--owner", help="Project/program owner")
@click.option(
    "--program-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("templates/research/programs"),
    help="Directory containing starter program Markdown files",
)
@click.pass_context
def research_bootstrap(
    ctx: click.Context,
    project_slug: str,
    project_name: str,
    owner: Optional[str],
    program_dir: Path,
) -> None:
    """Create or reuse the baseline firm project and starter programs."""
    from hal9000.db.models import ResearchProgramRecord, init_db
    from hal9000.db.store import ResearchStore
    from hal9000.research import load_program

    settings = _get_settings_from_context(ctx)
    _, session_local = init_db(settings.database.url)
    session = session_local()

    try:
        store = ResearchStore(session)
        project = store.get_project_by_slug(project_slug)
        project_created = project is None
        if project is None:
            project = store.create_project(
                name=project_name,
                slug=project_slug,
                owner=owner,
                description="Baseline shared project for firm-wide research programs.",
            )

        program_paths = sorted(program_dir.glob("*.md"))
        if not program_paths:
            raise click.ClickException(f"No starter programs found in {program_dir}")

        table = Table(title="Research Bootstrap")
        table.add_column("Program", style="cyan")
        table.add_column("Version", style="magenta")
        table.add_column("Status", style="green")
        table.add_column("ID")

        created = 0
        reused = 0
        for program_path in program_paths:
            program = load_program(program_path)
            existing = (
                session.query(ResearchProgramRecord)
                .filter_by(
                    project_id=project.id,
                    name=program.spec.name,
                    version=program.spec.version,
                )
                .one_or_none()
            )
            if existing:
                reused += 1
                table.add_row(existing.name, existing.version, "existing", existing.id)
                continue

            record = store.save_program(program, project=project)
            created += 1
            table.add_row(record.name, record.version, "created", record.id)

        session.commit()
        console.print("[green]Research bootstrap complete.[/green]")
        console.print(f"  project: {project.slug} ({'created' if project_created else 'existing'})")
        console.print(f"  programs_created: {created}")
        console.print(f"  programs_existing: {reused}")
        console.print(table)
    finally:
        session.close()


@research.command("queue-run")
@click.option("--objective", help="Run objective; defaults to the program objective when provided")
@click.option("--project-slug", help="Attach the run to a research project")
@click.option("--program-id", help="Attach the run to a saved research program")
@click.option("--initiated-by", help="User or agent queuing the run")
@click.pass_context
def research_queue_run(
    ctx: click.Context,
    objective: Optional[str],
    project_slug: Optional[str],
    program_id: Optional[str],
    initiated_by: Optional[str],
) -> None:
    """Queue a bounded research run record."""
    import json

    from hal9000.db.models import ResearchProgramRecord, init_db
    from hal9000.db.store import ResearchStore

    settings = _get_settings_from_context(ctx)
    _, session_local = init_db(settings.database.url)
    session = session_local()

    try:
        store = ResearchStore(session)

        project = None
        if project_slug:
            project = store.get_project_by_slug(project_slug)
            if project is None:
                raise click.ClickException(f"Research project not found: {project_slug}")

        program = None
        if program_id:
            program = session.get(ResearchProgramRecord, program_id)
            if program is None:
                raise click.ClickException(f"Research program not found: {program_id}")
            if project is None:
                project = program.project

        run_objective = objective or (program.objective if program else None)
        if not run_objective:
            raise click.ClickException("Provide --objective or --program-id")

        budget = None
        tool_policy = None
        if program:
            spec = json.loads(program.spec_json)
            budget = spec.get("budget")
            tool_policy = {"allowed_tools": spec.get("allowed_tools", [])}

        run = store.create_run(
            objective=run_objective,
            project=project,
            program=program,
            initiated_by=initiated_by,
            budget=budget,
            tool_policy=tool_policy,
        )
        store.append_run_event(
            run,
            event_type="run.queued",
            message="Research run queued.",
            actor=initiated_by,
            payload={"program_id": program.id if program else None},
        )
        session.commit()
        console.print("[green]Research run queued.[/green]")
        console.print(f"  id: {run.id}")
        console.print(f"  status: {run.status}")
    finally:
        session.close()


@research.command("runs")
@click.option("--status", help="Filter by run status")
@click.option("--project-slug", help="Filter by research project")
@click.option("--limit", default=20, type=int, help="Maximum runs to show")
@click.pass_context
def research_runs(
    ctx: click.Context,
    status: Optional[str],
    project_slug: Optional[str],
    limit: int,
) -> None:
    """List recent research runs."""
    from hal9000.db.models import init_db
    from hal9000.db.store import ResearchStore

    settings = _get_settings_from_context(ctx)
    _, session_local = init_db(settings.database.url)
    session = session_local()

    try:
        store = ResearchStore(session)
        project = None
        if project_slug:
            project = store.get_project_by_slug(project_slug)
            if project is None:
                raise click.ClickException(f"Research project not found: {project_slug}")

        runs = store.list_runs(status=status, project=project, limit=limit)
        table = Table(title="Research Runs")
        table.add_column("ID", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Project", style="blue")
        table.add_column("Program", style="magenta")
        table.add_column("Objective")

        for run in runs:
            table.add_row(
                run.id[:8],
                run.status,
                run.project.slug if run.project else "-",
                run.program.name if run.program else "-",
                run.objective[:70],
            )
        console.print(table)
    finally:
        session.close()


@research.command("run-log")
@click.argument("run_id")
@click.pass_context
def research_run_log(ctx: click.Context, run_id: str) -> None:
    """Show ordered events for a research run."""
    from hal9000.db.models import init_db
    from hal9000.db.store import ResearchStore

    settings = _get_settings_from_context(ctx)
    _, session_local = init_db(settings.database.url)
    session = session_local()

    try:
        store = ResearchStore(session)
        run = store.get_run(run_id)
        if run is None:
            raise click.ClickException(f"Research run not found: {run_id}")

        events = store.list_run_events(run)
        table = Table(title=f"Run Log: {run.id}")
        table.add_column("#", style="cyan", justify="right")
        table.add_column("Type", style="green")
        table.add_column("Actor", style="blue")
        table.add_column("Message")

        for event in events:
            table.add_row(
                str(event.sequence),
                event.event_type,
                event.actor or "-",
                event.message or "",
            )
        console.print(table)
    finally:
        session.close()


@research.command("run-summary")
@click.argument("run_id")
@click.option("--json", "as_json", is_flag=True, help="Emit the summary as JSON")
@click.pass_context
def research_run_summary(ctx: click.Context, run_id: str, as_json: bool) -> None:
    """Show reviewer-facing telemetry for a research run."""
    import json

    from hal9000.db.models import init_db
    from hal9000.db.store import ResearchStore
    from hal9000.research.telemetry import RunTelemetrySummarizer

    settings = _get_settings_from_context(ctx)
    _, session_local = init_db(settings.database.url)
    session = session_local()

    try:
        store = ResearchStore(session)
        run = store.get_run(run_id)
        if run is None:
            raise click.ClickException(f"Research run not found: {run_id}")

        summary = RunTelemetrySummarizer(store).summarize(run)
        if as_json:
            console.print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
            return

        _render_run_summary(summary)
    finally:
        session.close()


def _render_run_summary(summary) -> None:
    """Render a telemetry summary with compact review tables."""
    overview = Table(title=f"Run Summary: {summary.run_id}")
    overview.add_column("Field", style="cyan")
    overview.add_column("Value", style="green")
    overview.add_row("Status", summary.status)
    overview.add_row("Project", summary.project_slug or "-")
    overview.add_row("Program", summary.program_name or "-")
    overview.add_row("Initiated By", summary.initiated_by or "-")
    overview.add_row("Events", str(summary.event_count))
    overview.add_row("Tool Calls", str(summary.tool_call_count))
    overview.add_row("Chunks", str(summary.chunk_count))
    overview.add_row("Claims", str(summary.claim_count))
    overview.add_row("Objective", summary.objective)
    console.print(overview)

    budget = summary.budget
    budget_table = Table(title="Budget Usage")
    budget_table.add_column("Metric", style="cyan")
    budget_table.add_column("Used", justify="right", style="green")
    budget_table.add_column("Limit", justify="right", style="magenta")
    budget_table.add_column("State", style="yellow")
    budget_table.add_row(
        "Papers Found",
        str(budget.papers_found),
        str(budget.max_papers),
        "-",
    )
    budget_table.add_row(
        "Downloads",
        str(budget.papers_downloaded),
        str(budget.max_downloads),
        "exceeded" if budget.papers_downloaded > budget.max_downloads else "-",
    )
    budget_table.add_row(
        "Processed Papers",
        str(budget.papers_processed),
        str(budget.max_papers),
        "-",
    )
    budget_table.add_row(
        "LLM Calls",
        str(budget.llm_calls_used),
        str(budget.max_llm_calls),
        "exceeded" if budget.llm_calls_exceeded else "-",
    )
    budget_table.add_row(
        "Runtime",
        f"{budget.runtime_seconds}s",
        f"{budget.max_runtime_minutes}m",
        "exceeded" if budget.runtime_exceeded else "-",
    )
    console.print(budget_table)

    acquisition = summary.acquisition
    acquisition_table = Table(title="Acquisition")
    acquisition_table.add_column("Found", justify="right", style="cyan")
    acquisition_table.add_column("Downloaded", justify="right", style="green")
    acquisition_table.add_column("Processed", justify="right", style="green")
    acquisition_table.add_column("Skipped", justify="right", style="yellow")
    acquisition_table.add_column("Failed", justify="right", style="red")
    acquisition_table.add_row(
        str(acquisition.papers_found),
        str(acquisition.papers_downloaded),
        str(acquisition.papers_processed),
        str(acquisition.papers_skipped),
        str(acquisition.papers_failed),
    )
    console.print(acquisition_table)

    if acquisition.paper_events:
        paper_table = Table(title="Paper Outcomes")
        paper_table.add_column("Status", style="green")
        paper_table.add_column("Stage", style="cyan")
        paper_table.add_column("Source", style="blue")
        paper_table.add_column("Identifier", style="magenta")
        paper_table.add_column("Title")
        paper_table.add_column("Reason", style="yellow")
        for event in acquisition.paper_events[:20]:
            paper_table.add_row(
                event.status,
                event.stage or "-",
                event.source or "-",
                event.identifier or "-",
                (event.title or "-")[:80],
                event.reason or "-",
            )
        console.print(paper_table)
        if len(acquisition.paper_events) > 20:
            console.print(
                f"[dim]Showing 20 of {len(acquisition.paper_events)} paper outcome events.[/dim]"
            )

    tool_table = Table(title="Tool Calls")
    tool_table.add_column("#", justify="right", style="cyan")
    tool_table.add_column("Tool", style="green")
    tool_table.add_column("Status", style="magenta")
    tool_table.add_column("Actor", style="blue")
    tool_table.add_column("Error", style="red")
    for call in summary.tool_calls:
        tool_table.add_row(
            str(call.sequence),
            call.tool_name,
            call.status,
            call.actor or "-",
            call.error_message or "-",
        )
    console.print(tool_table)

    output_table = Table(title="Outputs")
    output_table.add_column("Type", style="cyan")
    output_table.add_column("Status", style="green")
    output_table.add_column("Format", style="magenta")
    output_table.add_column("Title")
    output_table.add_column("Artifact", style="blue")
    for output in summary.outputs:
        output_table.add_row(
            output.output_type,
            output.status,
            output.format,
            output.title,
            output.artifact_uri or "-",
        )
    console.print(output_table)

    if summary.warnings:
        console.print("\n[yellow]Warnings[/yellow]")
        for warning in summary.warnings:
            console.print(f"  - {warning}")

    console.print("\n[bold]Reviewer Notes[/bold]")
    for note in summary.reviewer_notes:
        console.print(f"  - {note}")


@research.command("review-run")
@click.argument("run_id")
@click.option(
    "--decision",
    required=True,
    type=click.Choice(["promote", "reject", "request-changes"]),
    help="Reviewer decision for all staged outputs on the run",
)
@click.option("--reviewer", help="Reviewer name or email")
@click.option("--rationale", help="Review rationale or requested changes")
@click.pass_context
def research_review_run(
    ctx: click.Context,
    run_id: str,
    decision: str,
    reviewer: Optional[str],
    rationale: Optional[str],
) -> None:
    """Promote, reject, or request changes for staged run outputs."""
    from hal9000.db.models import init_db
    from hal9000.db.store import ResearchStore

    settings = _get_settings_from_context(ctx)
    _, session_local = init_db(settings.database.url)
    session = session_local()

    try:
        store = ResearchStore(session)
        run = store.get_run(run_id)
        if run is None:
            raise click.ClickException(f"Research run not found: {run_id}")

        result = store.review_run_outputs(
            run,
            decision=decision,
            reviewer=reviewer,
            rationale=rationale,
        )
        session.commit()
        console.print("[green]Research run reviewed.[/green]")
        console.print(f"  id: {result.run.id}")
        console.print(f"  status: {result.run.status}")
        console.print(f"  outputs_reviewed: {len(result.decisions)}")
        console.print(f"  event: {result.event.event_type} #{result.event.sequence}")
    except Exception as exc:
        session.rollback()
        raise click.ClickException(str(exc)) from exc
    finally:
        session.close()


@research.command("search-chunks")
@click.argument("query_text")
@click.option("--project-slug", help="Limit search to chunks attached to runs in a project")
@click.option("--run-id", help="Limit search to chunks attached to a run")
@click.option("--limit", default=None, type=int, help="Maximum chunks to return")
@click.pass_context
def research_search_chunks(
    ctx: click.Context,
    query_text: str,
    project_slug: Optional[str],
    run_id: Optional[str],
    limit: Optional[int],
) -> None:
    """Search embedded document chunks semantically."""
    from hal9000.db.models import init_db
    from hal9000.db.store import ResearchStore
    from hal9000.vector import VectorRepository, create_embedding_provider

    settings = _get_settings_from_context(ctx)
    _, session_local = init_db(settings.database.url)
    session = session_local()

    try:
        store = ResearchStore(session)
        project_id = None
        if project_slug:
            project = store.get_project_by_slug(project_slug)
            if project is None:
                raise click.ClickException(f"Research project not found: {project_slug}")
            project_id = project.id

        provider = create_embedding_provider(
            settings.vector.embedding_provider,
            dimension=settings.vector.embedding_dimension,
            model=settings.vector.embedding_model,
        )
        repository = VectorRepository(session)
        results = repository.search_chunks(
            query_text=query_text,
            provider=provider,
            limit=limit or settings.vector.retrieval_limit,
            project_id=project_id,
            run_id=run_id,
        )

        table = Table(title="Semantic Chunk Search")
        table.add_column("Score", style="green", justify="right")
        table.add_column("Chunk", style="cyan")
        table.add_column("Source", style="blue")
        table.add_column("Content")

        for result in results:
            table.add_row(
                f"{result.score:.3f}",
                result.chunk_id[:8],
                result.document_title or result.document_id[:8],
                result.content[:120].replace("\n", " "),
            )
        console.print(table)
        if not results:
            console.print("[yellow]No embedded chunks matched the query.[/yellow]")
    finally:
        session.close()


def _parse_payload_json(raw_payload: Optional[str]) -> Optional[dict]:
    """Parse an optional JSON payload for research run CLI commands."""
    if not raw_payload:
        return None
    import json

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"Invalid JSON payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise click.BadParameter("Payload JSON must be an object")
    return payload


@research.command("log-run-event")
@click.argument("run_id")
@click.option("--event-type", required=True, help="Event type, e.g. tool.search")
@click.option("--message", help="Human-readable event message")
@click.option("--actor", help="User, worker, or agent responsible for the event")
@click.option("--payload-json", help="Optional JSON object payload")
@click.pass_context
def research_log_run_event(
    ctx: click.Context,
    run_id: str,
    event_type: str,
    message: Optional[str],
    actor: Optional[str],
    payload_json: Optional[str],
) -> None:
    """Append an event to a research run log."""
    from hal9000.db.models import init_db
    from hal9000.db.store import ResearchStore

    settings = _get_settings_from_context(ctx)
    _, session_local = init_db(settings.database.url)
    session = session_local()

    try:
        store = ResearchStore(session)
        run = store.get_run(run_id)
        if run is None:
            raise click.ClickException(f"Research run not found: {run_id}")

        event = store.append_run_event(
            run,
            event_type=event_type,
            message=message,
            actor=actor,
            payload=_parse_payload_json(payload_json),
        )
        session.commit()
        console.print(f"[green]Run event appended:[/green] {event.event_type} #{event.sequence}")
    finally:
        session.close()


@research.command("update-run")
@click.argument("run_id")
@click.option(
    "--status",
    required=True,
    type=click.Choice(
        [
            "queued",
            "running",
            "staged",
            "completed",
            "failed",
            "promoted",
            "rejected",
            "changes_requested",
            "cancel_requested",
            "cancelled",
        ]
    ),
    help="New run status",
)
@click.option("--message", help="Human-readable lifecycle message")
@click.option("--actor", help="User, worker, or agent responsible for the update")
@click.option("--payload-json", help="Optional JSON object payload")
@click.pass_context
def research_update_run(
    ctx: click.Context,
    run_id: str,
    status: str,
    message: Optional[str],
    actor: Optional[str],
    payload_json: Optional[str],
) -> None:
    """Advance a research run lifecycle state."""
    from hal9000.db.models import init_db
    from hal9000.db.store import ResearchStore

    settings = _get_settings_from_context(ctx)
    _, session_local = init_db(settings.database.url)
    session = session_local()

    try:
        store = ResearchStore(session)
        run = store.get_run(run_id)
        if run is None:
            raise click.ClickException(f"Research run not found: {run_id}")

        event = store.update_run_status(
            run,
            status=status,
            message=message,
            actor=actor,
            payload=_parse_payload_json(payload_json),
        )
        session.commit()
        console.print(f"[green]Research run updated:[/green] {run.id}")
        console.print(f"  status: {run.status}")
        console.print(f"  event: {event.event_type} #{event.sequence}")
    finally:
        session.close()


@research.command("cancel-run")
@click.argument("run_id")
@click.option("--actor", help="User or agent requesting cancellation")
@click.option("--reason", help="Cancellation reason")
@click.pass_context
def research_cancel_run(
    ctx: click.Context,
    run_id: str,
    actor: Optional[str],
    reason: Optional[str],
) -> None:
    """Request cancellation for a queued or running research run."""
    from hal9000.db.models import init_db
    from hal9000.db.store import ResearchStore

    settings = _get_settings_from_context(ctx)
    _, session_local = init_db(settings.database.url)
    session = session_local()

    try:
        store = ResearchStore(session)
        run = store.get_run(run_id)
        if run is None:
            raise click.ClickException(f"Research run not found: {run_id}")
        if run.status == "queued":
            status = "cancelled"
            message = reason or "Queued run cancelled before execution."
        elif run.status == "running":
            status = "cancel_requested"
            message = reason or "Run cancellation requested."
        else:
            raise click.ClickException(f"Cannot cancel run with status: {run.status}")

        event = store.update_run_status(
            run,
            status=status,
            message=message,
            actor=actor,
            payload={"reason": reason},
        )
        session.commit()
        console.print("[green]Research run cancellation recorded.[/green]")
        console.print(f"  id: {run.id}")
        console.print(f"  status: {run.status}")
        console.print(f"  event: {event.event_type} #{event.sequence}")
    finally:
        session.close()


def _build_research_worker(
    store,
    settings,
    session,
    actor: str,
    live_acquisition: bool,
    max_attempts: int,
    phase_timeout_seconds: Optional[float],
):
    """Build a configured bounded research worker for CLI commands."""
    from hal9000.research import BoundedResearchWorker, WorkerExecutionControls
    from hal9000.research.acquisition import LiveAcquisitionRunner
    from hal9000.research.pipeline import ResearchCorpusPipeline
    from hal9000.vector import create_embedding_provider

    retrieval_provider = create_embedding_provider(
        settings.vector.embedding_provider,
        dimension=settings.vector.embedding_dimension,
        model=settings.vector.embedding_model,
    )
    acquisition_runner = LiveAcquisitionRunner(settings, session) if live_acquisition else None
    return BoundedResearchWorker(
        store,
        actor=actor,
        retrieval_provider=retrieval_provider,
        retrieval_limit=settings.vector.retrieval_limit,
        corpus_pipeline=ResearchCorpusPipeline(
            store,
            embedding_provider=retrieval_provider,
            chunk_size=settings.processing.chunk_size,
        ),
        acquisition_runner=acquisition_runner,
        controls=WorkerExecutionControls(
            max_attempts=max_attempts,
            phase_timeout_seconds=phase_timeout_seconds,
        ),
    )


@research.command("execute-run")
@click.argument("run_id")
@click.option("--actor", default="hal-worker", help="Worker or agent name")
@click.option(
    "--live-acquisition/--no-live-acquisition",
    default=False,
    help="Allow the worker to search, download, and process new papers within budget",
)
@click.option("--max-attempts", default=1, type=int, help="Maximum attempts per worker phase")
@click.option(
    "--phase-timeout-seconds",
    type=float,
    help="Fail a worker phase if it exceeds this duration",
)
@click.pass_context
def research_execute_run(
    ctx: click.Context,
    run_id: str,
    actor: str,
    live_acquisition: bool,
    max_attempts: int,
    phase_timeout_seconds: Optional[float],
) -> None:
    """Execute a queued research run through the bounded worker."""
    from hal9000.db.models import init_db
    from hal9000.db.store import ResearchStore

    settings = _get_settings_from_context(ctx)
    _, session_local = init_db(settings.database.url)
    session = session_local()

    try:
        store = ResearchStore(session)
        worker = _build_research_worker(
            store,
            settings,
            session,
            actor,
            live_acquisition,
            max_attempts,
            phase_timeout_seconds,
        )
        result = worker.execute_run(run_id)
        session.commit()
        console.print("[green]Research run executed.[/green]")
        console.print(f"  id: {result.run.id}")
        console.print(f"  status: {result.run.status}")
        console.print(f"  outputs: {len(result.output_ids)}")
        console.print(f"  corpus_documents: {len(result.corpus_document_ids)}")
        console.print(f"  corpus_chunks: {len(result.corpus_chunk_ids)}")
        console.print(f"  corpus_claims: {len(result.corpus_claim_ids)}")
        console.print(f"  retrieved_context: {len(result.retrieval_context)}")
        if result.run_report_id:
            console.print(f"  run_report: {result.run_report_id}")
        if result.acquisition:
            console.print(f"  acquired_downloaded: {result.acquisition.papers_downloaded}")
            console.print(f"  acquired_processed: {result.acquisition.papers_processed}")
    except Exception as exc:
        session.commit()
        raise click.ClickException(str(exc)) from exc
    finally:
        session.close()


@research.command("work-queue")
@click.option("--limit", default=1, type=int, help="Maximum queued runs to execute")
@click.option("--actor", default="hal-queue-worker", help="Worker or agent name")
@click.option(
    "--live-acquisition/--no-live-acquisition",
    default=False,
    help="Allow queued runs to search, download, and process new papers within budget",
)
@click.option("--max-attempts", default=1, type=int, help="Maximum attempts per worker phase")
@click.option(
    "--phase-timeout-seconds",
    type=float,
    help="Fail a worker phase if it exceeds this duration",
)
@click.pass_context
def research_work_queue(
    ctx: click.Context,
    limit: int,
    actor: str,
    live_acquisition: bool,
    max_attempts: int,
    phase_timeout_seconds: Optional[float],
) -> None:
    """Execute queued research runs once for worker/scheduler deployments."""
    from hal9000.db.models import init_db
    from hal9000.db.store import ResearchStore
    from hal9000.research.queue import ResearchQueueRunner

    settings = _get_settings_from_context(ctx)
    _, session_local = init_db(settings.database.url)
    session = session_local()

    try:
        store = ResearchStore(session)

        def worker_factory(current_store):
            return _build_research_worker(
                current_store,
                settings,
                session,
                actor,
                live_acquisition,
                max_attempts,
                phase_timeout_seconds,
            )

        results = ResearchQueueRunner(store, worker_factory).run_once(limit=limit)
        session.commit()

        table = Table(title="Queued Worker Results")
        table.add_column("Run", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Result", style="magenta")
        table.add_column("Error", style="red")
        for result in results:
            table.add_row(
                result.run_id[:8],
                result.status,
                "succeeded" if result.succeeded else "failed",
                result.error or "-",
            )
        console.print(table)
        console.print(f"[green]Queued worker processed {len(results)} run(s).[/green]")
    except Exception as exc:
        session.commit()
        raise click.ClickException(str(exc)) from exc
    finally:
        session.close()


def main() -> None:
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
