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

  function logout() {
    setToken(null);
    router.replace("/login");
  }

  return (
    <div className="flex h-screen">
      {/* sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-border bg-surface p-4 md:flex">
        <button
          onClick={startNew}
          className="rounded-lg bg-accent py-2 text-sm font-medium text-white transition hover:opacity-90"
        >
          + แชตใหม่
        </button>

        <nav className="mt-4 flex-1 space-y-1 overflow-y-auto">
          {conversations.map((conversation) => (
            <button
              key={conversation.id}
              onClick={() => openConversation(conversation.id)}
              className={`w-full truncate rounded-lg px-3 py-2 text-left text-sm transition ${
                activeId === conversation.id
                  ? "bg-accent-soft text-accent"
                  : "text-muted hover:bg-background hover:text-foreground"
              }`}
            >
              {conversation.title}
            </button>
          ))}
        </nav>

        <div className="mt-4 space-y-1 border-t border-border pt-4 text-sm">
          <Link
            href="/profile"
            className="block rounded-lg px-3 py-2 text-muted transition hover:text-foreground"
          >
            โปรไฟล์และเป้าหมาย
          </Link>
          <button
            onClick={logout}
            className="block w-full rounded-lg px-3 py-2 text-left text-muted transition hover:text-foreground"
          >
            ออกจากระบบ
          </button>
        </div>
      </aside>

      {/* conversation */}
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border px-6 py-3">
          <h1 className="font-semibold">โค้ชนัท</h1>
          <Link href="/profile" className="text-sm text-accent hover:underline md:hidden">
            โปรไฟล์
          </Link>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto p-6">
          {bubbles.length === 0 && (
            <div className="mx-auto max-w-lg pt-12 text-center">
              <h2 className="text-lg font-semibold">ถามเรื่องโภชนาการสำหรับเวทเทรนนิ่งได้เลย</h2>
              <p className="mt-2 text-sm text-muted">
                คำตอบอ้างอิงจากฐานความรู้ที่คัดมา และตัวเลขคำนวณจากโปรไฟล์ของคุณ
              </p>
              <div className="mt-6 grid gap-2">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => send(suggestion)}
                    className="rounded-lg border border-border px-4 py-2.5 text-left text-sm transition hover:border-accent"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          {bubbles.map((bubble, index) => (
            <MessageBubble key={index} bubble={bubble} />
          ))}

          {error && (
            <p className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-500">
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
          className="border-t border-border p-4"
        >
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="พิมพ์คำถามเรื่องอาหารและโภชนาการ…"
              className="flex-1 rounded-lg border border-border bg-surface px-4 py-2.5 outline-none focus:border-accent"
            />
            <button
              type="submit"
              disabled={streaming || !input.trim()}
              className="rounded-lg bg-accent px-5 py-2.5 font-medium text-white transition hover:opacity-90 disabled:opacity-40"
            >
              ส่ง
            </button>
          </div>
          <p className="mt-2 text-center text-xs text-muted">
            ข้อมูลเพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำทางการแพทย์
          </p>
        </form>
      </main>

      {/* sources */}
      <aside className="hidden w-80 shrink-0 overflow-y-auto border-l border-border bg-surface p-4 lg:block">
        <h2 className="text-sm font-semibold">แหล่งอ้างอิงที่ใช้ตอบ</h2>
        {sources.length === 0 ? (
          <p className="mt-2 text-xs text-muted">
            ยังไม่มีแหล่งอ้างอิง — จะแสดงเมื่อบอทตอบคำถามที่ใช้ฐานความรู้
          </p>
        ) : (
          <ul className="mt-3 space-y-3">
            {sources.map((source) => (
              <li key={source.label} className="rounded-lg border border-border p-3">
                <div className="flex items-baseline gap-2">
                  <span className="rounded bg-accent-soft px-1.5 text-xs text-accent">
                    {source.label}
                  </span>
                  <span className="text-sm font-medium">{source.title}</span>
                </div>
                {source.heading && (
                  <div className="mt-1 text-xs text-muted">หัวข้อ: {source.heading}</div>
                )}
                <div className="mt-1 text-xs text-muted">
                  ความใกล้เคียง {(source.score * 100).toFixed(0)}%
                </div>
                {source.source_refs && source.source_refs.length > 0 && (
                  <ul className="mt-2 list-disc space-y-1 pl-4 text-[11px] text-muted">
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
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-accent px-4 py-2.5 text-white">
          {bubble.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-border bg-surface px-4 py-3">
        {bubble.tools?.map((tool, index) => (
          <div key={index} className="mb-2 text-xs text-muted">
            ⚙ {TOOL_LABELS[tool] ?? tool}
          </div>
        ))}

        <div className="whitespace-pre-wrap">
          {bubble.content}
          {bubble.pending && <span className="animate-pulse">▌</span>}
        </div>

        {bubble.citations && bubble.citations.length > 0 && (
          <div className="mt-3 border-t border-border pt-2 text-xs text-muted">
            อ้างอิง:{" "}
            {bubble.citations.map((citation) => (
              <span key={citation.label} className="mr-2">
                [{citation.label}] {citation.title}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
