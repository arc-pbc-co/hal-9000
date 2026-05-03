"""Research program primitives for HAL 9000."""

from hal9000.research.orchestrator import (
    BoundedResearchWorker,
    RunCancelledError,
    RunExecutionResult,
    WorkerExecutionControls,
    WorkerPhaseTimeoutError,
)
from hal9000.research.outputs import ResearchOutputGenerator, StagedOutputs
from hal9000.research.program import (
    OutputContract,
    ProgramParseError,
    ResearchBudget,
    ResearchProgram,
    ResearchProgramSpec,
    load_program,
    render_program_template,
)

__all__ = [
    "BoundedResearchWorker",
    "OutputContract",
    "ProgramParseError",
    "ResearchBudget",
    "ResearchProgram",
    "ResearchProgramSpec",
    "ResearchOutputGenerator",
    "StagedOutputs",
    "RunCancelledError",
    "RunExecutionResult",
    "WorkerExecutionControls",
    "WorkerPhaseTimeoutError",
    "load_program",
    "render_program_template",
]
