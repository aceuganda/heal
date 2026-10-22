/**
 * A reddish two-stop gradient picked from an email, plus the letter to show.
 *
 * "Random" per person but stable: hashed from the email, so the same account
 * gets the same colours on every page and every visit, and two accounts
 * usually differ. Hues stay in the rose → red → coral band so every avatar
 * reads as one family, and lightness stays low enough for white text.
 */

/** FNV-1a: tiny, dependency-free, and spreads similar emails apart. */
function hash(text: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

export interface AvatarLook {
  initial: string;
  background: string;
}

export function avatarLook(email: string | null | undefined): AvatarLook {
  const key = (email || "").trim().toLowerCase();
  const initial = key.match(/[a-z0-9]/)?.[0]?.toUpperCase() ?? "?";
  const h = hash(key || "anonymous");

  // 340..385 wraps through 0: rose, crimson, red, warm coral.
  const hue = (340 + (h % 46)) % 360;
  const shift = 12 + ((h >>> 8) % 18);
  const angle = (h >>> 16) % 360;
  const from = `hsl(${hue} 72% 52%)`;
  const to = `hsl(${(hue + shift) % 360} 78% 40%)`;

  return {
    initial,
    background: `linear-gradient(${angle}deg, ${from}, ${to})`,
  };
}
