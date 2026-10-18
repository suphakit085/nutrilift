"use client";

import { useSyncExternalStore } from "react";

function subscribe(listener: () => void) {
  window.addEventListener("hashchange", listener);
  return () => window.removeEventListener("hashchange", listener);
}

export function useEmailLinkToken(): string {
  const fragment = useSyncExternalStore(subscribe, () => window.location.hash, () => "");
  return new URLSearchParams(fragment.slice(1)).get("token") ?? "";
}

export function clearEmailLinkToken() {
  window.history.replaceState(null, "", window.location.pathname);
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}
