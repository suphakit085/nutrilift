"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  api,
  getToken,
  type DailySummary,
  type FoodLogEntry,
  type FoodSearchResult,
  type MealType,
} from "@/lib/api";

const MEAL_LABELS: Record<MealType, string> = {
  breakfast: "มื้อเช้า",
  lunch: "มื้อกลางวัน",
  dinner: "มื้อเย็น",
  snack: "ของว่าง",
};

const MEAL_ORDER: MealType[] = ["breakfast", "lunch", "dinner", "snack"];

/** Local calendar date as YYYY-MM-DD - never `toISOString()`, which is UTC
 * and can be a day off near midnight in Thailand (UTC+7). */
function toDateStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

function todayStr(): string {
  return toDateStr(new Date());
}

function shiftDate(dateStr: string, days: number): string {
  const d = new Date(`${dateStr}T00:00:00`);
  d.setDate(d.getDate() + days);
  return toDateStr(d);
}

export default function LogPage() {
  const router = useRouter();
  const [date, setDate] = useState(todayStr());
  const [entries, setEntries] = useState<FoodLogEntry[]>([]);
  const [summary, setSummary] = useState<DailySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openMeal, setOpenMeal] = useState<MealType | null>(null);

  const refresh = useCallback(async (forDate: string) => {
    try {
      const [entriesRes, summaryRes] = await Promise.all([
        api.listFoodLog(forDate),
        api.getFoodLogSummary(forDate),
      ]);
      setEntries(entriesRes);
      setSummary(summaryRes);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    (async () => {
      await refresh(date);
      setLoading(false);
    })();
  }, [router, date, refresh]);

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-muted">กำลังโหลด…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl p-6 pb-16">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight">บันทึกอาหารประจำวัน</h1>
          <p className="mt-1 text-sm text-muted">
            เทียบยอดสะสมกับเป้าหมายที่คำนวณจากโปรไฟล์ของคุณ
          </p>
        </div>
        <Link
          href="/chat"
          className="rounded-md border border-border px-4 py-2 text-sm transition hover:border-accent hover:text-accent"
        >
          ไปหน้าแชต →
        </Link>
      </header>

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <button
          onClick={() => setDate((d) => shiftDate(d, -1))}
          aria-label="วันก่อนหน้า"
          className="rounded-md border border-border px-3.5 py-2 text-sm transition hover:border-accent hover:text-accent"
        >
          ◀
        </button>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="rounded-sm border border-border bg-surface-sunken px-3.5 py-2 text-sm outline-none focus:border-accent focus:bg-surface"
        />
        <button
          onClick={() => setDate((d) => shiftDate(d, 1))}
          aria-label="วันถัดไป"
          className="rounded-md border border-border px-3.5 py-2 text-sm transition hover:border-accent hover:text-accent"
        >
          ▶
        </button>
        {date !== todayStr() && (
          <button
            onClick={() => setDate(todayStr())}
            className="rounded-md bg-accent-soft px-4 py-2 text-sm font-medium text-accent transition hover:opacity-85"
          >
            วันนี้
          </button>
        )}
      </div>

      {error && (
        <p className="mb-6 rounded-sm border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600">
          {error}
        </p>
      )}

      {summary && <SummaryHero summary={summary} />}

      <div className="mt-6 space-y-4">
        {MEAL_ORDER.map((meal) => (
          <MealSection
            key={meal}
            meal={meal}
            entries={entries.filter((e) => e.meal_type === meal)}
            subtotalKcal={summary?.by_meal[meal].kcal ?? 0}
            isOpen={openMeal === meal}
            onToggleAdd={() => setOpenMeal((m) => (m === meal ? null : meal))}
            date={date}
            onChanged={() => refresh(date)}
          />
        ))}
      </div>
    </main>
  );
}

