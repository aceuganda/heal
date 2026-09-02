/**
 * What Heal itself knows about the bodies the model names as references.
 *
 * When the approved library has nothing, the answer closes with a block of
 * source *names* the model produced — "WHO", "Uganda Clinical Guidelines".
 * Nothing was retrieved and nothing was checked, so the drawer has no excerpt
 * to show (see backend/heal/chat/external_refs.py). A reader who has never met
 * the acronym was being told to go and verify something with no idea what it
 * was or where it lives, which is a instruction nobody can follow.
 *
 * So this file adds the one thing that can be added honestly: a short,
 * hand-maintained note about each body Heal recognises, and a link to that
 * body's own publications library.
 *
 * **Why a link here is not the link the product refuses to show.** The rule is
 * that a URL the model produced is a claim about what sits at the other end of
 * it, and Heal will not print one. These URLs are not model output. They are
 * publisher front doors, written into this file by hand and reviewable in the
 * diff, and they point at a library rather than at a document — the reader is
 * being told where to go and search, not being handed a page and told it says
 * what the answer said. Nothing here asserts that the specific guideline the
 * model named exists, is current, or says what the answer claimed.
 *
 * A name that matches nothing below gets no note and no link. Silence is the
 * correct output for a body Heal has not been taught about; guessing a URL
 * from an unrecognised name is precisely the failure this design avoids.
 */

export interface KnownPublisher {
  /** Heal's own name for the body, not the model's wording for it. */
  readonly name: string;
  /** What this body publishes, for a reader meeting the acronym cold. */
  readonly about: string;
  /** The publisher's own entry point. Hand-checked, never model-produced,
   *  and deliberately a library rather than a document. */
  readonly url: string;
  /** What the reader still has to do once they arrive. */
  readonly findIt: string;
}

interface CatalogueEntry extends KnownPublisher {
  /** Matched against the model's wording for the source. */
  readonly match: RegExp;
}

/**
 * Recognised publishers, most specific first.
 *
 * Order is load-bearing: "Uganda Clinical Guidelines, aligned to WHO" should
 * resolve to Uganda's ministry, so the national bodies are matched before the
 * international ones.
 *
 * `WHO` and `NICE` are matched case-sensitively, and only as acronyms. Both
 * are ordinary English words, and a source line reading "guidance for staff
 * who manage TB" or "a nice summary of paediatric dosing" would otherwise be
 * filed under an international body it never mentioned. The spelled-out names
 * beside them stay case-insensitive; only the three or four capitals are
 * load-bearing. Acronyms that are not also words keep the `i` flag.
 */
const CATALOGUE: readonly CatalogueEntry[] = [
  {
    match: /uganda|\bucg\b|\bmoh\b/i,
    name: "Uganda Ministry of Health",
    about:
      "Uganda's national clinical guidelines — the Uganda Clinical Guidelines (UCG) and the disease-specific national protocols issued alongside them. These are the guidelines that apply in a Ugandan facility where they differ from international ones.",
    url: "https://www.health.go.ug/",
    findIt:
      "Guidelines and protocols sit under the ministry's publications section. The UCG is published as a single dated edition — check you are reading the current one.",
  },
  {
    match: /\bWHO\b|[Ww]orld [Hh]ealth [Oo]rgani[sz]ation/,
    name: "World Health Organization",
    about:
      "International clinical guidelines, treatment recommendations and fact sheets. Most national protocols, Uganda's included, are derived from these.",
    url: "https://www.who.int/publications",
    findIt:
      "Search the publications library by condition. Each guideline carries its edition and publication date on the record.",
  },
  {
    match: /\bcdc\b|centers? for disease control/i,
    name: "US Centers for Disease Control and Prevention",
    about:
      "United States clinical and public-health guidance: treatment recommendations, case definitions and outbreak notices. Written for US practice, so it may differ from the Ugandan protocol.",
    url: "https://www.cdc.gov/",
    findIt: "Search by condition; clinical guidance is separated from patient-facing pages.",
  },
  {
    match: /\bunaids\b/i,
    name: "UNAIDS",
    about:
      "The UN programme on HIV/AIDS: policy guidance, treatment targets and country-level epidemiological data.",
    url: "https://www.unaids.org/en/resources",
    findIt: "Resources are grouped by type; country data and guidance documents are listed separately.",
  },
  {
    match: /\bunicef\b/i,
    name: "UNICEF",
    about:
      "Guidance and programme data on maternal, newborn and child health, nutrition and immunisation.",
    url: "https://www.unicef.org/reports",
    findIt: "Reports are searchable by topic and by country.",
  },
  {
    match: /\bNICE\b|[Nn]ational [Ii]nstitute for [Hh]ealth and [Cc]are [Ee]xcellence/,
    name: "NICE (United Kingdom)",
    about:
      "UK clinical guidelines and evidence summaries. Written for the NHS, so treatment availability and first-line choices may not match Ugandan practice.",
    url: "https://www.nice.org.uk/guidance",
    findIt: "Guidance is browsable by condition, each with its own review date.",
  },
];

/**
 * The publisher behind a model-named reference, or null if Heal does not
 * recognise it.
 *
 * Null is an ordinary result, not a failure: the drawer's warning stands on
 * its own and simply carries no note.
 */
export function lookupPublisher(
  sourceName: string | null | undefined
): KnownPublisher | null {
  if (!sourceName) {
    return null;
  }

  const entry = CATALOGUE.find((candidate) => candidate.match.test(sourceName));
  if (!entry) {
    return null;
  }

  const { match, ...publisher } = entry;
  return publisher;
}

/** The bare host, for link text that shows where a tap actually goes. */
export function publisherHost(publisher: KnownPublisher): string {
  return publisher.url.replace(/^https?:\/\//, "").replace(/\/.*$/, "");
}
