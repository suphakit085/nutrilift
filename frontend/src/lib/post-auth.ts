import { api, ApiError } from "./api.ts";

/** Only a confirmed missing profile starts onboarding; outages must stay errors. */
export async function postAuthDestination(): Promise<string> {
  const me = await api.me();
  if (me.email_verified === false) return "/verify-email";
  if (me.needs_consent) return "/consent";
  try {
    await api.getProfile();
    return "/chat";
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return "/profile";
    throw error;
  }
}