function SummaryHero({ summary }: { summary: DailySummary }) {
  if (!summary.target) {
    return (
      <div className="rounded-lg border border-border bg-surface p-5">
        <p className="text-sm text-muted">
          ยังไม่ได้ตั้งเป้าหมาย —{" "}
          <Link href="/profile" className="text-accent hover:underline">
            กรอกโปรไฟล์เพื่อคำนวณเป้าหมาย
          </Link>
        </p>
      </div>
    );
  }

  const { target, consumed, remaining } = summary;
  const remainingKcal = remaining!.kcal;

  return (
    <div className="space-y-3">
      <div className="rounded-lg bg-cta p-5 text-cta-foreground">
        <div className="field-label text-[11px] opacity-60">
          {remainingKcal >= 0 ? "พลังงานคงเหลือวันนี้" : "พลังงานเกินเป้าวันนี้"}
        </div>
        <div className="mt-3 flex items-baseline gap-1.5">
          <span className="stat-figure text-3xl font-semibold">
            {Math.abs(Math.round(remainingKcal)).toLocaleString()}
          </span>
          <span className="text-sm opacity-60">kcal</span>
        </div>
        <div className="mt-1 text-xs opacity-60">
          กินไป{" "}
          <span className="stat-figure">{Math.round(consumed.kcal).toLocaleString()}</span> จากเป้า{" "}
          <span className="stat-figure">
            {Math.round(target.kcal).toLocaleString()} kcal
          </span>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <DiaryMacroStat
          label="โปรตีน"
          consumedG={consumed.protein_g}
          targetG={target.protein_g}
          bar="bg-macro-protein"
          track="bg-macro-protein-soft"
        />
        <DiaryMacroStat
          label="คาร์โบไฮเดรต"
          consumedG={consumed.carb_g}
          targetG={target.carb_g}
          bar="bg-macro-carb"
          track="bg-macro-carb-soft"
        />
        <DiaryMacroStat
          label="ไขมัน"
          consumedG={consumed.fat_g}
          targetG={target.fat_g}
          bar="bg-macro-fat"
          track="bg-macro-fat-soft"
        />
      </div>
    </div>
  );
}

function DiaryMacroStat({
  label,
  consumedG,
  targetG,
  bar,
  track,
}: {
  label: string;
  consumedG: number;
  targetG: number;
  bar: string;
  track: string;
}) {
  const percent = targetG > 0 ? Math.round((consumedG / targetG) * 100) : 0;
  const over = consumedG - targetG;

  return (
    <div className="rounded-lg border border-border bg-surface p-5">
      <div className="field-label text-[11px] text-muted">{label}</div>
      <div className="mt-3 flex items-baseline gap-1.5">
        <span className="stat-figure text-3xl font-semibold">
          {Math.round(consumedG)}
        </span>
        <span className="stat-figure text-sm text-muted">/ {Math.round(targetG)}g</span>
      </div>
      <div className={`mt-4 h-1.5 w-full overflow-hidden rounded-sm ${track}`}>
        <div
          className={`h-full ${bar}`}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>
      <div className="mt-2 text-xs text-muted">
        {over > 0 ? (
          <span>
            <span className="stat-figure text-amber-600">+{Math.round(over)}g</span>{" "}
            <span className="text-amber-600">เกินเป้า</span>
          </span>
        ) : (
          <>
            <span className="stat-figure">{percent}%</span> ของเป้าหมาย
          </>
        )}
      </div>
    </div>
  );
}

function MealSection({
  meal,
  entries,
  subtotalKcal,
  isOpen,
  onToggleAdd,
  date,
  onChanged,
}: {
  meal: MealType;
  entries: FoodLogEntry[];
  subtotalKcal: number;
  isOpen: boolean;
  onToggleAdd: () => void;
  date: string;
  onChanged: () => void;
}) {
  return (
    <section className="rounded-lg border border-border bg-surface p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-2">
          <h2 className="font-display font-semibold">{MEAL_LABELS[meal]}</h2>
          <span className="stat-figure text-xs text-muted">
            {Math.round(subtotalKcal).toLocaleString()} kcal
          </span>
        </div>
        <button
          type="button"
          aria-pressed={isOpen}
          onClick={onToggleAdd}
          className={`rounded-sm border px-3.5 py-1.5 text-xs font-medium transition ${
            isOpen
              ? "border-accent bg-accent-soft text-accent"
              : "border-border bg-surface-sunken text-muted hover:border-accent/40 hover:text-foreground"
          }`}
        >
          {isOpen ? "ปิด" : "+ เพิ่มเมนู"}
        </button>
      </div>

      {entries.length > 0 && (
        <ul className="mt-3 space-y-2">
          {entries.map((entry) => (
            <EntryRow key={entry.id} entry={entry} onChanged={onChanged} />
          ))}
        </ul>
      )}

      {isOpen && (
        <AddFoodSearch
          meal={meal}
          date={date}
          onAdded={() => {
            onChanged();
            onToggleAdd();
          }}
        />
      )}
    </section>
  );
}

