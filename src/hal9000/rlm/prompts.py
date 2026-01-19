"""Prompt templates for RLM processing."""

# System prompt for document analysis
DOCUMENT_ANALYSIS_SYSTEM = """You are an expert research analyst specializing in materials science and scientific literature analysis. Your task is to analyze research documents and extract structured information.

You should identify:
1. Key topics and themes
2. Methodology and experimental approaches
3. Main findings and contributions
4. Relationships to other work in the field
5. Potential applications and implications

Be precise, factual, and cite specific details from the document when possible."""


# Prompt for extracting topics from a document chunk
TOPIC_EXTRACTION_PROMPT = """Analyze the following text from a research document and extract the main topics and themes.

TEXT CHUNK:
{chunk}

Provide your response as a JSON object with the following structure:
{{
    "primary_topics": ["topic1", "topic2", ...],
    "secondary_topics": ["topic1", "topic2", ...],
    "keywords": ["keyword1", "keyword2", ...],
    "research_domain": "the main research domain",
    "confidence": 0.0-1.0
}}

Focus on:
- Scientific concepts and phenomena
- Materials or compounds discussed
- Techniques and methods mentioned
- Applications and use cases

Respond ONLY with the JSON object, no additional text."""


# Prompt for generating document summary
SUMMARY_PROMPT = """Based on the following document content, generate a comprehensive summary.

DOCUMENT:
{document}

Provide a structured summary that includes:
1. **Main Objective**: What is the paper trying to achieve?
2. **Key Contributions**: What are the main contributions?
3. **Methodology**: What approach/methods were used?
4. **Key Findings**: What were the main results?
5. **Implications**: What are the broader implications?

Keep the summary concise but informative (300-500 words)."""


# Prompt for extracting methodology details
METHODOLOGY_PROMPT = """Analyze the methodology section of this research document.

TEXT:
{chunk}

Extract and structure the following:
{{
    "experimental_methods": ["method1", "method2", ...],
    "computational_methods": ["method1", "method2", ...],
    "materials_used": ["material1", "material2", ...],
    "equipment": ["equipment1", "equipment2", ...],
    "parameters": {{"param_name": "value", ...}},
    "novel_techniques": ["any new techniques introduced"]
}}

Respond ONLY with the JSON object."""


# Prompt for extracting key findings
FINDINGS_PROMPT = """Analyze the results and findings from this research document section.

TEXT:
{chunk}

Extract the key findings as a JSON object:
{{
    "quantitative_results": [
        {{"metric": "name", "value": "value", "context": "brief context"}}
    ],
    "qualitative_findings": ["finding1", "finding2", ...],
    "comparisons": ["comparison to prior work..."],
    "limitations": ["limitation1", ...],
    "unexpected_results": ["any surprising findings"]
}}

Respond ONLY with the JSON object."""


# Prompt for extracting relationships/citations
RELATIONSHIPS_PROMPT = """Analyze the following text for references to other work and relationships.

TEXT:
{chunk}

Identify:
{{
    "cited_works": [
        {{"authors": "...", "title_hint": "...", "relationship": "extends/contradicts/builds_on/compares"}}
    ],
    "related_concepts": ["concept1", "concept2"],
    "contrasts_with": ["what this work differs from"],
    "builds_upon": ["what foundational work this extends"]
}}

Respond ONLY with the JSON object."""


# Prompt for Materials Science specific analysis
MATERIALS_SCIENCE_PROMPT = """You are analyzing a materials science research document.

TEXT:
{chunk}

Extract materials science specific information:
{{
    "materials": [
        {{
            "name": "material name",
            "composition": "chemical composition if given",
            "properties": ["property1", "property2"],
            "synthesis_method": "how it was made",
            "application": "intended use"
        }}
    ],
    "characterization_techniques": ["XRD", "SEM", "etc."],
    "performance_metrics": [
        {{"metric": "name", "value": "value", "unit": "unit"}}
    ],
    "processing_conditions": {{"temperature": "...", "pressure": "...", "atmosphere": "..."}},
    "structure_property_relationships": ["relationship1", ...]
}}

Respond ONLY with the JSON object."""


# Prompt for aggregating chunk results
AGGREGATION_PROMPT = """You have analyzed a research document in chunks. Here are the results from each chunk:

{chunk_results}

Synthesize these into a unified analysis:
{{
    "title": "inferred document title",
    "primary_topics": ["top 5 most relevant topics"],
    "research_domain": "main domain",
    "summary": "300-word synthesis of the document",
    "key_findings": ["top 5 findings"],
    "methodology_summary": "brief methodology overview",
    "materials_focus": ["main materials if applicable"],
    "potential_applications": ["applications"],
    "relevance_to_adam": "how this relates to materials discovery and experiment design"
}}

Respond ONLY with the JSON object."""


# Prompt for generating ADAM context
ADAM_CONTEXT_PROMPT = """Based on the analyzed research documents, generate a research context for experimental design.

ANALYZED DOCUMENTS:
{documents_summary}

Generate an ADAM-compatible research context:
{{
    "topic_focus": "specific research topic",
    "literature_insights": {{
        "key_findings": ["finding1", "finding2", ...],
        "established_methods": ["method1", "method2", ...],
        "open_questions": ["question1", "question2", ...],
        "gaps_in_knowledge": ["gap1", "gap2", ...]
    }},
    "experiment_suggestions": [
        {{
            "hypothesis": "clear hypothesis statement",
            "methodology": "suggested experimental approach",
            "variables": {{
                "independent": ["var1", "var2"],
                "dependent": ["var1", "var2"],
                "controlled": ["var1", "var2"]
            }},
            "expected_outcomes": ["outcome1", "outcome2"],
            "rationale": "why this experiment based on literature",
            "priority": "high/medium/low",
            "confidence_score": 0.0-1.0
        }}
    ],
    "materials_of_interest": ["material1", "material2"],
    "recommended_characterization": ["technique1", "technique2"]
}}

Respond ONLY with the JSON object."""


# Prompt for hypothesis generation
HYPOTHESIS_PROMPT = """Based on the following research literature analysis, generate novel hypotheses for investigation.

LITERATURE ANALYSIS:
{analysis}

RESEARCH DOMAIN: {domain}
FOCUS AREA: {focus}

Generate hypotheses:
{{
    "hypotheses": [
        {{
            "statement": "clear hypothesis statement",
            "type": "exploratory/confirmatory/comparative",
            "basis": "literature basis for this hypothesis",
            "testability": "how this could be experimentally tested",
            "novelty": "what makes this hypothesis novel",
            "impact_if_confirmed": "potential impact",
            "confidence": 0.0-1.0
        }}
    ]
}}

Respond ONLY with the JSON object."""


def format_prompt(template: str, **kwargs) -> str:
    """Format a prompt template with provided values."""
    return template.format(**kwargs)
