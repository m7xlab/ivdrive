"""AI Assistant access gate.

Centralizes all the tier/quota logic so chat.py stays clean. Single source of
truth for "is this user allowed to ask right now, and if so, which model?".

Resolution order:
1. ai_user_overrides.ai_enabled_override (if set) → user.ai_enabled
2. users.ai_enabled
3. ai_user_overrides.tier_override (if set) → user.ai_tier
4. users.ai_tier
5. ai_tier_configs[tier] → max_questions_per_day, model_provider, model_name
6. ai_user_overrides.max_questions_per_day (if set) → tier max
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

Tier = Literal["free", "pro", "team"]


@dataclass
class AIGateResult:
    allowed: bool
    reason: str | None          # "disabled" / "daily_cap" / "monthly_cap" / None
    model_provider: str         # "gemini" / "minimax" / "deterministic" / "blocked"
    model_name: str
    tier: str
    max_per_day: int
    max_per_month: int
    used_today: int
    used_this_month: int
    user_id: str
    # Effective after overrides (so the admin UI can show "you gave them a 200/day override on tier=pro's 50/day")
    effective_max_per_day: int
    effective_max_per_month: int


async def check_ai_access(
    db: AsyncSession, user_id: str
) -> AIGateResult:
    """Resolve the user's effective AI access state for the current moment.

    One DB roundtrip. Returns a struct the chat handler can branch on.
    """
    sql = text("""
        WITH user_row AS (
          SELECT id, ai_enabled, ai_tier FROM users WHERE id = :uid
        ),
        override_row AS (
          SELECT * FROM ai_user_overrides WHERE user_id = :uid
        ),
        tier_cfg AS (
          SELECT * FROM ai_tier_configs
          WHERE tier = COALESCE(
            (SELECT tier_override FROM override_row),
            (SELECT ai_tier FROM user_row)
          )
        ),
        usage_today AS (
          SELECT COUNT(*)::int AS n
          FROM ai_usage_log
          WHERE user_id = :uid
            AND blocked_reason IS NULL
            AND requested_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
        ),
        usage_month AS (
          SELECT COUNT(*)::int AS n
          FROM ai_usage_log
          WHERE user_id = :uid
            AND blocked_reason IS NULL
            AND requested_at >= date_trunc('month', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
        )
        SELECT
          u.id::text AS user_id,
          u.ai_enabled,
          u.ai_tier,
          COALESCE(o.tier_override, u.ai_tier) AS effective_tier,
          o.ai_enabled_override,
          t.max_questions_per_day,
          t.max_questions_per_month,
          COALESCE(o.max_questions_per_day, t.max_questions_per_day) AS effective_max_day,
          COALESCE(o.max_questions_per_month, t.max_questions_per_month) AS effective_max_month,
          t.model_provider,
          t.model_name,
          (SELECT n FROM usage_today) AS used_today,
          (SELECT n FROM usage_month) AS used_this_month
        FROM user_row u
        CROSS JOIN tier_cfg t
        LEFT JOIN override_row o ON TRUE
    """)

    row = (await db.execute(sql, {"uid": user_id})).mappings().first()
    if not row:
        # User vanished mid-request — fail closed
        return AIGateResult(
            allowed=False, reason="no_user", model_provider="blocked",
            model_name="", tier="free", max_per_day=0, max_per_month=0,
            used_today=0, used_this_month=0, user_id=user_id,
            effective_max_per_day=0, effective_max_per_month=0,
        )

    # Master switch — override > user default
    is_enabled = row["ai_enabled"]
    if row["ai_enabled_override"] is not None:
        is_enabled = row["ai_enabled_override"]

    if not is_enabled:
        return AIGateResult(
            allowed=False, reason="disabled", model_provider="blocked",
            model_name="", tier=row["effective_tier"],
            max_per_day=row["max_questions_per_day"],
            max_per_month=row["max_questions_per_month"],
            used_today=row["used_today"], used_this_month=row["used_this_month"],
            user_id=user_id,
            effective_max_per_day=row["effective_max_day"],
            effective_max_per_month=row["effective_max_month"],
        )

    # Quotas
    max_day = row["effective_max_day"]
    max_month = row["effective_max_month"]
    used_today = row["used_today"]
    used_month = row["used_this_month"]

    if max_day > 0 and used_today >= max_day:
        return AIGateResult(
            allowed=False, reason="daily_cap", model_provider="blocked",
            model_name="", tier=row["effective_tier"],
            max_per_day=row["max_questions_per_day"],
            max_per_month=row["max_questions_per_month"],
            used_today=used_today, used_this_month=used_month,
            user_id=user_id,
            effective_max_per_day=max_day, effective_max_per_month=max_month,
        )

    if max_month > 0 and used_month >= max_month:
        return AIGateResult(
            allowed=False, reason="monthly_cap", model_provider="blocked",
            model_name="", tier=row["effective_tier"],
            max_per_day=row["max_questions_per_day"],
            max_per_month=row["max_questions_per_month"],
            used_today=used_today, used_this_month=used_month,
            user_id=user_id,
            effective_max_per_day=max_day, effective_max_per_month=max_month,
        )

    return AIGateResult(
        allowed=True, reason=None,
        model_provider=row["model_provider"],
        model_name=row["model_name"],
        tier=row["effective_tier"],
        max_per_day=row["max_questions_per_day"],
        max_per_month=row["max_questions_per_month"],
        used_today=used_today, used_this_month=used_month,
        user_id=user_id,
        effective_max_per_day=max_day, effective_max_per_month=max_month,
    )


async def log_ai_usage(
    db: AsyncSession,
    *,
    user_id: str,
    vehicle_id: str | None,
    session_id: str | None,
    model_provider: str,
    model_name: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    cached_tokens: int | None,
    estimated_cost_usd: float,
    blocked_reason: str | None,
    question_chars: int | None,
) -> None:
    """Append a row to ai_usage_log. Best-effort: never raise to the caller."""
    try:
        await db.execute(
            text("""
                INSERT INTO ai_usage_log (
                  user_id, vehicle_id, session_id,
                  model_provider, model_name,
                  prompt_tokens, completion_tokens, cached_tokens,
                  estimated_cost_usd, blocked_reason, question_chars
                ) VALUES (
                  :user_id, :vehicle_id, :session_id,
                  :model_provider, :model_name,
                  :prompt_tokens, :completion_tokens, :cached_tokens,
                  :estimated_cost_usd, :blocked_reason, :question_chars
                )
            """),
            {
                "user_id": user_id,
                "vehicle_id": vehicle_id,
                "session_id": session_id,
                "model_provider": model_provider,
                "model_name": model_name,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cached_tokens": cached_tokens,
                "estimated_cost_usd": estimated_cost_usd,
                "blocked_reason": blocked_reason,
                "question_chars": question_chars,
            },
        )
        await db.commit()
    except Exception as e:
        logger.warning("Failed to log AI usage for user %s: %s", user_id, e)
        await db.rollback()


# Pricing per 1M tokens (USD) — update from /docs/guides/pricing-paygo as needed
# Cache hits = cache_read_input_tokens, input = input_tokens - cache_hits
PRICING = {
    "minimax-m3": {"input": 0.60, "output": 2.40, "cache_hit": 0.12},
    "gemini-3.1-pro-preview": {"input": 1.25, "output": 5.00, "cache_hit": 0.31},
}

_PRICING_DEFAULT = "minimax-m3"


def estimate_cost_usd(
    model_key: str, prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0
) -> float:
    """Estimate cost in USD from token usage. Per-1M-token rates. SINGLE source of truth (bug 2-13).

    Keyed by the real model_name the gate returns (e.g. 'MiniMax-M3',
    'gemini-3.1-pro-preview'), matched case-insensitively.
    """
    p = PRICING.get((model_key or "").lower(), PRICING[_PRICING_DEFAULT])
    new_input = max(0, prompt_tokens - cached_tokens)
    cost = (
        (new_input / 1_000_000) * p["input"]
        + (cached_tokens / 1_000_000) * p["cache_hit"]
        + (completion_tokens / 1_000_000) * p["output"]
    )
    return round(cost, 6)