function EntryRow({
  entry,
  onChanged,
}: {
  entry: FoodLogEntry;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [qty, setQty] = useState(entry.quantity_servings);
  const [busy, setBusy] = useState(false);

  async function saveQty() {
    setBusy(true);
    try {
      await api.updateFoodLogEntry(entry.id, { quantity_servings: qty });
      setEditing(false);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm(`ลบ "${entry.food_name_th}" ออกจากรายการ?`)) return;
    setBusy(true);
    try {
      await api.deleteFoodLogEntry(entry.id);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="flex items-center justify-between gap-3 rounded-md bg-surface-sunken px-3.5 py-2.5 text-sm">
      <div className="min-w-0">
        <div className="truncate">{entry.food_name_th}</div>
        <div className="text-xs text-muted">
          <span className="stat-figure">{entry.quantity_servings}</span> × {entry.serving_desc} ·{" "}
          <span className="stat-figure">{Math.round(entry.total_kcal)} kcal</span>
        </div>
      </div>
      {editing ? (
        <div className="flex shrink-0 items-center gap-1.5">
          <input
            type="number"
            step="0.5"
            min="0.1"
            value={qty}
            onChange={(e) => setQty(Number(e.target.value))}
            className="stat-figure w-16 rounded-sm border border-border bg-surface px-2 py-1 text-xs outline-none focus:border-accent"
          />
          <button
            disabled={busy}
            onClick={saveQty}
            className="rounded-sm bg-cta px-2.5 py-1 text-xs font-medium text-cta-foreground transition hover:opacity-85 disabled:opacity-50"
          >
            บันทึก
          </button>
        </div>
      ) : (
        <div className="flex shrink-0 items-center gap-3 text-xs">
          <button
            onClick={() => setEditing(true)}
            className="text-muted transition hover:text-accent"
          >
            แก้ไข
          </button>
          <button
            disabled={busy}
            onClick={remove}
            className="text-muted transition hover:text-red-600 disabled:opacity-50"
          >
            ลบ
          </button>
        </div>
      )}
    </li>
  );
}

function AddFoodSearch({
  meal,
  date,
  onAdded,
}: {
  meal: MealType;
  date: string;
  onAdded: () => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<FoodSearchResult[]>([]);
  const [selected, setSelected] = useState<FoodSearchResult | null>(null);
  const [qty, setQty] = useState(1);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const q = query.trim();
    const timer = setTimeout(() => {
      if (q.length === 0) {
        setResults([]);
        return;
      }
      api
        .searchFoods(q)
        .then(setResults)
        .catch(() => setResults([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  async function add() {
    if (!selected) return;
    setBusy(true);
    try {
      await api.addFoodLogEntry({
        food_id: selected.id,
        quantity_servings: qty,
        meal_type: meal,
        logged_date: date,
      });
      onAdded();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 rounded-md border border-border bg-surface-sunken p-3.5">
      <input
        autoFocus
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setSelected(null);
        }}
        placeholder="ค้นหาเมนู เช่น ข้าวผัดกุ้ง"
        className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
      />

      {!selected && results.length > 0 && (
        <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto">
          {results.map((food) => (
            <li key={food.id}>
              <button
                type="button"
                onClick={() => setSelected(food)}
                className="flex w-full items-center justify-between rounded-sm px-2.5 py-2 text-left text-sm transition hover:bg-surface"
              >
                <span className="truncate">{food.name_th}</span>
                <span className="shrink-0 text-xs text-muted">
                  {food.serving_desc} · <span className="stat-figure">{Math.round(food.kcal)} kcal</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {selected && (
        <div className="mt-3 flex items-center gap-2 text-sm">
          <span className="min-w-0 flex-1 truncate">{selected.name_th}</span>
          <input
            type="number"
            step="0.5"
            min="0.1"
            value={qty}
            onChange={(e) => setQty(Number(e.target.value))}
            className="stat-figure w-16 rounded-sm border border-border bg-surface px-2 py-1.5 text-xs outline-none focus:border-accent"
          />
          <span className="shrink-0 text-xs text-muted">× {selected.serving_desc}</span>
          <button
            disabled={busy}
            onClick={add}
            className="shrink-0 rounded-sm bg-cta px-4 py-1.5 text-xs font-medium text-cta-foreground transition hover:opacity-85 disabled:opacity-50"
          >
            เพิ่ม
          </button>
        </div>
      )}
    </div>
  );
}
