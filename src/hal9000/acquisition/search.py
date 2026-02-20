"""Search engine for paper acquisition with Claude-powered query expansion."""

import asyncio
import inspect
import json
import logging
import time
from typing import Optional

from anthropic import Anthropic

from hal9000.acquisition.providers.base import BaseProvider, SearchResult

logger = logging.getLogger(__name__)


# Prompts for Claude integration
QUERY_EXPANSION_PROMPT = """Given a research topic, generate effective search queries for academic paper databases.

TOPIC: {topic}

Generate 3-5 search queries that would find relevant papers. Consider:
1. Technical synonyms and alternative terms
2. Specific subtopics within this area
3. Related methodologies and techniques
4. Key materials or systems mentioned

Return as JSON:
{{
    "queries": ["query1", "query2", ...],
    "suggested_keywords": ["keyword1", "keyword2", ...],
    "year_range": {{"start": year, "end": year}},
    "reasoning": "brief explanation of query strategy"
}}

Respond ONLY with the JSON object, no other text."""

RELEVANCE_SCORING_PROMPT = """Score the relevance of these paper abstracts to the research topic.

RESEARCH TOPIC: {topic}

PAPERS TO SCORE:
{papers}

For each paper, provide a relevance score from 0.0 to 1.0:
- 1.0: Directly addresses the topic, highly relevant
- 0.7-0.9: Closely related, significant overlap
- 0.4-0.6: Somewhat related, tangential connection
- 0.1-0.3: Loosely related, minor relevance
- 0.0: Not relevant

Return as JSON:
{{
    "scores": [
        {{"paper_index": 0, "score": 0.0, "reasoning": "brief explanation"}},
        ...
    ]
}}

Respond ONLY with the JSON object, no other text."""


