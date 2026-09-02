"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  api,
  getToken,
  setToken,
  streamChat,
  type Citation,
  type Conversation,
  type ChatMessage,
} from "@/lib/api";

type Bubble = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  tools?: string[];
  pending?: boolean;
};

const TOOL_LABELS: Record<string, string> = {
  calc_nutrition_targets: "กำลังคำนวณพลังงานและสารอาหาร…",
  lookup_food: "กำลังค้นฐานข้อมูลอาหาร…",
};

const SUGGESTIONS = [
  "ควรกินโปรตีนวันละกี่กรัม",
  "ช่วง cut ควรลดแคลอรี่เท่าไหร่",
  "ครีเอทีนกินยังไง ต้องโหลดไหม",
  "ข้าวมันไก่ 1 จานกี่แคลอรี่",
];

export default function ChatPage() {
  const router = useRouter();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const [sources, setSources] = useState<Citation[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api
      .listConversations()
      .then(setConversations)
      .catch((err) => setError((err as Error).message));
  }, [router]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [bubbles]);

  const openConversation = useCallback(async (id: string) => {
    setActiveId(id);
    setError("");
    try {
      const detail = await api.getConversation(id);
      setBubbles(
        detail.messages.map((message: ChatMessage) => ({
          role: message.role,
          content: message.content,
          citations: message.citations ?? undefined,
        })),
      );
      const last = [...detail.messages].reverse().find((m) => m.citations?.length);
      setSources(last?.citations ?? []);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  async function send(text: string) {
    const message = text.trim();
    if (!message || streaming) return;

    setError("");
    setInput("");
    setStreaming(true);

    let conversationId = activeId;
    try {
      if (!conversationId) {
        const created = await api.createConversation();
        conversationId = created.id;
        setActiveId(created.id);
        setConversations((prev) => [created, ...prev]);
      }
    } catch (err) {
      setError((err as Error).message);
      setStreaming(false);
      return;
    }

    setBubbles((prev) => [
      ...prev,
      { role: "user", content: message },
      { role: "assistant", content: "", pending: true, tools: [] },
    ]);

    const updateLast = (patch: (bubble: Bubble) => Bubble) =>
      setBubbles((prev) => {
        const next = [...prev];
        next[next.length - 1] = patch(next[next.length - 1]);
        return next;
      });

    streamChat(conversationId!, message, {
      onSources: (citations) => setSources(citations),
      onDelta: (chunk) =>
        updateLast((bubble) => ({ ...bubble, content: bubble.content + chunk })),
      onTool: (name) =>
        updateLast((bubble) => ({
          ...bubble,
          tools: [...(bubble.tools ?? []), name],
        })),
      onDone: ({ text: full, citations }) => {
        updateLast((bubble) => ({
          ...bubble,
          content: full || bubble.content,
          citations,
          pending: false,
        }));
        // Narrow the panel from "passages consulted" to "passages actually
        // cited" - the backend filters these by the [Sn] markers in the answer.
        setSources(citations);
        setStreaming(false);
      },
      onError: (message) => {
        setError(message);
        updateLast((bubble) => ({ ...bubble, pending: false }));
        setStreaming(false);
      },
    });
  }

  function startNew() {
    setActiveId(null);
    setBubbles([]);
    setSources([]);
    setError("");
  }

  async function removeConversation(id: string) {
    // Deliberately not window.confirm(): a native modal blocks the whole page.
    // The row is removed optimistically and restored if the request fails.
    const previous = conversations;
    setConversations((list) => list.filter((c) => c.id !== id));
    if (activeId === id) startNew();

    try {
      await api.deleteConversation(id);
    } catch (err) {
      setConversations(previous);
      setError(`ลบห้องแชตไม่สำเร็จ: ${(err as Error).message}`);
    }
  }

  function logout() {
    setToken(null);
    router.replace("/login");
  }

  return (
    <div className="flex h-screen">
      {/* sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-border bg-surface p-4 md:flex">
        <div className="px-1 pb-4 pt-1">
          <span className="text-lg font-semibold tracking-tight">NutriLift</span>
        </div>

        <button
          onClick={startNew}
          className="rounded-full bg-cta py-2.5 text-sm font-medium text-cta-foreground transition hover:opacity-85 active:scale-[0.98]"
        >
          + แชตใหม่
        </button>

        <nav className="mt-5 flex-1 space-y-0.5 overflow-y-auto">
          {conversations.map((conversation) => (
            <div
              key={conversation.id}
              className={`group flex items-center gap-1 rounded-xl pr-1 transition ${
                activeId === conversation.id
                  ? "bg-accent-soft text-accent"
                  : "text-muted hover:bg-surface-sunken hover:text-foreground"
              }`}
            >
              <button
                onClick={() => openConversation(conversation.id)}
                className="min-w-0 flex-1 truncate px-3 py-2 text-left text-sm"
              >
                {conversation.title}
              </button>
              <button
                onClick={() => removeConversation(conversation.id)}
                aria-label={`ลบห้องแชต ${conversation.title}`}
                title="ลบห้องแชตนี้"
                className="shrink-0 rounded-lg px-2 py-1 text-xs opacity-0 transition group-hover:opacity-100 hover:bg-red-500/10 hover:text-red-500 focus:opacity-100"
              >
                ลบ
              </button>
            </div>
          ))}
        </nav>

        <div className="mt-4 space-y-0.5 border-t border-border pt-4 text-sm">
          <Link
            href="/log"
            className="block rounded-xl px-3 py-2 text-muted transition hover:bg-surface-sunken hover:text-foreground"
          >
            บันทึกอาหาร
          </Link>
          <Link
            href="/profile"
            className="block rounded-xl px-3 py-2 text-muted transition hover:bg-surface-sunken hover:text-foreground"
          >
            โปรไฟล์และเป้าหมาย
          </Link>
          <button
            onClick={logout}
            className="block w-full rounded-xl px-3 py-2 text-left text-muted transition hover:bg-surface-sunken hover:text-foreground"
          >
            ออกจากระบบ
          </button>
        </div>
      </aside>

      {/* conversation */}
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border px-6 py-3.5">
          <div className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent-soft text-sm">
              🥗
            </span>
            <span className="text-sm font-medium">โค้ชนัท</span>
          </div>
          <Link href="/profile" className="text-sm text-accent hover:underline md:hidden">
            โปรไฟล์
          </Link>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto p-6">
          {bubbles.length === 0 && (
            <div className="mx-auto max-w-lg pt-16">
              <h2 className="text-3xl font-semibold leading-snug tracking-tight">
                วันนี้อยากรู้เรื่องอะไร
                <br />
                เกี่ยวกับโภชนาการ
              </h2>
              <p className="mt-3 text-sm text-muted">
                คำตอบอ้างอิงจากฐานความรู้ที่คัดมา และตัวเลขคำนวณจากโปรไฟล์ของคุณ
              </p>
              <div className="mt-8 grid gap-2.5">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => send(suggestion)}
                    className="group flex items-center justify-between rounded-2xl border border-border bg-surface px-5 py-3.5 text-left text-sm transition hover:border-accent hover:bg-accent-soft/40"
                  >
                    <span>{suggestion}</span>
                    <span className="text-muted transition group-hover:translate-x-0.5 group-hover:text-accent">
                      →
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {bubbles.map((bubble, index) => (
            <MessageBubble key={index} bubble={bubble} />
          ))}

          {error && (
            <p className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600">
              {error}
            </p>
          )}
          <div ref={bottomRef} />
        </div>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            send(input);
          }}
          className="p-4"
        >
          <div className="flex items-center gap-2 rounded-full border border-border bg-surface p-1.5 pl-5 transition focus-within:border-accent">
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="พิมพ์คำถามเรื่องอาหารและโภชนาการ…"
              className="min-w-0 flex-1 bg-transparent py-2 outline-none placeholder:text-muted"
            />
            <button
              type="submit"
              disabled={streaming || !input.trim()}
              className="shrink-0 rounded-full bg-cta px-6 py-2.5 font-medium text-cta-foreground transition hover:opacity-85 active:scale-[0.98] disabled:opacity-30"
            >
              ส่ง
            </button>
          </div>
          <p className="mt-3 text-center text-xs text-muted">
            ข้อมูลเพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำทางการแพทย์
          </p>
        </form>
      </main>

      {/* sources */}
      <aside className="hidden w-80 shrink-0 overflow-y-auto border-l border-border bg-surface p-5 lg:block">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-semibold">แหล่งอ้างอิงที่ใช้ตอบ</h2>
          {sources.length > 0 && (
            <span className="text-xs text-muted">{sources.length} แหล่ง</span>
          )}
        </div>

        {sources.length === 0 ? (
          <p className="mt-3 rounded-2xl bg-surface-sunken px-4 py-5 text-xs leading-relaxed text-muted">
            ยังไม่มีแหล่งอ้างอิง — จะแสดงเมื่อบอทตอบคำถามที่ใช้ฐานความรู้
          </p>
        ) : (
          <ul className="mt-4 space-y-2.5">
            {sources.map((source) => (
              <li
                key={source.label}
                className="rounded-2xl border border-border bg-surface-sunken p-4 transition hover:border-accent/40"
              >
                <div className="flex items-start gap-2.5">
                  <span className="mt-0.5 shrink-0 rounded-lg bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent">
                    {source.label}
                  </span>
                  <span className="text-sm font-medium leading-snug">
                    {source.title}
                  </span>
                </div>

                {source.heading && (
                  <div className="mt-2 text-xs leading-relaxed text-muted">
                    {source.heading}
                  </div>
                )}

                {/* Relevance as a bar, not just a number - easier to compare
                    across sources at a glance. */}
                <div className="mt-3 flex items-center gap-2">
                  <div className="h-1 flex-1 overflow-hidden rounded-full bg-accent-soft">
                    <div
                      className="h-full rounded-full bg-accent"
                      style={{ width: `${Math.min(source.score * 100, 100)}%` }}
                    />
                  </div>
                  <span className="shrink-0 text-[11px] text-muted tabular-nums">
                    {(source.score * 100).toFixed(0)}%
                  </span>
                </div>

                {source.source_refs && source.source_refs.length > 0 && (
                  <ul className="mt-3 space-y-1 border-t border-border pt-3 text-[11px] leading-relaxed text-muted">
                    {source.source_refs.map((reference) => (
                      <li key={reference}>{reference}</li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}

function MessageBubble({ bubble }: { bubble: Bubble }) {
  if (bubble.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-3xl rounded-br-lg bg-cta px-5 py-3 text-cta-foreground">
          {bubble.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-3xl rounded-bl-lg border border-border bg-surface px-5 py-4">
        {bubble.tools?.map((tool, index) => (
          <div
            key={index}
            className="mb-2.5 inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-3 py-1 text-xs text-accent"
          >
            <span className="animate-pulse">⚙</span>
            {TOOL_LABELS[tool] ?? tool}
          </div>
        ))}

        <div className="whitespace-pre-wrap leading-relaxed">
          {bubble.content}
          {bubble.pending && <span className="animate-pulse">▌</span>}
        </div>

        {bubble.citations && bubble.citations.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5 border-t border-border pt-3">
            {bubble.citations.map((citation) => (
              <span
                key={citation.label}
                className="rounded-lg bg-surface-sunken px-2.5 py-1 text-[11px] text-muted"
              >
                <span className="font-medium text-accent">[{citation.label}]</span>{" "}
                {citation.title}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
