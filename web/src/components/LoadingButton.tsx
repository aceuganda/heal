"use client";

/**
 * A Tremor Button whose busy state does not crash React 19.
 *
 * Tremor's own `loading` prop wraps the button in a react-transition-group
 * `Transition` with no `nodeRef`, so the first time `loading` flips the library
 * calls `ReactDOM.findDOMNode` — removed in React 19, which Next 16 brought in.
 * Every busy button in the admin threw `findDOMNode is not a function` on the
 * click that started the work: upload-and-index, test search, playground run,
 * save-as-default, create-user.
 *
 * So the spinner is drawn here and `loading` is never handed to Tremor. `in`
 * stays false for the life of the button, the transition never enters, and the
 * styling stays Tremor's. Tremor 3.x is deprecated upstream and will not fix
 * this; when the admin moves off Tremor this wrapper goes with it.
 */

import { Button } from "@tremor/react";
import type { ComponentProps, ReactNode } from "react";

type TremorButtonProps = ComponentProps<typeof Button>;

export type LoadingButtonProps = Omit<
  TremorButtonProps,
  "loading" | "loadingText"
> & {
  loading?: boolean;
  children?: ReactNode;
};

export function LoadingButton({
  loading = false,
  disabled = false,
  children,
  ...rest
}: LoadingButtonProps) {
  return (
    <Button {...rest} disabled={disabled || loading} aria-busy={loading}>
      <span className="flex items-center gap-1.5">
        {loading && (
          <span
            aria-hidden="true"
            className="h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent opacity-70"
          />
        )}
        {children}
      </span>
    </Button>
  );
}
