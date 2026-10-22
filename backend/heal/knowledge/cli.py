"""Command-line entry points for the knowledge store.

The admin screen at `/admin/sources` is the normal way to do all of this. This
exists for scripted bulk loads, where clicking through a browser once per
document is the wrong tool.

Run through the API container, which already has the model and the Qdrant
credentials:

    docker compose exec api_server python -m heal.knowledge.cli init
    docker compose exec api_server python -m heal.knowledge.cli ingest \\
        --file /path/to/guideline.txt --title "Uganda ART Guidelines" \\
        --actor "dr.name@facility" --version 2022 --approve
    docker compose exec api_server python -m heal.knowledge.cli search "500mg BD"

`ingest` writes unapproved by default -- `--approve` is a separate, deliberate
act, because retrieval only ever returns approved chunks.
"""
import argparse
import sys

from heal import config
from heal.knowledge.ingest import reference_ingest
from heal.knowledge.ingest import set_approval
from heal.knowledge.ingest import supersede
from heal.knowledge.store import ensure_collection
from heal.knowledge.store import QdrantKnowledgeStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="heal.knowledge.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the Qdrant collection if absent")

    ing = sub.add_parser("ingest", help="chunk, embed and write one document")
    ing.add_argument("--file", required=True, help="UTF-8 text file to ingest")
    ing.add_argument("--title", required=True)
    ing.add_argument("--actor", required=True, help="who is doing this; recorded")
    ing.add_argument("--version", default="1")
    ing.add_argument("--publisher", default="")
    ing.add_argument("--published", default="")
    ing.add_argument("--source-id", default=None)
    ing.add_argument(
        "--approve",
        action="store_true",
        help="approve on ingest; without it the document is stored but never cited",
    )

    app = sub.add_parser("approve", help="approve or unapprove an existing source")
    app.add_argument("--source-id", required=True)
    app.add_argument("--off", action="store_true", help="unapprove instead")

    sup = sub.add_parser("supersede", help="mark other versions as not current")
    sup.add_argument("--source-id", required=True)
    sup.add_argument("--keep-version", required=True)

    sea = sub.add_parser("search", help="run a query the way the agent would")
    sea.add_argument("query")

    args = parser.parse_args(argv)

    if args.command == "init":
        ensure_collection()
        print(f"collection ready: {config.QDRANT_COLLECTION}")
        return 0

    if args.command == "ingest":
        with open(args.file, encoding="utf-8") as handle:
            text = handle.read()
        result = reference_ingest(
            text=text,
            title=args.title,
            actor=args.actor,
            version=args.version,
            publisher=args.publisher,
            published=args.published,
            source_id=args.source_id,
            approved=args.approve,
        )
        print(f"status:  {result.status}")
        print(f"source:  {result.source_id} (version {result.version})")
        print(f"chunks:  {result.chunks_written}")
        print(f"model:   {result.model}")
        if not args.approve and result.status == "completed":
            print("NOTE: stored unapproved -- no answer will cite it until approved.")
        if result.error:
            print(f"error:   {result.error}", file=sys.stderr)
            return 1
        return 0

    if args.command == "approve":
        set_approval(args.source_id, approved=not args.off)
        print(f"source {args.source_id} approved={not args.off}")
        return 0

    if args.command == "supersede":
        supersede(args.source_id, keep_version=args.keep_version)
        print(f"source {args.source_id}: current version is now {args.keep_version}")
        return 0

    if args.command == "search":
        outcome = QdrantKnowledgeStore().search(args.query)
        if outcome.unavailable:
            print(f"store unavailable: {outcome.error}", file=sys.stderr)
            return 1
        if outcome.below_floor:
            print(
                f"nothing above MIN_RETRIEVAL_SCORE={config.MIN_RETRIEVAL_SCORE} "
                f"(best was {outcome.best_score_before_floor:.3f})"
            )
            return 0
        if not outcome:
            print("no approved chunks matched")
            return 0
        for i, item in enumerate(outcome.chunks, start=1):
            print(
                f"\n[{i}] {item.source.label()}  score={item.score:.3f} "
                f"(dense {item.dense_score:.3f} / sparse {item.sparse_score:.3f})"
            )
            print(f"    {item.text[:300]}...")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
