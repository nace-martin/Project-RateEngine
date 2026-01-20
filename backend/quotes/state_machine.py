"""
Quote State Machine

Manages quote lifecycle transitions with validation.
MVP States: DRAFT → FINALIZED → SENT

Architecture Principles:
- FINALIZED and SENT quotes are immutable
- Transitions must be explicit (via API endpoint)
- Timestamps auto-populated on transition
"""

import logging
from typing import Tuple, Optional
from django.utils import timezone
from django.contrib.auth import get_user_model

from .models import Quote

logger = logging.getLogger(__name__)
User = get_user_model()


# Valid state transitions
VALID_TRANSITIONS = {
    Quote.Status.DRAFT: [Quote.Status.FINALIZED],
    Quote.Status.INCOMPLETE: [Quote.Status.DRAFT],  # Must complete before finalizing
    Quote.Status.FINALIZED: [Quote.Status.SENT, Quote.Status.EXPIRED],
    Quote.Status.SENT: [Quote.Status.ACCEPTED, Quote.Status.LOST, Quote.Status.EXPIRED],  # Outcome tracking
    Quote.Status.ACCEPTED: [],  # Terminal state (won)
    Quote.Status.LOST: [],      # Terminal state (lost)
    Quote.Status.EXPIRED: [],   # Terminal state
}

# States that block quote editing
LOCKED_STATES = [Quote.Status.FINALIZED, Quote.Status.SENT]


class QuoteStateError(Exception):
    """Raised when an invalid state transition is attempted."""
    pass


