#!/usr/bin/env python3
"""
Full Research Analysis Test for HAL-9000
Metal Binder Jetting Blisk Research Problem

Generates comprehensive research recommendations and experimental design.
"""

import os
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

RESEARCH_PROBLEM = """
## Research Problem Statement

**Objective**: Use metal binder jetting (MBJ) to additively manufacture an 8-inch diameter blisk (bladed disk) for high-performance gas turbine applications.

**Operating Requirements**:
- Rotational speed: 100,000 RPM
- Operating temperature: >980°C (service temperature)
- Environment: Oxidizing atmosphere, potential for hot corrosion

**Material Candidates**:
1. MAR-M 247 (standard nickel-based superalloy)
2. CM 247 LC (low carbon variant)
3. Novel alloy formulations optimized for additive manufacturing

**Critical Success Metric**: Crack-free component after complete processing (printing, debinding, sintering, HIP, heat treatment)

**Key Technical Challenges**:
1. MAR-M 247 and CM 247 contain ~60-65% γ' phase, making them susceptible to:
   - Solidification cracking during rapid cooling
   - Strain-age cracking during post-weld heat treatment
   - Liquation cracking in heat-affected zones

2. Binder jetting specific challenges:
   - Green part strength during handling
   - Debinding without causing defects
   - Achieving >99.5% theoretical density after sintering
   - Controlling grain growth during high-temperature sintering
   - Managing ~15-20% linear shrinkage uniformly

3. Performance requirements at temperature:
   - Creep rupture life >1000 hours at 980°C/150 MPa
   - Low cycle fatigue resistance under centrifugal loading
   - Oxidation resistance with minimal coating requirements

**Research Questions**:
1. Can MAR-M 247 or CM 247 LC be successfully processed via binder jetting to achieve crack-free 8-inch blisks?
2. What compositional modifications could improve processability?
3. What are optimal sintering parameters?
4. What NDT methods can reliably detect internal defects in complex blisk geometries?
5. How do mechanical properties of binder jet blisks compare to cast equivalents?
"""

def generate_full_analysis():
    """Generate comprehensive research analysis using Claude."""

    client = Anthropic()

    print("=" * 80)
    print("HAL-9000 FULL RESEARCH ANALYSIS")
    print("Metal Binder Jetting for 8-inch Superalloy Blisk")
    print("=" * 80)
    print()

    system_prompt = """You are HAL-9000, an advanced AI research assistant specializing in materials science and additive manufacturing. You have deep expertise in:

- Nickel-based superalloys and their metallurgy
- Metal binder jetting process parameters and optimization
- Turbine component design and performance requirements
- Experimental design for materials research
- Non-destructive testing methods

Provide thorough, technically detailed responses that would be useful for a research team planning actual experiments. Include specific numbers, parameters, and references to real alloy compositions and processing conditions where appropriate."""

    user_prompt = f"""Analyze this research problem and provide a comprehensive research plan:

{RESEARCH_PROBLEM}

Please provide:

## 1. LITERATURE SUMMARY
Summarize the current state-of-the-art for:
- Binder jetting of nickel superalloys
- Processing of MAR-M 247 and CM 247 via any AM method
- Novel superalloy compositions designed for AM

## 2. MATERIAL SELECTION ANALYSIS
For each candidate material (MAR-M 247, CM 247 LC, and potential novel compositions):
- Assess processability via binder jetting
- Identify specific risks and mitigation strategies
- Recommend compositional modifications if needed

## 3. EXPERIMENTAL DESIGN
Propose a phased experimental approach:
- Phase 1: Powder characterization and initial parameter development
- Phase 2: Small-scale trials and process optimization
- Phase 3: Full-scale blisk fabrication and testing

Include specific parameters to investigate.

## 4. PROCESS PARAMETER RECOMMENDATIONS
For binder jetting and post-processing:
- Printing parameters (layer thickness, binder saturation, etc.)
- Debinding schedule
- Sintering temperature profile and atmosphere
- HIP parameters
- Heat treatment schedule

## 5. CHARACTERIZATION AND TESTING PLAN
- Microstructural characterization methods
- Mechanical testing requirements
- NDT methods for crack detection
- Performance validation tests

## 6. NOVEL ALLOY COMPOSITIONS
Suggest 2-3 novel alloy compositions specifically designed for binder jetting that could meet the performance requirements. Include:
- Target composition (wt%)
- Rationale for modifications
- Expected benefits and tradeoffs

## 7. RISK ASSESSMENT
Create a risk matrix for each material candidate with:
- Key risks
- Likelihood (H/M/L)
- Impact (H/M/L)
- Mitigation strategies

## 8. RECOMMENDED PATH FORWARD
Provide your recommendation for the most promising approach and next steps.
"""

    print("Generating comprehensive analysis...")
    print("-" * 80)
    print()

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_prompt}
        ]
    )

    analysis = response.content[0].text

    print(analysis)

    # Save to file
    output_file = "blisk_research_analysis.md"
    with open(output_file, "w") as f:
        f.write("# HAL-9000 Research Analysis\n")
        f.write("## Metal Binder Jetting for 8-inch Superalloy Blisk\n\n")
        f.write("---\n\n")
        f.write(analysis)

    print()
    print("=" * 80)
    print(f"Analysis saved to: {output_file}")
    print("=" * 80)

    return analysis


if __name__ == "__main__":
    generate_full_analysis()
