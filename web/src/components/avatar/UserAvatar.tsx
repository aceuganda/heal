import { avatarLook } from "./gradient";

/** The signed-in person as the first letter of their email on a reddish
 *  gradient. Decorative: the email itself is always shown or announced
 *  beside it, so it carries no accessible name of its own. */
export function UserAvatar({
  email,
  size = 32,
  className = "",
}: {
  email: string | null | undefined;
  size?: number;
  className?: string;
}) {
  const { initial, background } = avatarLook(email);
  return (
    <span
      aria-hidden="true"
      className={`inline-flex shrink-0 select-none items-center justify-center rounded-full font-semibold text-white shadow-sm ${className}`}
      style={{
        width: size,
        height: size,
        background,
        fontSize: Math.round(size * 0.44),
      }}
    >
      {initial}
    </span>
  );
}
