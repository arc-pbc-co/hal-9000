"""Pytest configuration and shared fixtures for HAL 9000 tests."""

import tempfile
from pathlib import Path
from typing import Generator

import pytest


# Path to the test PDFs folder
TEST_PDF_FOLDER = Path(__file__).parent.parent / "research" / "01-superalloys-nickel-materials"


@pytest.fixture
def test_pdf_folder() -> Path:
    """Return path to test PDF folder."""
    return TEST_PDF_FOLDER


@pytest.fixture
def sample_pdf_path(test_pdf_folder: Path) -> Path:
    """Return path to a sample PDF for testing."""
    # Use the first PDF found in the test folder
    pdfs = list(test_pdf_folder.glob("*.pdf"))
    if not pdfs:
        pytest.skip("No PDFs found in test folder")
    return pdfs[0]


@pytest.fixture
def all_test_pdfs(test_pdf_folder: Path) -> list[Path]:
    """Return paths to all test PDFs."""
    return list(test_pdf_folder.glob("*.pdf"))


@pytest.fixture
def temp_directory() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_vault_path(temp_directory: Path) -> Path:
    """Return a temporary path for an Obsidian vault."""
    return temp_directory / "test_vault"


@pytest.fixture
def sample_document_text() -> str:
    """Return sample document text for testing."""
    return """
Abstract

This paper presents a comprehensive study of nickel-based superalloys for gas turbine applications.
We investigate the microstructural evolution and mechanical properties of Mar-M 247 and CM 247 LC
alloys under various processing conditions.

Introduction

Nickel-based superalloys are critical materials for high-temperature applications in aerospace
and power generation industries. These materials exhibit exceptional creep resistance, fatigue
properties, and oxidation resistance at elevated temperatures.

The development of single crystal superalloys has enabled significant improvements in turbine
efficiency and operating temperatures. Key strengthening mechanisms include gamma-prime (γ')
precipitation hardening and solid solution strengthening.

Methods

Samples were prepared using directional solidification (DS) and single crystal (SX) growth
techniques. Microstructural characterization was performed using:
- Scanning Electron Microscopy (SEM)
- X-ray Diffraction (XRD)
- Electron Probe Microanalysis (EPMA)

Mechanical testing included:
- Tensile testing at 25°C and 850°C
- Creep testing at 982°C/152 MPa
- Low cycle fatigue testing

Results

The single crystal samples exhibited superior creep resistance compared to directionally
solidified specimens. The creep rupture life at 982°C/152 MPa exceeded 500 hours for SX samples.

Microstructural analysis revealed a bimodal γ' distribution with primary γ' particles
(~400 nm) and secondary γ' (~50 nm). The volume fraction of γ' was approximately 65%.

Conclusion

This study demonstrates the superior high-temperature performance of single crystal
nickel-based superalloys. The optimized heat treatment produces a refined γ/γ' microstructure
that enhances creep resistance and mechanical properties.

Keywords: superalloys, nickel, creep, gamma-prime, single crystal, directional solidification

References

1. Reed, R.C. "The Superalloys: Fundamentals and Applications" (2006)
2. Pollock, T.M., Tin, S. "Nickel-Based Superalloys for Advanced Turbine Engines" (2006)
"""


@pytest.fixture
def sample_metadata_text() -> str:
    """Return sample text with metadata for testing extraction."""
    return """
High-Temperature Creep Behavior of Advanced Nickel-Based Superalloys

John Smith, Jane Doe, and Robert Johnson

Department of Materials Science and Engineering
Oak Ridge National Laboratory
Oak Ridge, TN 37831, USA

DOI: 10.1016/j.actamat.2024.001234

arXiv: 2401.12345v2

Abstract

This paper investigates the creep behavior of nickel-based superalloys...

Published in Acta Materialia, Volume 245, 2024

Copyright 2024 Elsevier Ltd. All rights reserved.
"""


@pytest.fixture
def sample_taxonomy_yaml(temp_directory: Path) -> Path:
    """Create a sample taxonomy YAML file for testing."""
    import yaml

    taxonomy_data = {
        "taxonomy": [
            {
                "name": "Superalloys",
                "slug": "superalloys",
                "description": "High-temperature alloys",
                "keywords": ["superalloy", "nickel", "creep", "turbine"],
                "children": [
                    {
                        "name": "Nickel-Based Superalloys",
                        "slug": "nickel-superalloys",
                        "keywords": ["nickel", "Inconel", "Waspaloy", "Mar-M"],
                    },
                    {
                        "name": "Cobalt-Based Superalloys",
                        "slug": "cobalt-superalloys",
                        "keywords": ["cobalt", "Stellite"],
                    },
                ],
            },
            {
                "name": "Additive Manufacturing",
                "slug": "additive-manufacturing",
                "keywords": ["3D printing", "AM", "SLM", "EBM"],
            },
        ]
    }

    yaml_path = temp_directory / "test_taxonomy.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(taxonomy_data, f)

    return yaml_path


@pytest.fixture
def mock_llm_response() -> dict:
    """Return a mock LLM response for testing RLM processor."""
    return {
        "primary_topics": ["nickel superalloys", "creep behavior", "gamma-prime"],
        "secondary_topics": ["turbine materials", "high temperature"],
        "keywords": ["superalloy", "nickel", "creep", "SX", "DS"],
        "research_domain": "materials_science",
        "confidence": 0.9,
    }


@pytest.fixture
def mock_document_analysis():
    """Return a mock DocumentAnalysis for testing."""
    from hal9000.rlm.processor import DocumentAnalysis

    return DocumentAnalysis(
        title="Test Paper on Superalloys",
        primary_topics=["nickel superalloys", "creep resistance"],
        secondary_topics=["turbine materials"],
        keywords=["superalloy", "nickel", "creep", "gamma-prime"],
        research_domain="materials_science",
        summary="A study on nickel-based superalloys for high-temperature applications.",
        key_findings=[
            "Single crystal samples showed superior creep resistance",
            "Gamma-prime volume fraction of 65% was optimal",
        ],
        methodology_summary="SEM, XRD, and mechanical testing were used.",
        materials=[
            {"name": "Mar-M 247", "composition": "Ni-based", "properties": ["high creep resistance"]},
            {"name": "CM 247 LC", "composition": "Ni-based", "properties": ["low carbon"]},
        ],
        potential_applications=["gas turbines", "aerospace"],
        chunks_processed=3,
        total_chunks=3,
    )