class SearchEngine:
    """Orchestrates searches across multiple providers with Claude enhancement.

    Features:
    - Query expansion using Claude to generate effective search terms
    - Parallel search across multiple providers
    - Result merging and deduplication
    - Claude-based relevance scoring and filtering
    """

    def __init__(
        self,
        providers: list[BaseProvider],
        anthropic_api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        """Initialize the search engine.

        Args:
            providers: List of search providers to use
            anthropic_api_key: API key for Claude (optional, uses env if not provided)
            model: Claude model to use for query expansion
        """
        self.providers = providers
        self.model = model
        self._provider_last_request: dict[str, float] = {}
        self._provider_locks: dict[str, asyncio.Lock] = {}

        # Initialize Anthropic client if API key available
        self._anthropic: Optional[Anthropic] = None
        if anthropic_api_key:
            self._anthropic = Anthropic(api_key=anthropic_api_key)
        else:
            try:
                self._anthropic = Anthropic()  # Uses ANTHROPIC_API_KEY env
            except Exception:
                logger.warning("Anthropic API not configured, query expansion disabled")

    async def _get_provider_delay(self, provider: BaseProvider) -> float:
        """Resolve provider-specific request spacing safely."""
        get_delay = getattr(provider, "get_rate_limit_delay", None)
        if not callable(get_delay):
            return 0.0

        try:
            value = get_delay()
            if inspect.isawaitable(value):
                value = await value
            return max(float(value), 0.0)
        except Exception:
            return 0.0

    async def _wait_for_provider_rate_limit(self, provider: BaseProvider) -> None:
        """Respect provider request pacing across expanded query runs."""
        delay = await self._get_provider_delay(provider)
        if delay <= 0:
            return

        lock = self._provider_locks.setdefault(provider.name, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            last_request = self._provider_last_request.get(provider.name, 0.0)
            elapsed = now - last_request
            if elapsed < delay:
                await asyncio.sleep(delay - elapsed)
            self._provider_last_request[provider.name] = time.monotonic()

    async def expand_query(self, topic: str) -> dict:
        """Use Claude to generate effective search queries for a topic.

        Args:
            topic: Research topic

        Returns:
            Dictionary with queries, keywords, and reasoning
        """
        if not self._anthropic:
            # Fallback: just use the topic as-is
            return {
                "queries": [topic],
                "suggested_keywords": topic.split(),
                "year_range": None,
                "reasoning": "Query expansion unavailable",
            }

        try:
            prompt = QUERY_EXPANSION_PROMPT.format(topic=topic)

            response = self._anthropic.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse JSON response
            content = response.content[0].text.strip()
            # Handle potential markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            result = json.loads(content)
            logger.info(f"Query expansion: {len(result.get('queries', []))} queries generated")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse query expansion response: {e}")
            return {"queries": [topic], "suggested_keywords": [], "reasoning": "Parse error"}
        except Exception as e:
            logger.error(f"Query expansion failed: {e}")
            return {"queries": [topic], "suggested_keywords": [], "reasoning": str(e)}

    async def _search_provider(
        self, provider: BaseProvider, query: str, max_results: int
    ) -> list[SearchResult]:
        """Search a single provider with error handling.

        Args:
            provider: Provider to search
            query: Search query
            max_results: Maximum results to return

        Returns:
            List of SearchResults
        """
        try:
            await self._wait_for_provider_rate_limit(provider)
            results = await provider.search(query, max_results)
            return results
        except Exception as e:
            logger.error(f"Search failed for {provider.name}: {e}")
            return []

    def _deduplicate_results(self, results: list[SearchResult]) -> list[SearchResult]:
        """Remove duplicate results based on DOI/arXiv ID/title.

        Args:
            results: List of results to deduplicate

        Returns:
            Deduplicated list
        """
        seen_ids = set()
        seen_titles = set()
        unique = []

        for result in results:
            # Check DOI
            if result.doi:
                if result.doi in seen_ids:
                    continue
                seen_ids.add(result.doi)

            # Check arXiv ID
            if result.arxiv_id:
                if result.arxiv_id in seen_ids:
                    continue
                seen_ids.add(result.arxiv_id)

            # Check title (normalized)
            title_key = result.title.lower().strip()[:100]
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            unique.append(result)

        logger.info(f"Deduplication: {len(results)} -> {len(unique)} results")
        return unique

    def _select_providers(self, sources: Optional[list[str]] = None) -> list[BaseProvider]:
        """Select providers by source name.

        Args:
            sources: Optional provider names (e.g., ["semantic_scholar", "arxiv"])

        Returns:
            Selected providers, preserving original order.
        """
        if not sources:
            return self.providers

        requested = {source.strip().lower() for source in sources if source.strip()}
        selected = [provider for provider in self.providers if provider.name in requested]

        missing = requested - {provider.name for provider in selected}
        if missing:
            logger.warning(f"Requested sources not configured: {sorted(missing)}")

        return selected

    async def search(
        self,
        topic: str,
        max_results_per_provider: int = 30,
        expand_query: bool = True,
        sources: Optional[list[str]] = None,
    ) -> list[SearchResult]:
        """Search for papers across all providers.

        Args:
            topic: Research topic to search for
            max_results_per_provider: Maximum results per provider
            expand_query: Whether to use Claude for query expansion
            sources: Optional provider names to include

        Returns:
            Merged and deduplicated list of SearchResults
        """
        providers = self._select_providers(sources)
        if not providers:
            logger.warning("No providers selected; returning empty search results")
            return []

        # Expand query if enabled
        queries = [topic]
        if expand_query:
            expansion = await self.expand_query(topic)
            expanded_queries = expansion.get("queries", []) or []
            # Always keep the original topic as a baseline search query.
            deduped = [topic]
            for query in expanded_queries:
                if query and query not in deduped:
                    deduped.append(query)
            queries = deduped[:3]  # Keep query fan-out bounded

        all_results = []

        # Search each provider with each query
        for query in queries:
            tasks = [
                self._search_provider(provider, query, max_results_per_provider)
                for provider in providers
            ]

            # Run searches in parallel
            provider_results = await asyncio.gather(*tasks)

            for results in provider_results:
                all_results.extend(results)

        # Deduplicate
        unique_results = self._deduplicate_results(all_results)

        return unique_results

    async def score_relevance(
        self, results: list[SearchResult], topic: str, batch_size: int = 10
    ) -> list[SearchResult]:
        """Use Claude to score relevance of search results.

        Args:
            results: List of SearchResults to score
            topic: Original research topic
            batch_size: Number of papers to score in each API call

        Returns:
            Results with updated relevance_score, sorted by relevance
        """
        if not self._anthropic:
            # Without Claude, just return as-is
            return results

        scored_results = []

        # Process in batches
        for i in range(0, len(results), batch_size):
            batch = results[i : i + batch_size]

            # Format papers for the prompt
            papers_text = ""
            for j, result in enumerate(batch):
                abstract = result.abstract or "No abstract available"
                abstract = abstract[:500]  # Truncate long abstracts
                papers_text += f"\n[{j}] Title: {result.title}\nAbstract: {abstract}\n"

            try:
                prompt = RELEVANCE_SCORING_PROMPT.format(
                    topic=topic, papers=papers_text
                )

                response = self._anthropic.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    messages=[{"role": "user", "content": prompt}],
                )

                content = response.content[0].text.strip()
                # Handle markdown code blocks
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                    content = content.strip()

                scores_data = json.loads(content)

                # Apply scores to results
                for score_info in scores_data.get("scores", []):
                    idx = score_info.get("paper_index", 0)
                    if 0 <= idx < len(batch):
                        batch[idx].relevance_score = score_info.get("score", 0.5)

            except Exception as e:
                logger.error(f"Relevance scoring failed for batch: {e}")
                # Keep default scores

            scored_results.extend(batch)

        # Sort by relevance
        scored_results.sort(key=lambda x: x.relevance_score, reverse=True)

        return scored_results

    async def filter_by_relevance(
        self,
        results: list[SearchResult],
        topic: str,
        threshold: float = 0.5,
        max_results: int = 20,
    ) -> list[SearchResult]:
        """Score and filter results by relevance.

        Args:
            results: List of SearchResults to filter
            topic: Original research topic
            threshold: Minimum relevance score to keep
            max_results: Maximum number of results to return

        Returns:
            Filtered and sorted list of relevant results
        """
        # Score all results
        scored = await self.score_relevance(results, topic)

        # Filter by threshold
        filtered = [r for r in scored if r.relevance_score >= threshold]

        # Limit to max_results
        filtered = filtered[:max_results]

        logger.info(
            f"Relevance filtering: {len(results)} -> {len(filtered)} "
            f"(threshold={threshold})"
        )

        return filtered

    async def search_and_filter(
        self,
        topic: str,
        max_results: int = 20,
        relevance_threshold: float = 0.5,
        expand_query: bool = True,
        sources: Optional[list[str]] = None,
    ) -> list[SearchResult]:
        """Search for papers and filter by relevance.

        This is the main entry point combining search and filtering.

        Args:
            topic: Research topic to search for
            max_results: Maximum final results to return
            relevance_threshold: Minimum relevance score
            expand_query: Whether to use Claude for query expansion
            sources: Optional provider names to include

        Returns:
            Relevant and deduplicated search results
        """
        # Search across providers
        results = await self.search(
            topic,
            max_results_per_provider=50,  # Get more initially for filtering
            expand_query=expand_query,
            sources=sources,
        )

        if not results:
            return []

        # Filter by relevance
        filtered = await self.filter_by_relevance(
            results,
            topic,
            threshold=relevance_threshold,
            max_results=max_results,
        )

        return filtered
