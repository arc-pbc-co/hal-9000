#!/usr/bin/env python3
"""
Test script for HAL-9000: Metal Binder Jetting Blisk Research Problem

CTO Test Case: Research problem for 8-inch blisk using MAR-M 247, CM 247,
or novel superalloy formulations for crack-free operation at 100,000 RPM
and >980°C.
"""

import asyncio
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

from hal9000.rlm import RLMProcessor
from hal9000.config import get_settings


RESEARCH_PROBLEM = """
You are a materials science research assistant helping with an advanced manufacturing challenge.

## Research Problem

We are investigating the use of **metal binder jetting (MBJ)** to additively manufacture an **8-inch diameter blisk** (bladed disk) for high-performance turbine applications.

### Requirements:
1. **Operating conditions**: 100,000 RPM rotational speed, operating temperatures exceeding 980°C
2. **Material candidates**:
   - MAR-M 247 (nickel-based superalloy)
   - CM 247 LC (low carbon variant)
   - Novel alloy formulations optimized for additive manufacturing
3. **Critical success metric**: Crack-free component after sintering and heat treatment

### Key Technical Challenges:
1. **Printability**: MAR-M 247 and CM 247 are notoriously difficult to process via AM due to:
   - High gamma prime (γ') content causing solidification cracking
   - Carbide formation and segregation
   - Residual stress accumulation

2. **Sintering**: Binder jetting requires sintering the green part, which can cause:
   - Grain growth affecting creep properties
   - Porosity from incomplete densification
   - Distortion from non-uniform shrinkage

3. **High-temperature performance**: The blisk must maintain:
   - Creep resistance at 980°C+
   - Fatigue strength under centrifugal loading
   - Oxidation resistance

### Research Questions:

1. What modifications to MAR-M 247 or CM 247 composition could improve binder jetting processability while maintaining high-temperature properties?

2. What sintering parameters (temperature profile, atmosphere, HIP post-processing) optimize densification while minimizing grain growth?

3. Are there novel nickel superalloy compositions specifically designed for binder jetting that could outperform traditional cast alloys in this application?

4. What non-destructive testing methods can verify crack-free status in complex blisk geometries?

5. What is the current state-of-the-art for binder jet printing of nickel superalloys for rotating turbine components?

Please provide a comprehensive analysis with:
- Summary of relevant prior research
- Recommended experimental approach
- Key process parameters to investigate
- Risk assessment for each material candidate
- Suggested novel alloy compositions worth investigating
"""


def test_rlm_processing():
    """Test the RLM processor with the blisk research problem."""
    print("=" * 70)
    print("HAL-9000 Test: Metal Binder Jetting Blisk Research")
    print("=" * 70)
    print()

    processor = RLMProcessor()

    print("Processing research problem through RLM...")
    print("-" * 70)

    try:
        result = processor.process_document(
            text=RESEARCH_PROBLEM,
            domain="materials_science",
            include_materials_analysis=True
        )

        print("\n" + "=" * 70)
        print("ANALYSIS RESULTS")
        print("=" * 70)

        if hasattr(result, 'summary'):
            print("\n### SUMMARY ###")
            print(result.summary)

        if hasattr(result, 'key_findings'):
            print("\n### KEY FINDINGS ###")
            for i, finding in enumerate(result.key_findings, 1):
                print(f"{i}. {finding}")

        if hasattr(result, 'methodology'):
            print("\n### METHODOLOGY ###")
            print(result.methodology)

        if hasattr(result, 'recommendations'):
            print("\n### RECOMMENDATIONS ###")
            for i, rec in enumerate(result.recommendations, 1):
                print(f"{i}. {rec}")

        if hasattr(result, 'raw_analysis'):
            print("\n### FULL ANALYSIS ###")
            print(result.raw_analysis)

        # Also print the full result object for inspection
        print("\n" + "=" * 70)
        print("RAW RESULT OBJECT")
        print("=" * 70)
        print(result)

        return result

    except Exception as e:
        print(f"Error during processing: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    result = test_rlm_processing()

    if result:
        print("\n" + "=" * 70)
        print("TEST COMPLETED SUCCESSFULLY")
        print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print("TEST FAILED")
        print("=" * 70)
