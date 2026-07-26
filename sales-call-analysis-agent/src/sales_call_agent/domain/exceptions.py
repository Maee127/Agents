"""Domain exception hierarchy.

All messages are log-safe: they reference field names and status names only,
never PII values or call identifiers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sales_call_agent.domain.models import CallProcessingStatus


class DomainError(Exception):
    """Base class for all domain rule violations. Never raised directly."""


class InvalidCallMetadataError(DomainError):
    """Raised when a ``CallMetadata`` invariant is violated."""


class InvalidAudioAssetError(DomainError):
    """Raised when an ``AudioAsset`` invariant is violated."""


class InvalidCallError(DomainError):
    """Raised when a ``Call``-level consistency rule is violated."""


class InvalidStatusTransitionError(DomainError):
    """Raised when a call is moved to a status its current status does not allow."""

    def __init__(
        self,
        from_status: CallProcessingStatus,
        to_status: CallProcessingStatus,
    ) -> None:
        super().__init__(f"cannot transition from {from_status.name} to {to_status.name}")
        self.from_status = from_status
        self.to_status = to_status
