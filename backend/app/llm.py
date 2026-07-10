"""Market generation guardrail.

An LLM can draft compelling questions, but it cannot prove that every valid
answer has been enumerated. New markets remain disabled until they arrive with
an explicit, validated object universe through ``create_market_with_universe``.
"""
import logging

log = logging.getLogger("pulse.llm")


async def generate_markets_for_category(category_id) -> int:
    log.info(
        "Skipped dynamic market generation for %s: no validated answer universe was supplied",
        category_id,
    )
    return 0
