/**
 * Backend API client.
 *
 * The chat endpoint streams Server-Sent Events over a POST, which EventSource
 * cannot do (it is GET-only and cannot send an Authorization header), so the
 * stream is read manually from the fetch body reader.
 */

function resolveApiBase(): string {
  // Trailing slashes are stripped so `${API_BASE}/auth/login` never becomes
  // `http://host//auth/login`.
  const configured = (process.env.NEXT_PUBLIC_API_BASE ?? "").trim().replace(/\/+$/, "");
  if (configured) return configured;
  if (process.env.NODE_ENV === "production") {
    // Fail `next build` loudly rather than silently baking localhost:8000 into
    // a production bundle that then cannot reach the backend.
    throw new Error(
      "NEXT_PUBLIC_API_BASE is not set. Set it to the backend URL (e.g. https://api.example.com) before building for production.",
    );
  }
  return "http://localhost:8000";
}

export const API_BASE = resolveApiBase();

const TOKEN_KEY = "nutrition_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode / storage blocked - the session just won't persist */
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/**
 * A 401 outside `/auth/` means the stored token is expired or revoked (the
 * backend issues 7-day tokens): drop it and send the user back to the login
 * page instead of leaving every request failing with an opaque error.
 * `/auth/login` legitimately answers 401 for a wrong password, so the whole
 * `/auth/` prefix is exempt.
 */
