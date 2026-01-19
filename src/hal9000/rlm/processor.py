"""
Recursive Language Model (RLM) processor for document analysis.

Implements patterns from the RLM paper:
- Context as environment (documents stored externally, not in prompt)
- Chunking and sub-LM calls for long documents
- Result aggregation across chunks
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from anthropic import Anthropic

from hal9000.rlm.prompts import (
    DOCUMENT_ANALYSIS_SYSTEM,
    TOPIC_EXTRACTION_PROMPT,
    SUMMARY_PROMPT,
    METHODOLOGY_PROMPT,
    FINDINGS_PROMPT,
    MATERIALS_SCIENCE_PROMPT,
    AGGREGATION_PROMPT,
    format_prompt,
)

logger = logging.getLogger(__name__)


@dataclass
class ChunkResult:
    """Result from processing a single chunk."""

    chunk_index: int
    topics: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    methodology: dict = field(default_factory=dict)
    materials: list[dict] = field(default_factory=list)
    raw_response: Optional[str] = None
    error: Optional[str] = None


@dataclass
class DocumentAnalysis:
    """Complete analysis of a document."""

    title: Optional[str] = None
    primary_topics: list[str] = field(default_factory=list)
    secondary_topics: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    research_domain: Optional[str] = None
    summary: Optional[str] = None
    key_findings: list[str] = field(default_factory=list)
    methodology_summary: Optional[str] = None
    materials: list[dict] = field(default_factory=list)
    potential_applications: list[str] = field(default_factory=list)
    adam_relevance: Optional[str] = None

    # Processing metadata
    chunks_processed: int = 0
    total_chunks: int = 0
    processing_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "primary_topics": self.primary_topics,
            "secondary_topics": self.secondary_topics,
            "keywords": self.keywords,
            "research_domain": self.research_domain,
            "summary": self.summary,
            "key_findings": self.key_findings,
            "methodology_summary": self.methodology_summary,
            "materials": self.materials,
            "potential_applications": self.potential_applications,
            "adam_relevance": self.adam_relevance,
            "processing": {
                "chunks_processed": self.chunks_processed,
                "total_chunks": self.total_chunks,
                "errors": self.processing_errors,
            },
        }


class RLMProcessor:
    """
    Process documents using Recursive Language Model patterns.

    Key principles from the RLM paper:
    1. Don't feed long documents directly into prompts
    2. Store document as external "environment" variable
    3. Chunk and recursively process with sub-LM calls
    4. Aggregate results from chunks into final analysis
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
        chunk_size: int = 50000,
        chunk_overlap: int = 1000,
        max_concurrent_calls: int = 5,
    ):
        """
        Initialize the RLM processor.

        Args:
            api_key: Anthropic API key (uses env var if not provided)
            model: Model to use for processing
            chunk_size: Target characters per chunk
            chunk_overlap: Overlap between chunks
            max_concurrent_calls: Max parallel LLM calls
        """
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_concurrent_calls = max_concurrent_calls

    def process_document(
        self,
        text: str,
        domain: str = "materials_science",
        include_materials_analysis: bool = True,
    ) -> DocumentAnalysis:
        """
        Process a document using RLM pattern.

        Args:
            text: Full document text
            domain: Research domain for context
            include_materials_analysis: Whether to run materials-specific extraction

        Returns:
            DocumentAnalysis object with extracted information
        """
        # Step 1: Chunk the document (RLM pattern: treat as external environment)
        chunks = self._chunk_document(text)
        total_chunks = len(chunks)

        logger.info(f"Processing document: {len(text)} chars -> {total_chunks} chunks")

        # Step 2: Process each chunk with sub-LM calls
        chunk_results = []
        for i, chunk in enumerate(chunks):
            logger.debug(f"Processing chunk {i+1}/{total_chunks}")
            result = self._process_chunk(chunk, i, domain, include_materials_analysis)
            chunk_results.append(result)

        # Step 3: Aggregate results
        analysis = self._aggregate_results(chunk_results, domain)
        analysis.total_chunks = total_chunks
        analysis.chunks_processed = len([r for r in chunk_results if not r.error])

        return analysis

    def _chunk_document(self, text: str) -> list[str]:
        """Split document into chunks for processing."""
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        current_pos = 0

        while current_pos < len(text):
            end_pos = min(current_pos + self.chunk_size, len(text))

            # Find good break point
            if end_pos < len(text):
                break_pos = self._find_break_point(text, current_pos, end_pos)
                if break_pos > current_pos:
                    end_pos = break_pos

            chunk = text[current_pos:end_pos].strip()
            if chunk:
                chunks.append(chunk)

            # Move with overlap
            current_pos = end_pos - self.chunk_overlap if end_pos < len(text) else end_pos

        return chunks

    def _find_break_point(
        self, text: str, start: int, end: int, window: int = 2000
    ) -> int:
        """Find a good break point for chunking."""
        search_start = max(start, end - window)
        search_text = text[search_start:end]

        # Prefer paragraph breaks
        para_break = search_text.rfind("\n\n")
        if para_break != -1:
            return search_start + para_break + 2

        # Then sentence breaks
        for pattern in [". ", ".\n", "? ", "! "]:
            pos = search_text.rfind(pattern)
            if pos != -1:
                return search_start + pos + 2

        # Then any newline
        newline = search_text.rfind("\n")
        if newline != -1:
            return search_start + newline + 1

        return end

    def _process_chunk(
        self,
        chunk: str,
        chunk_index: int,
        domain: str,
        include_materials: bool,
    ) -> ChunkResult:
        """Process a single chunk with sub-LM calls."""
        result = ChunkResult(chunk_index=chunk_index)

        try:
            # Topic extraction
            topics_response = self._call_llm(
                format_prompt(TOPIC_EXTRACTION_PROMPT, chunk=chunk[:40000])
            )
            topics_data = self._parse_json_response(topics_response)

            if topics_data:
                result.topics = topics_data.get("primary_topics", [])
                result.keywords = topics_data.get("keywords", [])

            # Materials-specific analysis if requested
            if include_materials and domain == "materials_science":
                materials_response = self._call_llm(
                    format_prompt(MATERIALS_SCIENCE_PROMPT, chunk=chunk[:40000])
                )
                materials_data = self._parse_json_response(materials_response)

                if materials_data:
                    result.materials = materials_data.get("materials", [])
                    result.methodology = {
                        "techniques": materials_data.get("characterization_techniques", []),
                        "metrics": materials_data.get("performance_metrics", []),
                    }

            # Findings extraction
            findings_response = self._call_llm(
                format_prompt(FINDINGS_PROMPT, chunk=chunk[:40000])
            )
            findings_data = self._parse_json_response(findings_response)

            if findings_data:
                result.findings = findings_data.get("qualitative_findings", [])

            result.raw_response = topics_response

        except Exception as e:
            logger.error(f"Error processing chunk {chunk_index}: {e}")
            result.error = str(e)

        return result

    def _aggregate_results(
        self, chunk_results: list[ChunkResult], domain: str
    ) -> DocumentAnalysis:
        """Aggregate results from all chunks into unified analysis."""
        analysis = DocumentAnalysis()

        # Collect all topics, keywords, findings
        all_topics = []
        all_keywords = []
        all_findings = []
        all_materials = []

        for result in chunk_results:
            if result.error:
                analysis.processing_errors.append(f"Chunk {result.chunk_index}: {result.error}")
                continue

            all_topics.extend(result.topics)
            all_keywords.extend(result.keywords)
            all_findings.extend(result.findings)
            all_materials.extend(result.materials)

        # Deduplicate and rank by frequency
        analysis.primary_topics = self._rank_by_frequency(all_topics)[:10]
        analysis.keywords = self._rank_by_frequency(all_keywords)[:20]
        analysis.key_findings = self._deduplicate_list(all_findings)[:10]
        analysis.materials = all_materials[:20]  # Keep unique materials

        # Generate final aggregated summary using LLM
        if chunk_results:
            chunk_summaries = []
            for r in chunk_results:
                if not r.error:
                    chunk_summaries.append({
                        "chunk": r.chunk_index,
                        "topics": r.topics[:5],
                        "findings": r.findings[:3],
                        "materials": [m.get("name") for m in r.materials[:3]],
                    })

            try:
                aggregation_response = self._call_llm(
                    format_prompt(
                        AGGREGATION_PROMPT,
                        chunk_results=json.dumps(chunk_summaries, indent=2),
                    )
                )
                agg_data = self._parse_json_response(aggregation_response)

                if agg_data:
                    analysis.title = agg_data.get("title")
                    analysis.summary = agg_data.get("summary")
                    analysis.research_domain = agg_data.get("research_domain", domain)
                    analysis.methodology_summary = agg_data.get("methodology_summary")
                    analysis.potential_applications = agg_data.get("potential_applications", [])
                    analysis.adam_relevance = agg_data.get("relevance_to_adam")

                    # Use aggregated topics if they're better
                    if agg_data.get("primary_topics"):
                        analysis.primary_topics = agg_data["primary_topics"]

            except Exception as e:
                logger.error(f"Error in aggregation: {e}")
                analysis.processing_errors.append(f"Aggregation: {e}")

        return analysis

    def _call_llm(self, prompt: str, max_tokens: int = 4096) -> str:
        """Make an LLM call."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=DOCUMENT_ANALYSIS_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text

    def _parse_json_response(self, response: str) -> Optional[dict]:
        """Parse JSON from LLM response."""
        try:
            # Try direct parse first
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from response
        try:
            # Look for JSON object
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(response[start:end])
        except json.JSONDecodeError:
            pass

        logger.warning(f"Failed to parse JSON response: {response[:200]}...")
        return None

    def _rank_by_frequency(self, items: list[str]) -> list[str]:
        """Rank items by frequency and return unique list."""
        from collections import Counter

        # Normalize items
        normalized = [item.lower().strip() for item in items if item]
        counts = Counter(normalized)

        # Return original casing for most common items
        seen = set()
        ranked = []
        for item in items:
            key = item.lower().strip()
            if key and key not in seen:
                seen.add(key)
                ranked.append((item, counts[key]))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return [item for item, _ in ranked]

    def _deduplicate_list(self, items: list[str]) -> list[str]:
        """Remove duplicates while preserving order."""
        seen = set()
        result = []
        for item in items:
            key = item.lower().strip()
            if key and key not in seen:
                seen.add(key)
                result.append(item)
        return result

    def generate_summary(self, text: str, max_length: int = 500) -> str:
        """Generate a standalone summary of a document."""
        # For shorter documents, process directly
        if len(text) <= 100000:
            prompt = format_prompt(SUMMARY_PROMPT, document=text[:100000])
        else:
            # For longer documents, summarize chunks first
            chunks = self._chunk_document(text)
            chunk_summaries = []

            for i, chunk in enumerate(chunks[:5]):  # Limit to first 5 chunks
                mini_summary = self._call_llm(
                    f"Summarize this section in 2-3 sentences:\n\n{chunk[:30000]}",
                    max_tokens=500,
                )
                chunk_summaries.append(mini_summary)

            combined = "\n\n".join(chunk_summaries)
            prompt = format_prompt(SUMMARY_PROMPT, document=combined)

        return self._call_llm(prompt, max_tokens=max_length * 2)
