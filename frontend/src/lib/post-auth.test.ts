import assert from "node:assert/strict";
import { test } from "node:test";
import { api, ApiError } from "./api.ts";
import { postAuthDestination } from "./post-auth.ts";

test("post-auth routes respect verification, consent, saved profile and failures", async () => {
  const originalMe = api.me, originalProfile = api.getProfile;
  let verified = true, consent = false, status = 404, profileCalls = 0;
  api.me = async () => ({ email_verified: verified, needs_consent: consent } as Awaited<ReturnType<typeof api.me>>);
  api.getProfile = async () => {
    profileCalls++;
    if (status) throw new ApiError(status, "profile failed");
    return {} as Awaited<ReturnType<typeof api.getProfile>>;
  };
  try {
    verified = false;
    assert.equal(await postAuthDestination(), "/verify-email");
    verified = true; consent = true;
    assert.equal(await postAuthDestination(), "/consent");
    assert.equal(profileCalls, 0);
    consent = false;
    assert.equal(await postAuthDestination(), "/profile");
    status = 0;
    assert.equal(await postAuthDestination(), "/chat");
    for (status of [401, 403, 500]) await assert.rejects(postAuthDestination(), ApiError);
    api.getProfile = async () => { throw new TypeError("network unavailable"); };
    await assert.rejects(postAuthDestination(), /network unavailable/);
  } finally { api.me = originalMe; api.getProfile = originalProfile; }
});
