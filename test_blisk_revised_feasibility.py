#!/usr/bin/env python3
"""
REVISED Production-Scale Analysis for HAL-9000
Metal Binder Jetting Blisk - 40,000 units in 12 months

Updated assumptions:
- 71 binder jet machines already acquired at $150K each
- Powder requirement reduced by 5x (240 MT vs 1,200 MT)
"""

import os
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

RESEARCH_PROBLEM = """
## REVISED FEASIBILITY ASSESSMENT: UPDATED CONSTRAINTS

**Objective**: Scale metal binder jetting (MBJ) to produce **40,000 eight-inch diameter blisks in 12 months**.

### CRITICAL UPDATED ASSUMPTIONS

**Equipment Already Secured**:
- **71 metal binder jet machines** already acquired
- Purchase price: $150K per machine (discounted from $1.5M - inventory liquidation)
- Total equipment investment to date: $10.65M
- Machines are available NOW (no lead time)

**Revised Powder Assessment**:
- Original estimate was 1,200 MT
- **Revised estimate: 240 MT** (5x reduction)
- Possible due to: higher yield assumptions, optimized powder recycling, reduced per-part usage

### Production Requirements (Unchanged)
- **Volume**: 40,000 blisks
- **Timeline**: 12 months
- **Implied rate**: ~3,333 blisks/month | ~111 blisks/day | ~4.6 blisks/hour

### Technical Specifications (Unchanged)
- Blisk diameter: 8 inches (~200mm)
- Rotational speed: 100,000 RPM
- Operating temperature: >980°C
- Material candidates: MAR-M 247, CM 247 LC, or novel AM-optimized alloys
- Critical requirement: Crack-free components

### Updated Analysis Required

Given these new constraints, reassess:

1. **Equipment Gap Analysis**:
   - Do 71 machines provide sufficient capacity?
   - What additional equipment is needed?
   - What is the realistic throughput with 71 machines?

2. **Powder Supply Reassessment**:
   - 240 MT requirement vs current global capacity
   - Feasibility of sourcing this volume
   - Supply chain risk with reduced requirement

3. **Revised Capital Requirements**:
   - Equipment already acquired: $10.65M
   - Remaining equipment needed
   - Total program cost vs original estimate

4. **Updated Risk Matrix**:
   - Re-score all risks with new assumptions
   - Identify which blockers are now mitigated
   - Which risks remain critical?

5. **Revised Feasibility Verdict**:
   - New probability of success
   - Remaining gaps to close
   - Path to feasibility if one exists

Be quantitative. Show the math on throughput and capacity gaps.
"""

def generate_revised_analysis():
    """Generate revised feasibility analysis with updated constraints."""

    client = Anthropic()

    print("=" * 80)
    print("HAL-9000 REVISED FEASIBILITY ANALYSIS")
    print("71 Machines Acquired | Powder Reduced 5x")
    print("=" * 80)
    print()

    system_prompt = """You are HAL-9000, an advanced AI consultant specializing in additive manufacturing scale-up and production feasibility.

The user has provided UPDATED CONSTRAINTS that significantly change the feasibility picture:
1. 71 binder jet machines already acquired at $150K each (massive discount)
2. Powder requirement reduced by 5x to 240 MT

Recalculate all feasibility metrics with these new numbers. Be rigorous with the math - show calculations for throughput, capacity utilization, and gaps.

Remain honest about remaining risks, but acknowledge where the updated assumptions improve the picture. If this is now more feasible, say so. If critical blockers remain, identify them clearly."""

    user_prompt = f"""Reassess this production program with updated constraints:

{RESEARCH_PROBLEM}

Provide a comprehensive REVISED analysis:

## 1. EQUIPMENT CAPACITY ANALYSIS

With 71 machines in hand:
- Calculate theoretical throughput (show math)
- Calculate realistic throughput with utilization factors
- Identify capacity gap (if any)
- Downstream equipment requirements (sintering, HIP, etc.)

## 2. POWDER SUPPLY REASSESSMENT

With 240 MT requirement (vs original 1,200 MT):
- Compare to global production capacity
- Assess sourcing feasibility
- Identify qualified or qualifiable suppliers
- Supply chain risk score

## 3. REVISED CAPITAL BUDGET

Update the capital requirements:
| Item | Original | Revised | Savings |
Show the full picture with equipment already secured.

## 4. UPDATED RISK MATRIX

Re-score all risks from the original assessment:
| Risk | Original Score | Revised Score | Change | Notes |

Which blockers are now mitigated? Which remain critical?

## 5. REMAINING CRITICAL GAPS

List the top 3-5 remaining issues that must be solved:
- Gap description
- Severity (1-5)
- Path to close
- Timeline to close

## 6. REVISED FEASIBILITY VERDICT

**New probability of success**: X%
**Comparison to original**: Improvement from Y% to X%

What would the program need to achieve to reach >50% success probability?
What would it need for >80%?

## 7. RECOMMENDED PATH FORWARD

Given the improved position:
- Go/No-Go recommendation
- Critical path items for first 90 days
- Decision gates and milestones
- Contingency triggers

Be specific and actionable.
"""

    print("Generating revised feasibility analysis...")
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
    output_file = "blisk_revised_feasibility.md"
    with open(output_file, "w") as f:
        f.write("# HAL-9000 REVISED Feasibility Analysis\n")
        f.write("## 40,000 Blisks | 71 Machines Acquired | Powder 5x Reduction\n\n")
        f.write("**Assessment Date**: 2026-02-04\n\n")
        f.write("**Key Changes from Original Assessment**:\n")
        f.write("- 71 binder jet machines already in hand ($150K each vs $1.5M)\n")
        f.write("- Powder requirement reduced from 1,200 MT to 240 MT\n\n")
        f.write("---\n\n")
        f.write(analysis)

    print()
    print("=" * 80)
    print(f"Revised analysis saved to: {output_file}")
    print("=" * 80)

    return analysis


if __name__ == "__main__":
    generate_revised_analysis()
