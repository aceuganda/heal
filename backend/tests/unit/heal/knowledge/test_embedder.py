"""Tests for tokenisation and the sparse lexical vector.

The sparse half exists for one reason: drug codes and dosages are strings to
match, not concepts to embed. These tests pin that behaviour.
"""
from heal.knowledge.embedder import sparse_vector
from heal.knowledge.embedder import tokenize


class TestTokenize:
    def test_keeps_a_drug_regimen_as_one_token(self) -> None:
        """TDF/3TC/DTG shredded into fragments matches nothing useful."""
        assert "tdf/3tc/dtg" in tokenize("Start TDF/3TC/DTG today")

    def test_keeps_hyphenated_drug_names_intact(self) -> None:
        assert "co-trimoxazole" in tokenize("Give co-trimoxazole prophylaxis")

    def test_keeps_dosage_strings(self) -> None:
        assert "500mg" in tokenize("500mg BD for five days")

    def test_drops_stopwords_and_single_characters(self) -> None:
        tokens = tokenize("the a of x dose")
        assert "dose" in tokens
        assert "the" not in tokens and "x" not in tokens

    def test_does_not_drop_clinical_negations(self) -> None:
        """ "not" and "without" change a dose instruction completely."""
        tokens = tokenize("not for pregnant patients without renal review")
        assert "not" in tokens and "without" in tokens


class TestSparseVector:
    def test_empty_text_yields_an_empty_vector(self) -> None:
        assert len(sparse_vector("   ")) == 0

    def test_indices_are_sorted_as_qdrant_expects(self) -> None:
        vector = sparse_vector("dolutegravir tenofovir lamivudine dosage adult")
        assert vector.indices == sorted(vector.indices)

    def test_parallel_arrays_stay_the_same_length(self) -> None:
        vector = sparse_vector("give 500mg twice daily for five days")
        assert len(vector.indices) == len(vector.values)

    def test_hashing_is_stable_across_calls(self) -> None:
        """Unstable hashing would make yesterday's points unsearchable."""
        assert (
            sparse_vector("TDF/3TC/DTG").indices == sparse_vector("TDF/3TC/DTG").indices
        )

    def test_is_normalised_so_long_passages_do_not_dominate(self) -> None:
        vector = sparse_vector("dose " * 50 + "rifampicin")
        assert sum(v * v for v in vector.values) == __import__("pytest").approx(1.0)

    def test_repetition_is_damped_not_linear(self) -> None:
        once = sparse_vector("rifampicin isoniazid")
        many = sparse_vector("rifampicin " * 20 + "isoniazid")
        assert max(many.values) < 20 * max(once.values)
