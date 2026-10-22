"""Translation failure types.

Two distinct cases, because they need different handling: a misconfigured
deployment is an operator problem and should be loud in the logs, while an
unreachable or failing MT service is a runtime problem the user must be told
about in language they can act on.
"""


class TranslationError(Exception):
    """Base class for all translation failures."""

    # Shown to the end user. Never includes URLs, keys or message content.
    user_message = "Translation is temporarily unavailable. Please try again."


class TranslationNotConfigured(TranslationError):
    """A required translation endpoint or credential is missing."""

    user_message = "Translation is not configured for this deployment."


class TranslationUnavailable(TranslationError):
    """The translation service could not be reached or returned an error."""
