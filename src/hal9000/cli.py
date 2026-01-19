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


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with rich handler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, console=console)],
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config file",
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool, config: Optional[Path]) -> None:
    """HAL 9000 - AI-powered research assistant.

    Process PDFs, organize knowledge, and generate research contexts.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["config_path"] = config

    setup_logging(verbose)


@cli.command()
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option("--recursive/--no-recursive", default=True, help="Scan recursively")
@click.pass_context
def scan(ctx: click.Context, paths: tuple[Path, ...], recursive: bool) -> None:
    """Scan directories for PDF files.

    PATHS: One or more directories to scan (uses config defaults if not specified)
    """
    from hal9000.config import get_settings
    from hal9000.ingest import LocalScanner

    settings = get_settings()

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
    from hal9000.config import get_settings
    from hal9000.ingest import PDFProcessor, MetadataExtractor
    from hal9000.rlm import RLMProcessor
    from hal9000.categorize import Taxonomy, Classifier
    from hal9000.categorize.taxonomy import create_materials_science_taxonomy
    from hal9000.obsidian import VaultManager, NoteGenerator
    from hal9000.db.models import Document, init_db
    import json

    settings = get_settings()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Initialize database
        progress.add_task("Initializing database...", total=None)
        engine, SessionLocal = init_db(settings.database.url)
        session = SessionLocal()

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
        rlm_processor = RLMProcessor()
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
    from hal9000.config import get_settings
    from hal9000.ingest import LocalScanner, PDFProcessor, MetadataExtractor
    from hal9000.rlm import RLMProcessor
    from hal9000.categorize.taxonomy import create_materials_science_taxonomy
    from hal9000.categorize import Classifier
    from hal9000.adam import ContextBuilder

    settings = get_settings()

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
    rlm_processor = RLMProcessor()
    taxonomy = create_materials_science_taxonomy()
    classifier = Classifier(taxonomy)

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
@click.option("--vault-path", type=click.Path(path_type=Path), help="Override vault path")
@click.pass_context
def init_vault(ctx: click.Context, vault_path: Optional[Path]) -> None:
    """Initialize a new Obsidian vault for research."""
    from hal9000.config import get_settings
    from hal9000.obsidian import VaultManager

    settings = get_settings()
    path = vault_path or Path(settings.obsidian.vault_path)

    console.print(f"[bold]Initializing Obsidian vault at: {path}[/bold]")

    vault = VaultManager(path)
    vault.initialize()

    stats = vault.get_vault_stats()

    console.print(f"[green]Vault initialized successfully![/green]")
    console.print(f"  Papers folder: {vault.config.papers_folder}")
    console.print(f"  Concepts folder: {vault.config.concepts_folder}")
    console.print(f"  Topics folder: {vault.config.topics_folder}")


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show HAL 9000 status and statistics."""
    from hal9000.config import get_settings
    from hal9000.db.models import init_db, Document
    from hal9000.obsidian import VaultManager

    settings = get_settings()

    console.print("[bold]HAL 9000 Status[/bold]\n")

    # Config
    table = Table(title="Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Database", settings.database.url)
    table.add_row("Obsidian Vault", settings.obsidian.vault_path)
    table.add_row("ADAM Output", settings.adam.output_path)
    table.add_row("Log Level", settings.log_level)

    console.print(table)

    # Database stats
    try:
        engine, SessionLocal = init_db(settings.database.url)
        session = SessionLocal()
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


def main() -> None:
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
