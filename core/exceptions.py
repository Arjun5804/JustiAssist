"""
JustiAssist Domain Exceptions
"""

class ConversationOwnershipError(Exception):
    """Raised when a user attempts to access or modify a conversation belonging to another user."""
    pass
