"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AnswerText } from "@/components/AnswerText";
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
  const [menuOpen, setMenuOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  // The in-flight stream. `streamId` is bumped whenever a stream starts or is
  // cancelled, so callbacks from a stream the user has already abandoned
  // (new chat, switched room, deleted room, unmounted) are ignored instead of
  // appending its tokens onto whatever is on screen now.
  const abortRef = useRef<(() => void) | null>(null);
  const streamIdRef = useRef(0);
  // Same idea for opening a room: a slow fetch for room A must not overwrite
  // room B, which the user opened afterwards.
  const openSeqRef = useRef(0);

  const stopStream = useCallback(() => {
    streamIdRef.current += 1;
    abortRef.current?.();
    abortRef.current = null;
    setStreaming(false);
    setBubbles((prev) =>
      prev.some((b) => b.pending)
        ? prev.map((b) => (b.pending ? { ...b, pending: false } : b))
        : prev,
    );
  }, []);

  useEffect(
    () => () => {
      streamIdRef.current += 1;
      abortRef.current?.();
      abortRef.current = null;
    },
    [],
  );

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

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

  const openConversation = useCallback(
    async (id: string) => {
      stopStream();
      const seq = ++openSeqRef.current;
      setActiveId(id);
      setError("");
      try {
        const detail = await api.getConversation(id);
        if (openSeqRef.current !== seq) return;
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
        if (openSeqRef.current !== seq) return;
        setError((err as Error).message);
      }
    },
    [stopStream],
  );

  async function send(text: string) {
    const message = text.trim();
    if (!message || streaming) return;

    setError("");
    setInput("");
    setStreaming(true);

    // Taken before the first await: if the user starts a new chat while the
    // room is still being created, stopStream() bumps the id and everything
    // below becomes a no-op.
    const streamId = ++streamIdRef.current;
    const isCurrent = () => streamIdRef.current === streamId;

    let conversationId = activeId;
    try {
      if (!conversationId) {
        const created = await api.createConversation();
        if (!isCurrent()) return;
        conversationId = created.id;
        setActiveId(created.id);
        setConversations((prev) => [created, ...prev]);
      }
    } catch (err) {
      if (!isCurrent()) return;
      setError((err as Error).message);
      setStreaming(false);
      return;
    }

    setBubbles((prev) => [
      ...prev,
      { role: "user", content: message },
      { role: "assistant", content: "", pending: true, tools: [] },
    ]);

    // Patch the pending assistant bubble. A no-op when there is none - the
    // list may have been cleared by "new chat" / delete while a delta was
    // already queued, and patching `undefined` used to crash the whole page.
    const updateLast = (patch: (bubble: Bubble) => Bubble) =>
      setBubbles((prev) => {
        const last = prev[prev.length - 1];
        if (!last || last.role !== "assistant" || !last.pending) return prev;
        const next = [...prev];
        next[next.length - 1] = patch(last);
        return next;
      });

    const finish = () => {
      abortRef.current = null;
      setStreaming(false);
    };

    abortRef.current = streamChat(conversationId, message, {
      onSources: (citations) => {
        if (isCurrent()) setSources(citations);
      },
      onDelta: (chunk) => {
        if (!isCurrent()) return;
        updateLast((bubble) => ({ ...bubble, content: bubble.content + chunk }));
      },
      onTool: (name) => {
        if (!isCurrent()) return;
        updateLast((bubble) => ({
          ...bubble,
          tools: [...(bubble.tools ?? []), name],
        }));
      },
      onDone: ({ text: full, citations }) => {
        if (!isCurrent()) return;
        updateLast((bubble) => ({
          ...bubble,
          content: full || bubble.content,
          citations,
          pending: false,
        }));
        // Narrow the panel from "passages consulted" to "passages actually
        // cited" - the backend filters these by the [Sn] markers in the answer.
        setSources(citations);
        finish();
      },
      onError: (message) => {
        if (!isCurrent()) return;
        setError(message);
        updateLast((bubble) => ({ ...bubble, pending: false }));
        finish();
      },
    });
  }

  function startNew() {
    stopStream();
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

  const sidebarProps = {
    conversations,
    activeId,
    onNew: startNew,
    onOpen: openConversation,
    onRemove: removeConversation,
    onLogout: logout,
  };

  return (
    <div className="flex h-dvh">
      {/* sidebar (desktop) */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-border bg-surface p-4 md:flex">
        <Sidebar {...sidebarProps} />
      </aside>

      {/* sidebar (mobile drawer) - same content, shown over the chat */}
      {menuOpen && (
        <div
          className="fixed inset-0 z-40 flex md:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="เมนู"
        >
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setMenuOpen(false)}
            aria-hidden
          />
          <aside className="relative flex h-full w-72 max-w-[85vw] flex-col border-r border-border bg-surface p-4">
            <Sidebar {...sidebarProps} onNavigate={() => setMenuOpen(false)} />
          </aside>
        </div>
      )}

      {/* conversation */}
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border px-4 py-3.5 md:px-6">
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              aria-label="เปิดเมนู"
              aria-expanded={menuOpen}
              className="-ml-1 flex h-8 w-8 items-center justify-center rounded-sm border border-border text-muted transition hover:border-accent hover:text-foreground md:hidden"
            >
              <MenuIcon className="h-4 w-4" />
            </button>
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-cta text-cta-foreground">
              <LeafIcon className="h-3.5 w-3.5" />
            </span>
            <span className="text-sm font-medium">โค้ชนัท</span>
          </div>
          <Link href="/profile" className="text-sm text-accent hover:underline md:hidden">
            โปรไฟล์
          </Link>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto p-4 md:p-6">
          {bubbles.length === 0 && (
            <div className="mx-auto max-w-lg pt-16">
              <h2 className="font-display text-3xl font-bold leading-snug tracking-tight">
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
                    className="group flex items-center justify-between rounded-md border border-border bg-surface px-5 py-3.5 text-left text-sm transition hover:border-accent hover:bg-accent-soft/40"
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
            <p className="rounded-sm border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600">
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
          <div className="flex items-center gap-2 rounded-md border border-border bg-surface p-1.5 pl-5 transition focus-within:border-accent">
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="พิมพ์คำถามเรื่องอาหารและโภชนาการ…"
              className="min-w-0 flex-1 bg-transparent py-2 outline-none placeholder:text-muted"
            />
            <button
              type="submit"
              disabled={streaming || !input.trim()}
              className="shrink-0 rounded-sm bg-cta px-6 py-2.5 font-medium text-cta-foreground transition hover:opacity-85 active:scale-[0.98] disabled:opacity-30"
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
          <h2 className="field-label text-xs text-muted">แหล่งอ้างอิงที่ใช้ตอบ</h2>
          {sources.length > 0 && (
            <span className="text-xs text-muted">
              <span className="stat-figure">{sources.length}</span> แหล่ง
            </span>
          )}
        </div>

        {sources.length === 0 ? (
          <p className="mt-3 rounded-md bg-surface-sunken px-4 py-5 text-xs leading-relaxed text-muted">
            ยังไม่มีแหล่งอ้างอิง — จะแสดงเมื่อบอทตอบคำถามที่ใช้ฐานความรู้
          </p>
        ) : (
          <ul className="mt-4 space-y-2.5">
            {sources.map((source) => (
              <li
                key={source.label}
                className="rounded-md border border-border bg-surface-sunken p-4 transition hover:border-accent/40"
              >
                <div className="flex items-start gap-2.5">
                  <span className="stat-figure mt-0.5 shrink-0 rounded-sm bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent">
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
                  <div className="h-1 flex-1 overflow-hidden rounded-sm bg-accent-soft">
                    <div
                      className="h-full bg-accent"
                      style={{ width: `${Math.min(source.score * 100, 100)}%` }}
                    />
                  </div>
                  <span className="stat-figure shrink-0 text-[11px] text-muted">
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

/**
 * Room list + navigation. Rendered twice: inside the fixed desktop sidebar and
 * inside the mobile drawer. `onNavigate` is called after any action so the
 * drawer can close itself; the desktop sidebar leaves it undefined.
 */
function Sidebar({
  conversations,
  activeId,
  onNew,
  onOpen,
  onRemove,
  onLogout,
  onNavigate,
}: {
  conversations: Conversation[];
  activeId: string | null;
  onNew: () => void;
  onOpen: (id: string) => void;
  onRemove: (id: string) => void;
  onLogout: () => void;
  onNavigate?: () => void;
}) {
  const navLink =
    "block rounded-sm px-3 py-2 text-muted transition hover:bg-surface-sunken hover:text-foreground";

  return (
    <>
      <div className="flex items-center gap-2.5 px-1 pb-4 pt-1">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-cta text-cta-foreground">
          <LeafIcon className="h-4 w-4" />
        </span>
        <span className="font-display text-lg font-bold tracking-tight">NutriLift</span>
      </div>

      <button
        onClick={() => {
          onNew();
          onNavigate?.();
        }}
        className="rounded-md bg-cta py-2.5 text-sm font-medium text-cta-foreground transition hover:opacity-85 active:scale-[0.98]"
      >
        + แชตใหม่
      </button>

      <nav className="mt-5 flex-1 space-y-0.5 overflow-y-auto">
        {conversations.map((conversation) => (
          <div
            key={conversation.id}
            className={`group flex items-center gap-1 rounded-sm pr-1 transition ${
              activeId === conversation.id
                ? "bg-accent-soft text-accent"
                : "text-muted hover:bg-surface-sunken hover:text-foreground"
            }`}
          >
            <button
              onClick={() => {
                onOpen(conversation.id);
                onNavigate?.();
              }}
              className="min-w-0 flex-1 truncate px-3 py-2 text-left text-sm"
            >
              {conversation.title}
            </button>
            <button
              onClick={() => onRemove(conversation.id)}
              aria-label={`ลบห้องแชต ${conversation.title}`}
              title="ลบห้องแชตนี้"
              className={`shrink-0 rounded-sm px-2 py-1 text-xs transition hover:bg-red-500/10 hover:text-red-500 focus:opacity-100 ${
                // No hover on touch screens, so the drawer shows the button always.
                onNavigate ? "" : "opacity-0 group-hover:opacity-100"
              }`}
            >
              ลบ
            </button>
          </div>
        ))}
      </nav>

      <div className="mt-4 space-y-0.5 border-t border-border pt-4 text-sm">
        <Link href="/log" className={navLink} onClick={onNavigate}>
          บันทึกอาหาร
        </Link>
        <Link href="/profile" className={navLink} onClick={onNavigate}>
          โปรไฟล์และเป้าหมาย
        </Link>
        <button onClick={onLogout} className={`${navLink} w-full text-left`}>
          ออกจากระบบ
        </button>
      </div>
    </>
  );
}

function MessageBubble({ bubble }: { bubble: Bubble }) {
  if (bubble.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="min-w-0 max-w-[80%] rounded-lg rounded-br-sm bg-cta px-5 py-3 text-cta-foreground wrap-anywhere">
          {bubble.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="min-w-0 max-w-[85%] rounded-lg rounded-bl-sm border border-border bg-surface px-5 py-4 wrap-anywhere">
        {bubble.tools?.map((tool, index) => (
          <div
            key={index}
            className="mb-2.5 inline-flex items-center gap-1.5 rounded-sm bg-accent-soft px-3 py-1 text-xs text-accent"
          >
            <span className="animate-pulse">⚙</span>
            {TOOL_LABELS[tool] ?? tool}
          </div>
        ))}

        <div>
          <AnswerText content={bubble.content} />
          {bubble.pending && <span className="animate-pulse">▌</span>}
        </div>

        {bubble.citations && bubble.citations.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5 border-t border-border pt-3">
            {bubble.citations.map((citation) => (
              <span
                key={citation.label}
                className="rounded-sm bg-surface-sunken px-2.5 py-1 text-[11px] text-muted"
              >
                <span className="stat-figure font-medium text-accent">[{citation.label}]</span>{" "}
                {citation.title}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MenuIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  );
}

function LeafIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.9}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z" />
      <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12" />
    </svg>
  );
}
