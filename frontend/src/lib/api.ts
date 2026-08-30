/**
 * Backend API client.
 *
 * The chat endpoint streams Server-Sent Events over a POST, which EventSource
 * cannot do (it is GET-only and cannot send an Authorization header), so the
 * stream is read manually from the fetch body reader.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

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
  inputs: { goal_label_th: string; activity_label_th: string };
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

// --- endpoints -----------------------------------------------------------

export const api = {
  register: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
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
};

// --- streaming chat ------------------------------------------------------

export type ChatStreamHandlers = {
  onSources?: (citations: Citation[]) => void;
  onDelta?: (text: string) => void;
  onTool?: (name: string) => void;
  onDone?: (payload: { text: string; citations: Citation[] }) => void;
  onError?: (message: string) => void;
};

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

  (async () => {
    try {
      const token = getToken();
      const response = await fetch(
        `${API_BASE}/conversations/${conversationId}/chat`,
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
        handlers.onError?.(`เชื่อมต่อไม่สำเร็จ (${response.status})`);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE frames are separated by a blank line.
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";

        for (const frame of frames) {
          let eventName = "message";
          const dataLines: string[] = [];
          for (const line of frame.split("\n")) {
            if (line.startsWith("event:")) eventName = line.slice(6).trim();
            else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
          }
          if (!dataLines.length) continue;

          let payload: Record<string, unknown>;
          try {
            payload = JSON.parse(dataLines.join("\n"));
          } catch {
            continue;
          }

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
              handlers.onDone?.({
                text: String(payload.text ?? ""),
                citations: (payload.citations ?? []) as Citation[],
              });
              break;
            case "error":
              handlers.onError?.(String(payload.message ?? "เกิดข้อผิดพลาด"));
              break;
          }
        }
      }
    } catch (error) {
      if ((error as Error).name !== "AbortError") {
        handlers.onError?.((error as Error).message);
      }
    }
  })();

  return () => controller.abort();
}