class QuoteStateMachine:
    """
    Manages quote lifecycle transitions.
    
    Usage:
        machine = QuoteStateMachine(quote)
        success, error = machine.transition_to('FINALIZED', user)
    """
    
    def __init__(self, quote: Quote):
        self.quote = quote
    
    @property
    def current_state(self) -> str:
        return self.quote.status
    
    @property
    def is_editable(self) -> bool:
        """Check if quote can be edited (not locked)."""
        if getattr(self.quote, 'is_archived', False):
            return False
        return self.quote.status not in LOCKED_STATES
    
    @property
    def available_transitions(self) -> list:
        """Return list of valid next states from current state."""
        if getattr(self.quote, 'is_archived', False):
            return []
        return VALID_TRANSITIONS.get(self.quote.status, [])
    
    def can_transition_to(self, target_status: str) -> bool:
        """Check if transition to target status is valid."""
        return target_status in self.available_transitions
    
    def transition_to(
        self, 
        target_status: str, 
        user: Optional[User] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Attempt to transition quote to target status.
        
        Args:
            target_status: The status to transition to
            user: The user performing the transition
            
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        # Validate transition
        if not self.can_transition_to(target_status):
            current = self.current_state
            valid = ', '.join(self.available_transitions) or 'none'
            error = (
                f"Cannot transition from {current} to {target_status}. "
                f"Valid transitions: {valid}"
            )
            logger.warning(f"Invalid quote transition attempt: {error}")
            return False, error
        
        # Perform transition
        now = timezone.now()
        self.quote.status = target_status
        
        # Set lifecycle timestamps based on target state
        if target_status == Quote.Status.FINALIZED:
            self.quote.finalized_at = now
            self.quote.finalized_by = user
            logger.info(f"Quote {self.quote.quote_number} finalized by {user}")
            
        elif target_status == Quote.Status.SENT:
            self.quote.sent_at = now
            self.quote.sent_by = user
            logger.info(f"Quote {self.quote.quote_number} sent by {user}")
        
        # Save the quote
        self.quote.save(update_fields=[
            'status',
            'finalized_at', 'finalized_by',
            'sent_at', 'sent_by',
        ])
        
        return True, None
    
    def finalize(self, user: Optional[User] = None) -> Tuple[bool, Optional[str]]:
        """
        Finalize a quote by delegating to the Quote model's finalize() method.
        This properly assigns the permanent QT-YYYY-NNNN quote number.
        """
        # Validate transition first
        if not self.can_transition_to(Quote.Status.FINALIZED):
            current = self.current_state
            valid = ', '.join(self.available_transitions) or 'none'
            error = (
                f"Cannot transition from {current} to FINALIZED. "
                f"Valid transitions: {valid}"
            )
            logger.warning(f"Invalid quote transition attempt: {error}")
            return False, error
        
        try:
            # Delegate to the model's finalize() which handles:
            # - Quote number assignment (QT-YYYY-NNNN)
            # - Status change
            # - Expiry date (valid_until)
            # - Timestamps
            self.quote.finalize(user=user)
            logger.info(f"Quote {self.quote.quote_number} finalized by {user}")
            return True, None
        except ValueError as e:
            return False, str(e)
    
    def mark_sent(self, user: Optional[User] = None) -> Tuple[bool, Optional[str]]:
        """Convenience method to mark quote as sent."""
        return self.transition_to(Quote.Status.SENT, user)
    
    def mark_won(self, user: Optional[User] = None) -> Tuple[bool, Optional[str]]:
        """Mark quote as accepted/won."""
        return self.transition_to(Quote.Status.ACCEPTED, user)
    
    def mark_lost(self, user: Optional[User] = None) -> Tuple[bool, Optional[str]]:
        """Mark quote as lost."""
        return self.transition_to(Quote.Status.LOST, user)
    
    def mark_expired(self, user: Optional[User] = None) -> Tuple[bool, Optional[str]]:
        """Mark quote as expired."""
        return self.transition_to(Quote.Status.EXPIRED, user)
    
    def cancel(self, user: Optional[User] = None) -> Tuple[bool, Optional[str]]:
        """
        Cancel/archive a draft quote.
        This is a soft-delete (sets is_archived=True) rather than a state transition.
        """
        if self.quote.status != Quote.Status.DRAFT:
            return False, f"Cannot cancel quote with status {self.quote.status}. Only DRAFT quotes can be cancelled."
        
        self.quote.is_archived = True
        self.quote.save(update_fields=['is_archived'])
        logger.info(f"Quote {self.quote.quote_number} cancelled/archived by {user}")
        return True, None


def is_quote_editable(quote: Quote) -> bool:
    """Utility function to check if quote is editable."""
    if getattr(quote, 'is_archived', False):
        return False
    return quote.status not in LOCKED_STATES


def get_status_display_info(status: str) -> dict:
    """
    Get display information for a status.
    
    Returns:
        dict with 'label', 'color', 'description'
    """
    status_info = {
        Quote.Status.DRAFT: {
            'label': 'Draft',
            'color': 'blue',
            'description': 'Quote is being prepared',
            'editable': True,
        },
        Quote.Status.INCOMPLETE: {
            'label': 'Incomplete',
            'color': 'red',
            'description': 'Missing required data',
            'editable': True,
        },
        Quote.Status.FINALIZED: {
            'label': 'Finalized',
            'color': 'green',
            'description': 'Quote is locked and ready to send',
            'editable': False,
        },
        Quote.Status.SENT: {
            'label': 'Sent',
            'color': 'purple',
            'description': 'Quote delivered to customer',
            'editable': False,
        },
        # Post-MVP states
        Quote.Status.ACCEPTED: {
            'label': 'Accepted',
            'color': 'emerald',
            'description': 'Customer accepted the quote',
            'editable': False,
        },
        Quote.Status.LOST: {
            'label': 'Lost',
            'color': 'gray',
            'description': 'Quote was not accepted',
            'editable': False,
        },
        Quote.Status.EXPIRED: {
            'label': 'Expired',
            'color': 'amber',
            'description': 'Quote validity period ended',
            'editable': False,
        },
    }
    return status_info.get(status, {
        'label': status,
        'color': 'gray',
        'description': '',
        'editable': False,
    })
