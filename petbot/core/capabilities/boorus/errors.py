"""Exceptions for booru providers.

Reserved for the genuinely exceptional (a site returning an error payload or a
bad HTTP status). Expected outcomes — an empty search — are not errors and are
returned as ordinary results instead.
"""

from __future__ import annotations


class BooruError(Exception):
    """Base class for booru provider errors."""


class SiteFailureStatusError(BooruError):
    """The remote site reported a failure we should surface to the user."""

    def __init__(self, site_message: str, print_message: str, *, need_code_block: bool = False):
        super().__init__(print_message)
        self.site_message = site_message
        self.print_message = print_message
        self.need_code_block = need_code_block
