# `deprecated/`

Frozen code from the Danswer fork, kept for review and revert only.

Rules (from `docs/architecture-decisions.md`):

1. Nothing here may be imported by live code. Enforced by
   `backend/tests/unit/heal/test_no_hardcoded_endpoints.py` and a CI grep.
2. Nothing here is registered: no router, no task, no compose service, no
   Alembic head.
3. Excluded from lint, type-check and test collection.
4. Moves are pure `git mv` renames. Behaviour changes go in their own commit.

The ledger of what moved and why is `docs/deprecated/MOVED.md`.
