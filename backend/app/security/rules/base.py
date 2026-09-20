"""
Abstract base class for all security rules.

Every rule MUST:
    1. Receive a ``SecurityContext`` via ``evaluate()``.
    2. Return a ``SecurityRuleResult`` if the rule condition was triggered.
    3. Return ``None`` if the rule was NOT triggered.

Rules MUST NOT:
    - Access the database.
    - Send notifications or alerts.
    - Call Frigate or any external service.
    - Import modules from ``app.models``, ``app.database``, or
      ``app.integrations``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.security.models import SecurityContext, SecurityRuleResult


class SecurityRule(ABC):
    """Base class for pluggable security rules."""

    @property
    def name(self) -> str:
        """Human-readable rule name (defaults to the class name)."""
        return self.__class__.__name__

    @abstractmethod
    def evaluate(self, context: SecurityContext) -> SecurityRuleResult | None:
        """Evaluate the rule against the supplied *context*.

        Returns:
            A ``SecurityRuleResult`` when the rule condition is met, or
            ``None`` when it is not.
        """

    def reset(self) -> None:
        """Clear any internal state held by this rule.

        The default implementation is a no-op.  Stateful rules (zone
        entry, loitering) should override this.
        """
