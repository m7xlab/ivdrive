"use client";

import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

/**
 * False while rendering on the server and during hydration, true on the client afterwards.
 * Use it to hold back content that differs between the two (theme, window size, maps).
 * Same result as `useState(false)` + an effect that flips it, without the extra render and without
 * calling setState inside an effect.
 */
export function useMounted(): boolean {
  return useSyncExternalStore(subscribe, () => true, () => false);
}
