"""Tests for tokenisation and the sparse lexical vector.

The sparse half exists for one reason: drug codes and dosages are strings to
match, not concepts to embed. These tests pin that behaviour.
"""
import pytest

from heal.knowledge import embedder
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


class TestHashCollisions:
    """Two tokens can hash to the same slot. Qdrant will not accept that.

    The hashing trick maps an unbounded vocabulary into a fixed space, so
    collisions are expected rather than exceptional. Emitting one entry per
    token produced a duplicate index and Qdrant rejected the entire write:

        422 ... points[11].vector.?.indices: must be unique

    A one-chunk test document never collides, so this only appeared on a real
    1242-chunk guideline -- after minutes of embedding, and it failed the lot.
    """

    def test_indices_are_unique_when_tokens_collide(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Force every token into the same slot: the worst possible collision.
        monkeypatch.setattr(embedder, "_hash_token", lambda token: 7)

        vector = embedder.sparse_vector("amoxicillin ceftriaxone metronidazole")

        assert vector.indices == [7]
        assert len(vector.indices) == len(set(vector.indices))
        assert len(vector.values) == len(vector.indices)

    def test_colliding_weights_are_summed_not_dropped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A collision merges two features; it must not silently discard one."""
        monkeypatch.setattr(
            embedder, "_hash_token", lambda token: 1 if token == "aspirin" else 2
        )

        merged = embedder.sparse_vector("aspirin ibuprofen paracetamol")

        # ibuprofen and paracetamol share slot 2, so it outweighs slot 1.
        weights = dict(zip(merged.indices, merged.values))
        assert weights[2] > weights[1]

    def test_a_real_document_never_produces_duplicate_indices(self) -> None:
        """The property Qdrant enforces, checked against ordinary clinical text."""
        text = (
            "Give TDF/3TC/DTG once daily. Cotrimoxazole 960 mg once daily. "
            "Artemether-lumefantrine 80/480 mg BD for three days. "
            "Artesunate 2.4 mg/kg IV at 0, 12 and 24 hours. "
        ) * 40

        vector = embedder.sparse_vector(text)

        assert len(vector.indices) == len(set(vector.indices))
        assert vector.indices == sorted(vector.indices)
