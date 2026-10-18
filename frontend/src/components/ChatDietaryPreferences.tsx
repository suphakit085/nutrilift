"use client";

import { useEffect, useRef, useState } from "react";
import { api, type DietaryContext } from "@/lib/api";
import { DietaryRestrictionFields } from "@/components/DietaryRestrictionFields";

export function ChatDietaryPreferences({ conversationId, onClose, onSaved }: {
  conversationId: string; onClose: () => void; onSaved: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [context, setContext] = useState<DietaryContext | null>(null);
  const [value, setValue] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => { element?.close(); };
  }, []);
  useEffect(() => {
    let cancelled = false;
    api.getDietaryPreferences(conversationId).then((result) => {
      if (!cancelled) { setContext(result); setValue(result.restrictions); setError(""); }
    }).catch((err: Error) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, [conversationId, retry]);
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!context || savingRef.current) return;
    const button = (event.nativeEvent as SubmitEvent).submitter;
    const scope = button?.getAttribute("value") === "profile" ? "profile" : "conversation";
    const confirmed = new FormData(event.currentTarget).get("confirm-allergy-changes") === "on";
    savingRef.current = true; setSaving(true); setError("");
    try {
      await api.saveDietaryPreferences(conversationId, {
        restrictions: value, scope, context_version: context.context_version,
        confirm_allergy_changes: confirmed,
      });
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally { savingRef.current = false; setSaving(false); }
  }
  return <dialog ref={dialog} aria-labelledby="dietary-title"
    onCancel={(event) => { event.preventDefault(); if (!savingRef.current) onClose(); }}
    className="m-auto max-h-[90dvh] w-[calc(100%_-_2rem)] max-w-2xl overflow-y-auto rounded-lg border border-border bg-surface p-5 text-foreground backdrop:bg-black/50">
    <div className="mb-4 flex items-start justify-between gap-3">
      <h2 id="dietary-title" className="font-display text-xl font-bold">ข้อจำกัดอาหาร</h2>
      <button type="button" disabled={saving} onClick={onClose} className="shrink-0 rounded-sm border border-border px-3 py-1">ปิด</button>
    </div>
    {!context && !error && <p role="status">กำลังโหลดข้อจำกัดอาหาร…</p>}
    {error && <div role="alert" className="mb-4 text-sm text-red-600">{error}
      <button type="button" disabled={saving} className="ml-3 underline" onClick={() => {setContext(null); setError(""); setRetry((v) => v + 1);}}>โหลดข้อมูลล่าสุด</button>
    </div>}
    {context && <form onSubmit={save}>
      <fieldset disabled={saving} className="space-y-5 disabled:opacity-60">
        <p className="text-sm text-muted">ตรวจข้อมูลที่บอตใช้ในห้องนี้ การพูดคุยยังไม่เปลี่ยนโปรไฟล์จนกว่าคุณจะเลือกบันทึก</p>
        <DietaryRestrictionFields value={value} original={context.restrictions} onChange={setValue} />
        <div className="flex flex-wrap gap-3 border-t border-border pt-4">
          <button type="submit" name="scope" value="conversation" className="rounded-md bg-cta px-4 py-3 text-sm text-cta-foreground">ใช้เฉพาะห้องนี้</button>
          <button type="submit" name="scope" value="profile" disabled={!context.has_profile} className="rounded-md border border-border px-4 py-3 text-sm disabled:opacity-50">บันทึกในโปรไฟล์ด้วย</button>
        </div>
        {!context.has_profile && <p className="text-xs text-muted">กรอกโปรไฟล์ก่อนเพื่อใช้ตัวเลือกบันทึกถาวร</p>}
        {saving && <p role="status" className="text-sm">กำลังบันทึก…</p>}
      </fieldset>
    </form>}
  </dialog>;
}
