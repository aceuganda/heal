/** Chat request errors, worded for the person using the chat. */

/** An error whose message is already fit to show a health worker. */
export class ChatRequestError extends Error {}

/**
 * The server's own explanation of a failed request, or `fallback`.
 *
 * Never assumes the body is JSON: a proxy or a crashed worker answers with
 * plain text ("Internal Server Error"), and parsing that is what used to turn
 * one failure into a second, more confusing one.
 */
export async function errorDetail(
  response: Response,
  fallback: string
): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail ?? body?.message;
    return typeof detail === "string" && detail ? detail : fallback;
  } catch {
    return fallback;
  }
}

/**
 * What to tell the user when sending a message fails.
 *
 * `streamStarted` separates "never reached the server" from "cut off part
 * way": in the second case the answer may well have been saved, and a refresh
 * is the honest advice.
 */
export function chatErrorMessage(
  error: unknown,
  streamStarted: boolean
): string {
  if (error instanceof ChatRequestError) return error.message;
  if (streamStarted) {
    return "The answer was interrupted before it finished. Refresh the page to see if it was saved, or ask again.";
  }
  if (error instanceof TypeError) {
    return "Couldn't reach Heal. Check your connection and try again.";
  }
  return "Something went wrong while answering. Please try again.";
}
