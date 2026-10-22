"""Turning many ratings into one number, without letting the first one shout.

A four-point rating, 1 (worst) to 4 (best). Four rather than five because there
is no neutral middle: a health worker has to come down on one side of "was this
usable", and a five-point scale's midpoint is where undecided answers go to be
uncounted. Four also fits a phone screen without the stars shrinking.

The aggregate is deliberately NOT a mean. A mean lets a single early 1-star
verdict define a source forever, and lets a much-used source accumulate an
unbounded score. Instead the mean is pulled toward neutral by a confidence
factor that saturates: the first few ratings move the score a lot, later ones
move it less, and the result is always bounded in 0..1.

  score = 0.5 + (normalised_mean - 0.5) * n / (n + SMOOTHING)

At n=0 the score is exactly 0.5 -- "nobody has said" and "opinion is evenly
split" are the same number, so `count` is always reported alongside it and no
caller should read one without the other.

**What this score may do.** It is a review signal: it tells an admin which
answers and which sources health workers rate poorly, so a human goes and looks
at the guideline. It is NOT wired into retrieval ranking, and must not be. The
inherited system fed feedback through a sigmoid into a 0.5x-2.0x multiplier on
the retrieval score, which means a source can be quietly demoted below the
evidence threshold because users disliked answers built from it -- no audit
trail, no clinician in the loop. See docs/architecture-decisions.md § Feedback.
"""
from dataclasses import dataclass

# The scale. 1 is the worst rating a health worker can give, 4 the best.
MIN_RATING = 1
MAX_RATING = 4

# How many ratings before the score is worth roughly half its face value.
# Five is a judgement, not a measurement: it is small enough that a genuinely
# bad source surfaces within a morning's use, and large enough that one
# irritated afternoon does not condemn a guideline.
SMOOTHING = 5.0

NEUTRAL = 0.5


def valid_rating(rating: int) -> bool:
    """Whether a rating is on the scale at all."""
    return MIN_RATING <= rating <= MAX_RATING


@dataclass(frozen=True)
class Aggregate:
    """One subject's ratings, reduced.

    `count` is not decoration. A score of 0.5 from no ratings and a score of
    0.5 from forty evenly-split ratings mean opposite things, and a screen that
    shows the score without the count cannot tell them apart.
    """

    count: int
    mean: float
    score: float

    @property
    def unrated(self) -> bool:
        return self.count == 0


def normalise(mean: float) -> float:
    """A 1..4 mean onto 0..1."""
    return (mean - MIN_RATING) / (MAX_RATING - MIN_RATING)


def aggregate(ratings: list[int]) -> Aggregate:
    """Reduce ratings to a bounded score, discarding anything off-scale.

    Off-scale values are dropped rather than clamped: a 7 in this list is a bug
    somewhere upstream, and clamping it to 4 would launder that bug into a
    glowing review.
    """
    usable = [r for r in ratings if valid_rating(r)]
    if not usable:
        return Aggregate(count=0, mean=0.0, score=NEUTRAL)

    count = len(usable)
    mean = sum(usable) / count
    confidence = count / (count + SMOOTHING)
    score = NEUTRAL + (normalise(mean) - NEUTRAL) * confidence
    return Aggregate(count=count, mean=mean, score=score)
