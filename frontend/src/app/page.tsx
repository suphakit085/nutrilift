"use client";

import { useSyncExternalStore } from "react";
import Link from "next/link";
import { getToken } from "@/lib/api";

/** Icon tints reuse the macro palette so the landing page can't drift from the app. */
const TINTS = {
  green: "bg-accent-soft text-accent",
  amber: "bg-macro-carb-soft text-macro-carb",
  blue: "bg-macro-fat-soft text-macro-fat",
} as const;

type Tint = keyof typeof TINTS;

const FEATURES: { icon: Icon; tint: Tint; title: string; body: string }[] = [
  {
    icon: FileTextIcon,
    tint: "green",
    title: "ทุกคำตอบมีแหล่งอ้างอิง",
    body: "เห็นได้ว่าประโยคไหนมาจากงานวิจัยฉบับไหน ไม่ใช่คำตอบลอย ๆ",
  },
  {
    icon: CalculatorIcon,
    tint: "amber",
    title: "ตัวเลขคำนวณจากสูตร",
    body: "Mifflin-St Jeor และ Katch-McArdle รันในโค้ดจริง ไม่ผ่านการเดาของ AI",
  },
  {
    icon: BowlIcon,
    tint: "blue",
    title: "อาหารไทยค่าจริง",
    body: "จากตารางคุณค่าอาหารไทยของ INMU และกรมอนามัย ไม่ใช่ค่าจากฐานต่างประเทศ",
  },
];

/** Every number here is countable in the repo - none of it is marketing padding. */
const STATS = [
  { value: "25", label: "การ์ดความรู้" },
  { value: "329", label: "เมนูอาหารไทยค่าจริง" },
  { value: "100", label: "คำถามในชุดทดสอบ" },
  { value: "6", label: "หมวดกฎความปลอดภัย" },
];

const TOPICS: { icon: Icon; tint: Tint; title: string; body: string }[] = [
  {
    icon: DumbbellIcon,
    tint: "green",
    title: "โปรตีนและมาโคร",
    body: "ควรกินเท่าไหร่ ต่อมื้อเท่าไหร่ โปรตีนพืชกับสัตว์ต่างกันไหม",
  },
  {
    icon: FlameIcon,
    tint: "amber",
    title: "พลังงาน cut / bulk",
    body: "ขาดดุลเท่าไหร่ถึงพอดี ทำไมน้ำหนักนิ่ง การปรับตัวของระบบเผาผลาญ",
  },
  {
    icon: ClockIcon,
    tint: "blue",
    title: "ช่วงเวลาการกิน",
    body: "ก่อน-หลังฝึกกินอะไร ฝึกตอนท้องว่างเสียกล้ามไหม IF กับการเล่นเวท",
  },
  {
    icon: PillIcon,
    tint: "green",
    title: "อาหารเสริม",
    body: "ครีเอทีน เวย์ คาเฟอีน EAA วิตามินดี — ตัวไหนมีหลักฐาน ตัวไหนไม่คุ้มเงิน",
  },
  {
    icon: BowlIcon,
    tint: "amber",
    title: "อาหารไทย",
    body: "ข้าวกะเพราไก่กี่แคล สั่งอะไรตอน cut น้ำตาลแฝงในชานมไข่มุก",
  },
  {
    icon: HelpCircleIcon,
    tint: "blue",
    title: "ความเชื่อผิด ๆ",
    body: "ลดไขมันเฉพาะจุด คาร์บตอนดึก โปรตีนเกิน 30 กรัมเสียเปล่า",
  },
];

const TRUST_POINTS = [
  "BMR ด้วย Mifflin-St Jeor หรือ Katch-McArdle เมื่อมี %ไขมัน",
  "ค่าอาหารดึงจากฐานข้อมูล ไม่ให้โมเดลเดาแคลอรี่เมนู",
  "ถ้าฐานความรู้ไม่ครอบคลุม จะบอกตรง ๆ ว่าไม่มีข้อมูลพอ",
];

