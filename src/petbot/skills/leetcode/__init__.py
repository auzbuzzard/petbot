"""The ``leetcode`` skill package (LeetCode's GraphQL endpoint; no credentials)."""

from __future__ import annotations

import httpx

from petbot.skills.leetcode.skill import GraphQLProvider, LeetCodeProvider, LeetCodeSkill

__all__ = ["GraphQLProvider", "LeetCodeProvider", "LeetCodeSkill", "build_leetcode"]


def build_leetcode() -> LeetCodeSkill:
    return LeetCodeSkill([GraphQLProvider(httpx.AsyncClient(timeout=10.0))])
