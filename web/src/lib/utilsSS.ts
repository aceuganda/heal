import { cookies } from "next/headers";
import { INTERNAL_URL } from "./constants";

export function buildUrl(path: string) {
  if (path.startsWith("/")) {
    return `${INTERNAL_URL}${path}`;
  }
  return `${INTERNAL_URL}/${path}`;
}

// Async since Next 15: `cookies()` returns a promise there. Callers already
// awaited the fetch, so the extra hop is invisible to them.
export async function fetchSS(url: string, options?: RequestInit) {
  const init = options || {
    credentials: "include",
    cache: "no-store",
    headers: {
      cookie: (await cookies())
        .getAll()
        .map((cookie) => `${cookie.name}=${cookie.value}`)
        .join("; "),
    },
  };
  return fetch(buildUrl(url), init);
}
