# Moved to `deprecated/`

Every retirement gets one line here. Nothing under `deprecated/` is imported,
registered, linted, type-checked or tested — it is frozen text kept so that a
removal can be reviewed and reverted cheaply. Deletion is a separate change
after the pilot runs clean.

See `docs/keep-and-simplify-plan.md` § *Deprecation policy* for the rules.

| Date | From | To | Reason | Replaced by |
| --- | --- | --- | --- | --- |
| 2026-08-28 | `backend/danswer/utils/translation.py` | `backend/deprecated/danswer/utils/translation.py` | Called two hard-coded public IPs over plain HTTP with no timeout, auth, retry or failure path. | `backend/heal/language/` (`LanguageService` + `heal_mt` provider) |