const SOURCES = ["ISSN Position Stands", "ACSM / AND / DC", "กรมอนามัย", "INMU ม.มหิดล"];

const SAFETY = [
  {
    title: "ไม่ให้ขนาดยาหรือสารเร่งกล้าม",
    body: "สเตียรอยด์ ฮอร์โมน SARMs ยาลดน้ำหนัก — อธิบายความเสี่ยงและส่งต่อแพทย์ ไม่ให้วิธีใช้หรือแหล่งซื้อ",
  },
  {
    title: "มีโรคประจำตัว ตั้งครรภ์ หรืออายุต่ำกว่า 18",
    body: "เตือนชัดเจนว่าคำแนะนำทั่วไปอาจไม่เหมาะ และให้ปรึกษาแพทย์หรือนักกำหนดอาหารก่อนปรับอาหาร",
  },
  {
    title: "ไม่แนะนำการอดอาหารรุนแรง",
    body: "ไม่แนะนำพลังงานต่ำกว่า 1,200 kcal/วัน โดยไม่มีผู้เชี่ยวชาญดูแล และมีสายด่วนสุขภาพจิตเมื่อพบสัญญาณเสี่ยง",
  },
];

/** Sample targets shown in the mock cards - the same worked example the
 *  calculator unit tests use (male 25, 175cm, 70kg, moderate, cut). */
const SAMPLE = {
  bmr: "1,674",
  tdee: "2,594",
  target: "2,180",
  macros: [
    { label: "โปรตีน", grams: "140 g", share: 26, bar: "bg-macro-protein", track: "bg-macro-protein-soft" },
    { label: "คาร์โบไฮเดรต", grams: "260 g", share: 48, bar: "bg-macro-carb", track: "bg-macro-carb-soft" },
    { label: "ไขมัน", grams: "63 g", share: 26, bar: "bg-macro-fat", track: "bg-macro-fat-soft" },
  ],
};

const SHELL = "mx-auto w-full max-w-[1200px] px-5 sm:px-8";

/** The token lives in localStorage, which React treats as an external store:
 *  the server snapshot is `false` so the prerendered HTML matches, and the
 *  client swaps after hydration. Reading it in an effect instead would set
 *  state during the first commit and cascade a second render. */
