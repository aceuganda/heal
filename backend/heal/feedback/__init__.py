"""Rating and comment feedback on answers."""
from heal.feedback.aggregate import aggregate
from heal.feedback.aggregate import Aggregate
from heal.feedback.aggregate import MAX_RATING
from heal.feedback.aggregate import MIN_RATING
from heal.feedback.aggregate import valid_rating

__all__ = ["aggregate", "Aggregate", "MAX_RATING", "MIN_RATING", "valid_rating"]