function handleUnauthorized(path: string, status: number): void {
  if (status !== 401 || path.startsWith("/auth/")) return;
  setToken(null);
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    // A full navigation, not the router: this module has no access to it, and
    // a hard reload also drops any in-memory state that belonged to the old
    // session.
    window.location.assign(new URL("/login", window.location.origin).href);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    handleUnauthorized(path, response.status);
    let detail = `เกิดข้อผิดพลาด (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// --- types ---------------------------------------------------------------

export type Profile = {
  sex: "male" | "female";
  birth_year: number;
  /** 1-12. Null only on rows saved before the field existed; required on save. */
  birth_month: number | null;
  height_cm: number;
  weight_kg: number;
  body_fat_pct: number | null;
  activity_level: "sedentary" | "light" | "moderate" | "active" | "very_active";
  training_days: number;
  goal: "cut" | "bulk" | "maintain";
  restrictions: string[];
};

export type Targets = {
  bmr_kcal: number;
  bmr_formula: string;
  tdee_kcal: number;
  energy_target_kcal: number;
  energy_target_range_kcal: [number, number];
  macros: {
    protein_g: number;
    carb_g: number;
    fat_g: number;
    protein_kcal: number;
    carb_kcal: number;
    fat_kcal: number;
  };
  warnings: string[];
  references: string[];
  disclaimer: string;
  inputs: { goal: "cut" | "bulk" | "maintain"; goal_label_th: string; activity_label_th: string };
  /** kg/m². Only the low side is used for advice - see nutrition.py BMI_UNDERWEIGHT. */
  bmi: number;
  underweight: boolean;
  /** Goal the numbers were actually built from. Differs from inputs.goal when a
   *  cut was downgraded to maintenance (underweight). */
  effective_goal: "cut" | "bulk" | "maintain";
  effective_goal_label_th: string;
  deficit_suppressed_reason: "underweight" | null;
};

export type Citation = {
  label: string;
  title: string;
  heading: string | null;
  document_slug: string;
  score: number;
  source_refs: string[] | null;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
  tool_calls: { name: string }[] | null;
  created_at: string;
};

export type Conversation = {
  id: string;
  title: string;
  created_at: string;
};

export type ConversationDetail = Conversation & { messages: ChatMessage[] };

export type FoodSearchResult = {
  id: string;
  name_th: string;
  name_en: string | null;
  category: string | null;
  serving_desc: string;
  serving_g: number;
  kcal: number;
  protein_g: number;
  carb_g: number;
  fat_g: number;
  fiber_g: number | null;
};

export type MealType = "breakfast" | "lunch" | "dinner" | "snack";

export type FoodLogEntry = {
  id: string;
  food_id: string | null;
  food_name_th: string;
  serving_desc: string;
  serving_g: number;
  serving_kcal: number;
  serving_protein_g: number;
  serving_carb_g: number;
  serving_fat_g: number;
  quantity_servings: number;
  meal_type: MealType;
  logged_date: string;
  total_kcal: number;
  total_protein_g: number;
  total_carb_g: number;
  total_fat_g: number;
  created_at: string;
};

export type MacroTotals = {
  kcal: number;
  protein_g: number;
  carb_g: number;
  fat_g: number;
};

export type DailySummary = {
  date: string;
  entries_count: number;
  consumed: MacroTotals;
  target: MacroTotals | null;
  remaining: MacroTotals | null;
  by_meal: Record<MealType, MacroTotals>;
};

// --- endpoints -----------------------------------------------------------

export const api = {
  /** `consent` is not optional and has no default, mirroring RegisterRequest:
   *  the server rejects a registration that does not carry both assertions, so
   *  making them easy to forget here would only move the failure later. */
  register: (
    email: string,
    password: string,
    consent: { accepted_terms: boolean; is_adult: boolean },
  ) =>
    request<{ access_token: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, ...consent }),
    }),

  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<{ id: string; email: string }>("/auth/me"),

  getProfile: () => request<Profile>("/profile"),

  saveProfile: (profile: Profile) =>
    request<Profile>("/profile", {
      method: "PUT",
      body: JSON.stringify(profile),
    }),

  getTargets: () => request<Targets>("/profile/targets"),

  listConversations: () => request<Conversation[]>("/conversations"),

  createConversation: () =>
    request<Conversation>("/conversations", { method: "POST" }),

  getConversation: (id: string) =>
    request<ConversationDetail>(`/conversations/${id}`),

  deleteConversation: (id: string) =>
    request<void>(`/conversations/${id}`, { method: "DELETE" }),

  searchFoods: (q: string, limit = 20) =>
    request<FoodSearchResult[]>(
      `/foods/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    ),

  listFoodLog: (date: string) =>
    request<FoodLogEntry[]>(`/food-log?date=${date}`),

  getFoodLogSummary: (date: string) =>
    request<DailySummary>(`/food-log/summary?date=${date}`),

  addFoodLogEntry: (entry: {
    food_id: string;
    quantity_servings: number;
    meal_type: MealType;
    logged_date: string;
  }) =>
    request<FoodLogEntry>("/food-log", {
      method: "POST",
      body: JSON.stringify(entry),
    }),

  updateFoodLogEntry: (
    id: string,
    changes: Partial<Pick<FoodLogEntry, "quantity_servings" | "meal_type">>,
  ) =>
    request<FoodLogEntry>(`/food-log/${id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),

  deleteFoodLogEntry: (id: string) =>
    request<void>(`/food-log/${id}`, { method: "DELETE" }),
};

// --- streaming chat ------------------------------------------------------

export type ChatStreamHandlers = {
  onSources?: (citations: Citation[]) => void;
  onDelta?: (text: string) => void;
  onTool?: (name: string) => void;
  onDone?: (payload: { text: string; citations: Citation[] }) => void;
  onError?: (message: string) => void;
};

export type SSEFrame = { event: string; payload: Record<string, unknown> };

/** Shown when the SSE stream ends before the server sent `done` or `error`. */
export const STREAM_CUT_MESSAGE =
  "การเชื่อมต่อถูกตัดก่อนคำตอบจะจบ กรุณาลองใหม่อีกครั้ง";

/**
 * Split a raw SSE buffer into complete frames.
 *
 * Frames are separated by a blank line, but a network chunk can end anywhere -
 * mid-frame, mid-line, or even mid-UTF-8-character. Whatever follows the last
 * blank line is therefore incomplete and is handed back as `rest` to be
 * prepended to the next chunk.
 *
 * Line endings are normalised first because the server (sse-starlette) writes
 * CRLF: a parser that splits on "\n\n" alone finds zero frames in its output
 * and the chat silently renders nothing at all. Normalising the whole buffer
 * on every call also handles a chunk that ends between the CR and the LF - the
 * lone CR survives in `rest` and pairs up with the LF that starts the next one.
 *
 * Split out of `streamChat` so this can be unit-tested against realistic chunk
 * boundaries; it is the one piece of the client that a passing type-check does
 * not exercise at all.
 */
export function parseSSEFrames(buffer: string): {
  frames: SSEFrame[];
  rest: string;
} {
  const parts = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const rest = parts.pop() ?? "";
  const frames: SSEFrame[] = [];

  for (const part of parts) {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of part.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) continue;

    try {
      frames.push({ event, payload: JSON.parse(dataLines.join("\n")) });
    } catch {
      // A frame we cannot parse is dropped rather than killing the stream.
    }
  }

  return { frames, rest };
}

/**
 * POST a message and consume the SSE response.
 * Returns an abort function.
 */
export function streamChat(
  conversationId: string,
  message: string,
  handlers: ChatStreamHandlers,
  useRag = true,
): () => void {
  const controller = new AbortController();
  const path = `/conversations/${conversationId}/chat`;

  (async () => {
    try {
      const token = getToken();
      const response = await fetch(
        `${API_BASE}${path}`,
        {
          method: "POST",
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ message, use_rag: useRag }),
        },
      );

      if (!response.ok || !response.body) {
        handleUnauthorized(path, response.status);
            // The server explains rate limits and quota exhaustion in `detail`;
        // showing only the status code would leave the user with no idea how
        // long to wait or what went wrong.
        let detail = `เชื่อมต่อไม่สำเร็จ (${response.status})`;
        try {
          const body = await response.json();
          if (typeof body?.detail === "string") detail = body.detail;
        } catch {
          /* not a JSON error body */
        }
        const retryAfter = Number(response.headers.get("Retry-After"));
        if (Number.isFinite(retryAfter) && retryAfter > 0) {
          const minutes = Math.ceil(retryAfter / 60);
          detail += ` (ลองใหม่ได้ในอีกประมาณ ${minutes} นาที)`;
        }
        handlers.onError?.(detail);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      // Set once a terminal frame (`done` or `error`) has been dispatched. A
      // stream that hits EOF without one - proxy timeout, backend crash
      // mid-answer, dropped connection - would otherwise end silently and leave
      // the composer disabled forever.
      let finished = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const { frames, rest } = parseSSEFrames(buffer);
        buffer = rest;

        for (const { event: eventName, payload } of frames) {
          switch (eventName) {
            case "sources":
              handlers.onSources?.((payload.sources ?? []) as Citation[]);
              break;
            case "delta":
              handlers.onDelta?.(String(payload.text ?? ""));
              break;
            case "tool":
              handlers.onTool?.(String(payload.name ?? ""));
              break;
            case "done":
              finished = true;
              handlers.onDone?.({
                text: String(payload.text ?? ""),
                citations: (payload.citations ?? []) as Citation[],
              });
              break;
            case "error":
              finished = true;
              handlers.onError?.(String(payload.message ?? "เกิดข้อผิดพลาด"));
              break;
          }
        }
      }

      if (!finished && !controller.signal.aborted) {
        handlers.onError?.(STREAM_CUT_MESSAGE);
      }
    } catch (error) {
      if ((error as Error).name !== "AbortError") {
        handlers.onError?.((error as Error).message);
      }
    }
  })();

  return () => controller.abort();
}
