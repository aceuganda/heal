/**
 * Turning the `[1]` markers in an answer into something clickable.
 *
 * The model is told to write `[1]` after each claim, and the backend maps each
 * marker to the passage it points at. Until now the marker survived into the
 * rendered answer as literal text: a reader saw `[1]` and had nothing to click.
 *
 * The approach is to rewrite each marker into an ordinary markdown link with a
 * fragment href, and let the markdown parser do the work. The alternative --
 * walking the rendered nodes and splitting text on a regex -- looks simpler and
 * is not: react-markdown parses a bare `[1]` as an undefined link reference and
 * hands it back as SEVERAL adjacent text nodes, so there is frequently no
 * single node containing "[1]" to split.
 *
 * A fragment (`#heal-citation-1`) rather than a custom `citation:` scheme
 * because react-markdown's default URI transform strips unknown schemes, and
 * turning that sanitisation off for model-generated text is not a trade worth
 * making for a nicer-looking href.
 */

/** Mirrors `_CITATION` in `heal/chat/stream_processing.py`. Keep them in step:
 *  a marker this matches but the backend does not is a link to nothing. */
const CITATION_MARKER = /\[(\d{1,2})\](?!\()/g;

/** Fenced blocks and inline spans, captured so `split` keeps them. A dose
 *  written inside a code span is still literal text and must stay as it is. */
const CODE_SEGMENT = /(```[\s\S]*?```|`[^`\n]*`)/g;

export const CITATION_HREF_PREFIX = "#heal-citation-";

export function citationHref(key: string): string {
  return `${CITATION_HREF_PREFIX}${key}`;
}

/** The marker number a rewritten link points at, or null for a real link. */
export function citationKeyFromHref(href: string | undefined): string | null {
  if (!href || !href.startsWith(CITATION_HREF_PREFIX)) {
    return null;
  }
  return href.slice(CITATION_HREF_PREFIX.length) || null;
}

/**
 * Rewrite every marker that has a source behind it into a link.
 *
 * `knownKeys` are the keys of the message's citation map, so a marker the
 * model invented -- `[9]` when it was given five passages -- is left as plain
 * text rather than made clickable. The backend already drops those; this makes
 * the two agree about what the reader can click.
 */
export function linkifyCitations(
  markdown: string,
  knownKeys: Set<string>
): string {
  if (!markdown || knownKeys.size === 0) {
    return markdown;
  }

  // `split` on a capturing group yields text at even indices and the code
  // segments that separated them at odd ones.
  return markdown
    .split(CODE_SEGMENT)
    .map((segment, index) =>
      index % 2 === 1 ? segment : linkifySegment(segment, knownKeys)
    )
    .join("");
}

function linkifySegment(text: string, knownKeys: Set<string>): string {
  return text.replace(CITATION_MARKER, (marker, digits: string) => {
    // Normalised the way the backend normalises it, with int(): `[01]` and
    // `[1]` are the same citation, and the map is keyed by the number.
    const key = String(Number(digits));
    return knownKeys.has(key) ? `[${key}](${citationHref(key)})` : marker;
  });
}
