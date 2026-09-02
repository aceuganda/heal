"""Tests for the rating aggregate.

These pin the two properties the ADR asks for: bounded, and diminishing.
"""
from heal.feedback.aggregate import aggregate
from heal.feedback.aggregate import MAX_RATING
from heal.feedback.aggregate import MIN_RATING
from heal.feedback.aggregate import NEUTRAL
from heal.feedback.aggregate import normalise
from heal.feedback.aggregate import valid_rating


class TestScale:
    def test_the_scale_is_one_to_four(self) -> None:
        assert (MIN_RATING, MAX_RATING) == (1, 4)

    def test_off_scale_values_are_not_valid(self) -> None:
        assert valid_rating(1)
        assert valid_rating(4)
        assert not valid_rating(0)
        assert not valid_rating(5)

    def test_the_ends_normalise_to_the_ends(self) -> None:
        assert normalise(MIN_RATING) == 0.0
        assert normalise(MAX_RATING) == 1.0


class TestAggregate:
    def test_no_ratings_is_neutral_and_says_so(self) -> None:
        result = aggregate([])
        assert result.score == NEUTRAL
        assert result.count == 0
        assert result.unrated

    def test_off_scale_ratings_are_dropped_not_clamped(self) -> None:
        # A 9 here is a bug upstream. Clamping it to 4 would launder that bug
        # into a glowing review.
        assert aggregate([9]).unrated
        assert aggregate([9, 1]).count == 1

    def test_the_score_stays_inside_zero_and_one(self) -> None:
        for ratings in ([1] * 500, [4] * 500, [1, 4] * 250):
            score = aggregate(ratings).score
            assert 0.0 <= score <= 1.0

    def test_a_single_rating_barely_moves_the_score(self) -> None:
        # The whole point of the curve: one irritated afternoon must not
        # condemn a guideline.
        one = aggregate([1])
        assert one.score > 0.35
        assert one.mean == 1.0

    def test_more_ratings_move_the_score_further(self) -> None:
        few = aggregate([1] * 2)
        many = aggregate([1] * 50)
        assert many.score < few.score

    def test_later_ratings_move_it_less_than_earlier_ones(self) -> None:
        """Diminishing returns, stated as a test rather than as a comment."""
        first_five = aggregate([4] * 5).score - aggregate([4] * 1).score
        second_five = aggregate([4] * 10).score - aggregate([4] * 5).score
        assert second_five < first_five

    def test_good_and_bad_sit_on_opposite_sides_of_neutral(self) -> None:
        assert aggregate([4] * 20).score > NEUTRAL
        assert aggregate([1] * 20).score < NEUTRAL

    def test_evenly_split_ratings_land_on_neutral(self) -> None:
        # And are distinguishable from "nobody rated it" only by the count,
        # which is why callers must read both.
        result = aggregate([1, 4] * 20)
        assert abs(result.score - NEUTRAL) < 1e-9
        assert result.count == 40
        assert not result.unrated

    def test_the_mean_is_reported_unsmoothed(self) -> None:
        # The score is smoothed; the mean is not, so a screen can show what
        # people actually said as well as what it is worth.
        assert aggregate([1, 2, 3, 4]).mean == 2.5