function subscribeToToken(onChange: () => void) {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

export default function LandingPage() {
  const signedIn = useSyncExternalStore(
    subscribeToToken,
    () => Boolean(getToken()),
    () => false,
  );

  return (
    <main className="overflow-x-hidden bg-background text-foreground">
      {/* ---------- nav ---------- */}
      <div className={`${SHELL} flex items-center justify-between py-5`}>
        <Link href="/" className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent-soft text-band">
            <LeafIcon className="h-[18px] w-[18px]" />
          </span>
          <span className="text-lg font-bold tracking-tight">NutriLift</span>
        </Link>

        <nav className="hidden items-center gap-8 text-[15px] text-body lg:flex">
          <a href="#features" className="transition hover:text-foreground">จุดเด่น</a>
          <a href="#topics" className="transition hover:text-foreground">หมวดความรู้</a>
          <a href="#trust" className="transition hover:text-foreground">ความน่าเชื่อถือ</a>
          <a href="#safety" className="transition hover:text-foreground">ความปลอดภัย</a>
        </nav>

        <div className="flex items-center gap-4">
          {signedIn ? (
            <Link
              href="/chat"
              className="rounded-full bg-cta px-6 py-3 text-[15px] font-semibold text-cta-foreground transition hover:opacity-85"
            >
              ไปหน้าแชต
            </Link>
          ) : (
            <>
              <Link href="/login" className="hidden text-[15px] text-body transition hover:text-foreground sm:block">
                เข้าสู่ระบบ
              </Link>
              <Link
                href="/login"
                className="rounded-full bg-cta px-6 py-3 text-[15px] font-semibold text-cta-foreground transition hover:opacity-85"
              >
                เริ่มใช้งาน
              </Link>
            </>
          )}
        </div>
      </div>

      {/* ---------- hero ---------- */}
      <section className={`${SHELL} grid gap-14 pt-10 lg:grid-cols-2 lg:items-center lg:gap-12 lg:pt-14`}>
        <div>
          <span className="inline-flex items-center gap-2 rounded-full bg-accent-soft px-4 py-2 text-sm font-semibold text-band">
            <CheckIcon className="h-[15px] w-[15px]" />
            อ้างอิงงานวิจัยจริง ไม่เดาตัวเลข
          </span>

          {/* "โภชนาการเวทเทรนนิ่ง" is one long unbreakable-looking compound - sized
              so it clears the column at every breakpoint instead of splitting
              mid-word. */}
          <h1 className="mt-5 text-[34px] font-extrabold leading-[1.16] tracking-tight text-pretty sm:text-[42px] lg:text-[44px] xl:text-[50px]">
            โภชนาการเวทเทรนนิ่ง
            <br />
            <span className="text-band">ที่ตรวจสอบที่มาได้</span>
          </h1>

          <p className="mt-5 max-w-[520px] text-[15px] leading-[1.75] text-body sm:text-[17px]">
            ถามโค้ชนัทเรื่องกินได้ทุกอย่าง คำตอบมาจากการ์ดความรู้ที่สรุปจากงานวิจัยโภชนาการกีฬาและเอกสารกรมอนามัย
            พร้อมแสดงแหล่งอ้างอิงทุกครั้ง ส่วนแคลอรี่และมาโครคำนวณจากโปรไฟล์ของคุณด้วยสูตรมาตรฐาน
          </p>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
            <Link
              href="/login"
              className="rounded-full bg-cta px-9 py-4 text-center font-semibold text-cta-foreground transition hover:opacity-85 active:scale-[0.99]"
            >
              เริ่มใช้งานฟรี
            </Link>
            <a
              href="#trust"
              className="inline-flex items-center justify-center gap-2 rounded-full border-[1.5px] border-border px-8 py-4 font-semibold transition hover:border-accent hover:text-accent"
            >
              ดูตัวอย่างคำตอบ
              <ArrowRightIcon className="h-4 w-4" />
            </a>
          </div>

          <p className="mt-5 text-sm text-muted">ไม่มีค่าใช้จ่าย · ใช้ผ่านเบราว์เซอร์ได้เลย</p>
        </div>

        {/* The product itself is the hero image - a real answer with its sources. */}
        <div className="relative">
          {/* Sibling order does the layering: no z-index, so the cards below
              paint over this without it dropping behind the page background. */}
          <div className="absolute left-1/2 top-6 h-[280px] w-[280px] -translate-x-1/2 rounded-full bg-accent-soft sm:h-[380px] sm:w-[380px] lg:left-16 lg:translate-x-0" />

          <div className="relative rounded-3xl border border-border bg-surface p-5 shadow-[0_18px_44px_rgba(31,29,25,0.09)] sm:p-6">
            <div className="flex justify-end">
              <div className="rounded-3xl rounded-br-lg bg-cta px-4 py-3 text-[15px] text-cta-foreground">
                ช่วง cut ควรกินโปรตีนวันละเท่าไหร่
              </div>
            </div>

            <div className="mt-3.5 rounded-3xl rounded-bl-lg border border-border bg-surface-sunken p-4">
              <p className="text-[15px] leading-[1.8]">
                ช่วงลดไขมันแนะนำโปรตีน <strong className="font-bold">1.8–2.2 กรัม</strong> ต่อน้ำหนักตัว 1 กิโลกรัมต่อวัน{" "}
                <span className="font-semibold text-band">[S1]</span> เพื่อรักษามวลกล้ามเนื้อระหว่างขาดดุลพลังงาน{" "}
                <span className="font-semibold text-band">[S2]</span>
              </p>
              <div className="mt-3.5 flex flex-wrap gap-1.5 border-t border-border pt-3">
                <span className="rounded-lg bg-accent-soft px-2.5 py-1 text-xs text-accent">
                  [S1] ปริมาณโปรตีนสำหรับผู้ฝึกเวท
                </span>
                <span className="rounded-lg bg-accent-soft px-2.5 py-1 text-xs text-accent">
                  [S2] สมดุลพลังงาน cut/bulk
                </span>
              </div>
            </div>
          </div>

          {/* Tucked under the answer card in normal flow rather than absolutely
              placed: the answer's height changes with the viewport, and an
              absolute card was covering its citation chips at some widths. */}
          <div className="relative -mt-8 ml-auto w-[240px] rounded-3xl border border-border bg-surface p-5 shadow-[0_18px_44px_rgba(31,29,25,0.11)] sm:w-[280px]">
            <div className="text-[13px] text-muted">เป้าหมายวันนี้</div>
            <div className="mt-2 flex items-baseline gap-1.5">
              <span className="text-3xl font-bold tracking-tight tabular-nums">{SAMPLE.target}</span>
              <span className="text-sm text-muted">kcal</span>
            </div>
            <div className="mt-4 flex flex-col gap-3">
              {SAMPLE.macros.map((macro) => (
                <div key={macro.label}>
                  <div className="flex justify-between text-xs text-body">
                    <span>{macro.label}</span>
                    <span className="font-semibold">{macro.grams}</span>
                  </div>
                  <div className={`mt-1.5 h-1.5 overflow-hidden rounded-full ${macro.track}`}>
                    <div className={`h-full rounded-full ${macro.bar}`} style={{ width: `${macro.share}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ---------- curve into the band ---------- */}
      <svg
        viewBox="0 0 1440 110"
        preserveAspectRatio="none"
        aria-hidden="true"
        className="mt-10 block h-[64px] w-full text-band sm:h-[110px]"
      >
        <path d="M0,110 L0,44 C300,-6 860,74 1440,16 L1440,110 Z" fill="currentColor" />
      </svg>

      {/* ---------- features + stats ---------- */}
      <section id="features" className="bg-band pb-16 sm:pb-20">
        <div className={SHELL}>
          <div className="-mt-14 grid gap-5 sm:-mt-16 md:grid-cols-3">
            {FEATURES.map(({ icon: Icon, tint, title, body }) => (
              <div
                key={title}
                className="rounded-3xl bg-surface p-7 shadow-[0_14px_36px_rgba(31,29,25,0.1)]"
              >
                <span className={`flex h-12 w-12 items-center justify-center rounded-2xl ${TINTS[tint]}`}>
                  <Icon className="h-[22px] w-[22px]" />
                </span>
                <h3 className="mt-4 text-lg font-bold">{title}</h3>
                <p className="mt-2 text-[15px] leading-[1.7] text-body">{body}</p>
              </div>
            ))}
          </div>

          <div className="mt-14 grid grid-cols-2 gap-8 md:grid-cols-4">
            {STATS.map((stat) => (
              <div key={stat.label} className="text-center">
                <div className="text-4xl font-extrabold tracking-tight text-white tabular-nums sm:text-[46px]">
                  {stat.value}
                </div>
                <div className="mt-1 text-sm text-band-soft">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- topics ---------- */}
      <section id="topics" className={`${SHELL} pt-20 sm:pt-24`}>
        <div className="text-center">
          <span className="text-[15px] font-semibold text-band">หมวดความรู้</span>
          <h2 className="mt-2.5 text-3xl font-extrabold tracking-tight sm:text-[40px]">ถามได้ในเรื่องพวกนี้</h2>
          <p className="mx-auto mt-3 max-w-[560px] text-[15px] leading-[1.7] text-body sm:text-base">
            ทุกหมวดเขียนจากงานวิจัยและเอกสารอ้างอิงที่ระบุที่มาได้ ไม่ใช่ความรู้ทั่วไปที่โมเดลจำมา
          </p>
        </div>

        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {TOPICS.map(({ icon: Icon, tint, title, body }) => (
            <div key={title} className="rounded-3xl border border-border bg-surface p-6">
              <span className={`flex h-11 w-11 items-center justify-center rounded-2xl ${TINTS[tint]}`}>
                <Icon className="h-[21px] w-[21px]" />
              </span>
              <h3 className="mt-4 text-[17px] font-bold">{title}</h3>
              <p className="mt-2 text-sm leading-[1.7] text-body">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ---------- why the numbers are trustworthy ---------- */}
      <section id="trust" className={`${SHELL} grid gap-12 pt-20 sm:pt-24 lg:grid-cols-2 lg:items-center lg:gap-16`}>
        <div>
          <span className="text-[15px] font-semibold text-band">ทำไมตัวเลขถึงเชื่อได้</span>
          <h2 className="mt-2.5 text-3xl font-extrabold leading-[1.2] tracking-tight sm:text-[40px]">
            แยกการคำนวณ
            <br />
            ออกจาก AI
          </h2>
          <p className="mt-4 text-[15px] leading-[1.8] text-body sm:text-base">
            แชตบอททั่วไปให้โมเดลคิดเลขเอง ซึ่งผิดได้โดยไม่มีใครรู้ ระบบนี้ให้โมเดลเรียกเครื่องคำนวณที่เขียนเป็นโค้ด
            แล้วรายงานผลตามนั้น ตัวเลขที่คุณเห็นจึงตรวจย้อนได้ทุกตัว พร้อมบอกสูตรและช่วงอ้างอิงที่ใช้
          </p>

          <ul className="mt-7 flex flex-col gap-3.5">
            {TRUST_POINTS.map((point) => (
              <li key={point} className="flex items-start gap-3">
                <CheckIcon className="mt-0.5 h-5 w-5 shrink-0 text-band" />
                <span className="text-[15px] leading-[1.6] sm:text-base">{point}</span>
              </li>
            ))}
          </ul>

          <div className="mt-8 border-t border-border pt-6">
            <div className="text-[13px] font-semibold tracking-wide text-muted">ฐานความรู้สรุปจาก</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {SOURCES.map((source) => (
                <span key={source} className="rounded-full border border-border px-4 py-2 text-[13px] text-body">
                  {source}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="rounded-[28px] border border-border bg-surface p-6 shadow-[0_16px_40px_rgba(31,29,25,0.07)] sm:p-8">
          <div className="flex items-baseline justify-between">
            <span className="text-lg font-bold sm:text-[19px]">เป้าหมายต่อวันของคุณ</span>
            <span className="rounded-full bg-accent-soft px-3.5 py-1.5 text-xs font-semibold text-accent">ลดไขมัน</span>
          </div>

          <div className="mt-5 grid grid-cols-3 gap-3">
            <div className="rounded-2xl border border-border p-4">
              <div className="text-xs text-muted">BMR</div>
              <div className="mt-1.5 text-xl font-bold tracking-tight tabular-nums sm:text-[22px]">{SAMPLE.bmr}</div>
            </div>
            <div className="rounded-2xl border border-border p-4">
              <div className="text-xs text-muted">TDEE</div>
              <div className="mt-1.5 text-xl font-bold tracking-tight tabular-nums sm:text-[22px]">{SAMPLE.tdee}</div>
            </div>
            <div className="rounded-2xl bg-cta p-4">
              <div className="text-xs text-cta-foreground/70">เป้าหมาย</div>
              <div className="mt-1.5 text-xl font-bold tracking-tight text-cta-foreground tabular-nums sm:text-[22px]">
                {SAMPLE.target}
              </div>
            </div>
          </div>

          <div className="mt-5 flex flex-col gap-4">
            {SAMPLE.macros.map((macro) => (
              <div key={macro.label}>
                <div className="flex justify-between text-[13px]">
                  <span className="text-body">{macro.label}</span>
                  <span className="font-semibold tabular-nums">
                    {macro.grams} · {macro.share}%
                  </span>
                </div>
                <div className={`mt-1.5 h-[7px] overflow-hidden rounded-full ${macro.track}`}>
                  <div className={`h-full rounded-full ${macro.bar}`} style={{ width: `${macro.share}%` }} />
                </div>
              </div>
            ))}
          </div>

          <p className="mt-5 border-t border-border pt-4 text-xs leading-[1.7] text-muted">
            ตัวอย่างจากชาย 25 ปี 175 ซม. 70 กก. ออกกำลังกายปานกลาง เป้าหมายลดไขมัน
          </p>
        </div>
      </section>

      {/* ---------- safety ---------- */}
      <section id="safety" className={`${SHELL} pt-20 sm:pt-24`}>
        <div className="rounded-[32px] border border-border bg-surface p-7 sm:p-12">
          <div className="grid gap-10 lg:grid-cols-[420px_1fr] lg:gap-14">
            <div>
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-band">
                <ShieldCheckIcon className="h-6 w-6" />
              </span>
              <h2 className="mt-5 text-[28px] font-extrabold leading-[1.25] tracking-tight sm:text-[34px]">
                รู้ว่าเรื่องไหน
                <br className="hidden sm:block" /> ไม่ควรตอบ
              </h2>
              <p className="mt-4 text-[15px] leading-[1.8] text-body sm:text-base">
                กฎความปลอดภัยเขียนเป็นเงื่อนไขในโค้ด ทำงานก่อนถึงโมเดลเสมอ ผลจึงเหมือนเดิมทุกครั้ง
                ไม่ขึ้นกับว่าโมเดลจะตอบอย่างไรในวันนั้น
              </p>
            </div>

            <div className="flex flex-col gap-3.5">
              {SAFETY.map((item) => (
                <div key={item.title} className="rounded-3xl bg-surface-sunken p-5 sm:px-6">
                  <h3 className="text-base font-bold">{item.title}</h3>
                  <p className="mt-2 text-[15px] leading-[1.7] text-body">{item.body}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ---------- closing CTA ---------- */}
      <section className={`${SHELL} pt-20 sm:pt-24`}>
        <div className="rounded-[36px] bg-band px-6 py-14 text-center sm:px-14 sm:py-16">
          <h2 className="text-[30px] font-extrabold leading-[1.25] tracking-tight text-white sm:text-[42px]">
            กรอกโปรไฟล์ครั้งเดียว
            <br />
            แล้วเริ่มถามได้เลย
          </h2>
          <p className="mx-auto mt-4 max-w-[480px] text-[15px] leading-[1.7] text-band-soft sm:text-[17px]">
            ใช้เวลาไม่ถึงหนึ่งนาที ได้เป้าหมายพลังงานและมาโครของตัวเอง พร้อมถามต่อได้ทันที
          </p>
          <Link
            href="/login"
            className="mt-8 inline-block rounded-full bg-surface px-11 py-4 font-semibold text-foreground transition hover:opacity-90 active:scale-[0.99]"
          >
            เริ่มใช้งานฟรี
          </Link>
        </div>
      </section>

      {/* ---------- footer ---------- */}
      <footer className={`${SHELL} pb-12 pt-14`}>
        <div className="flex flex-col justify-between gap-8 border-t border-border pt-8 sm:flex-row">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="flex h-7 w-7 items-center justify-center rounded-[10px] bg-accent-soft text-band">
                <LeafIcon className="h-4 w-4" />
              </span>
              <span className="font-bold">NutriLift</span>
            </div>
            <p className="mt-3 max-w-[420px] text-[13px] leading-[1.8] text-muted">
              ระบบนี้ให้ข้อมูลเพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำทางการแพทย์
              ผู้ที่มีโรคประจำตัวควรปรึกษาแพทย์หรือนักกำหนดอาหารก่อนปรับอาหาร
            </p>
          </div>

          <div className="flex gap-14 text-sm">
            <div className="flex flex-col gap-2.5">
              <span className="font-semibold">ผลิตภัณฑ์</span>
              <a href="#features" className="text-muted transition hover:text-foreground">จุดเด่น</a>
              <a href="#topics" className="text-muted transition hover:text-foreground">หมวดความรู้</a>
              <a href="#safety" className="text-muted transition hover:text-foreground">ความปลอดภัย</a>
            </div>
            <div className="flex flex-col gap-2.5">
              <span className="font-semibold">เกี่ยวกับ</span>
              <a href="#trust" className="text-muted transition hover:text-foreground">แหล่งอ้างอิง</a>
              <Link href="/login" className="text-muted transition hover:text-foreground">เข้าสู่ระบบ</Link>
            </div>
          </div>
        </div>
      </footer>
    </main>
  );
}

/* -------------------------------------------------------------------------
 * Icons - stroke-based on a 24px grid, inheriting colour via currentColor so
 * the tint classes above control them.
 * ---------------------------------------------------------------------- */

type Icon = ({ className }: { className?: string }) => React.ReactElement;

function svgProps(className?: string) {
  return {
    className,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
}

function LeafIcon({ className }: { className?: string }) {
  return (
    <svg {...svgProps(className)} strokeWidth={1.9}>
      <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z" />
      <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12" />
    </svg>
  );
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg {...svgProps(className)} strokeWidth={2.4}>
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function ArrowRightIcon({ className }: { className?: string }) {
  return (
    <svg {...svgProps(className)} strokeWidth={2}>
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </svg>
  );
}

function FileTextIcon({ className }: { className?: string }) {
  return (
    <svg {...svgProps(className)}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
      <path d="M16 13H8" />
      <path d="M16 17H8" />
    </svg>
  );
}

function CalculatorIcon({ className }: { className?: string }) {
  return (
    <svg {...svgProps(className)}>
      <rect width="16" height="20" x="4" y="2" rx="2" />
      <line x1="8" x2="16" y1="6" y2="6" />
      <line x1="8" x2="8" y1="14" y2="14" />
      <line x1="12" x2="12" y1="14" y2="14" />
      <line x1="16" x2="16" y1="14" y2="14" />
      <line x1="8" x2="8" y1="18" y2="18" />
      <line x1="12" x2="12" y1="18" y2="18" />
      <line x1="16" x2="16" y1="18" y2="18" />
    </svg>
  );
}

function BowlIcon({ className }: { className?: string }) {
  return (
    <svg {...svgProps(className)}>
      <path d="M12 21a9 9 0 0 0 9-9H3a9 9 0 0 0 9 9Z" />
      <path d="M7 21h10" />
      <path d="M11.5 3v4" />
      <path d="M15 4.5v2.5" />
    </svg>
  );
}

function DumbbellIcon({ className }: { className?: string }) {
  return (
    <svg {...svgProps(className)}>
      <path d="m6.5 6.5 11 11" />
      <path d="m21 21-1-1" />
      <path d="m3 3 1 1" />
      <path d="m18 22 4-4" />
      <path d="m2 6 4-4" />
      <path d="m3 10 7-7" />
      <path d="m14 21 7-7" />
    </svg>
  );
}

function FlameIcon({ className }: { className?: string }) {
  return (
    <svg {...svgProps(className)}>
      <path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z" />
    </svg>
  );
}

function ClockIcon({ className }: { className?: string }) {
  return (
    <svg {...svgProps(className)}>
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

function PillIcon({ className }: { className?: string }) {
  return (
    <svg {...svgProps(className)}>
      <path d="m10.5 20.5 10-10a4.95 4.95 0 1 0-7-7l-10 10a4.95 4.95 0 1 0 7 7Z" />
      <path d="m8.5 8.5 7 7" />
    </svg>
  );
}

function HelpCircleIcon({ className }: { className?: string }) {
  return (
    <svg {...svgProps(className)}>
      <circle cx="12" cy="12" r="10" />
      <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
      <line x1="12" x2="12.01" y1="17" y2="17" />
    </svg>
  );
}

function ShieldCheckIcon({ className }: { className?: string }) {
  return (
    <svg {...svgProps(className)}>
      <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}
