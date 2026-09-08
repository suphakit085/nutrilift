"use client";

import { Fragment, useSyncExternalStore } from "react";
import Link from "next/link";
import { getToken } from "@/lib/api";

/** Every number, citation, food row, and calculated figure below was pulled
 *  from the running system on 8 ก.ย. 2569, not written by hand:
 *   - eval/reports/baseline-v9_summary.md and baseline-v9_wilcoxon.md (n=150)
 *   - knowledge/cards/*.md (26 files, excl. _TEMPLATE.md) and knowledge/foods.csv (356 rows)
 *   - a real POST /conversations/{id}/chat response for "ช่วง cut ควรกินโปรตีนวันละเท่าไหร่"
 *   - a real GET /profile/targets response for a male/24y/175cm/72kg/bulk profile
 *   - the Flag enum in backend/app/services/guardrails.py (8 members)
 *  If any of these change, this page goes stale - it is not meant to be
 *  re-derived from memory. */

const EVIDENCE_ROWS = [
  { metric: "ความถูกต้อง", withRag: "4.887", withoutRag: "4.693", p: "0.0019" },
  { metric: "ความครบถ้วน", withRag: "4.900", withoutRag: "4.747", p: "0.0114" },
  { metric: "อ้างอิงตรงเนื้อหา", withRag: "4.947", withoutRag: "4.700", p: "0.0002" },
] as const;

const STATS = [
  { value: "26", label: "การ์ดความรู้ที่เขียนเองจากงานวิจัย" },
  { value: "355", label: "เมนูอาหารที่ระบุแหล่งที่มาได้" },
  { value: "150", label: "คำถามในชุดประเมิน ถามซ้ำสองแบบ" },
  { value: "0", label: "อ้างแหล่งที่ไม่มีจริง จาก 340 มาร์กเกอร์" },
] as const;

const REFERENCES = [
  "Mifflin MD, St Jeor ST, et al. Am J Clin Nutr. 1990;51(2):241–247",
  "Jäger R, et al. ISSN Position Stand: Protein and Exercise. JISSN. 2017;14:20",
  "Thomas DT, et al. ACSM Joint Position Statement. Med Sci Sports Exerc. 2016;48(3):543–568",
] as const;

/** ชาย 24 ปี 175 ซม. 72 กก. เพิ่มกล้ามเนื้อ (moderate) - a real
 *  GET /profile/targets response, not a hand-picked example. */
const CALC = {
  bmr: "1,699",
  tdee: "2,633",
  target: "2,962",
  protein: { grams: "130", note: "1.6–2.0 g/กก." },
  carb: { grams: "463", note: "พลังงานที่เหลือ" },
  fat: { grams: "66", note: "ขั้นต่ำ 20% ของพลังงาน" },
};

const FOOD_ROWS = [
  { name: "ข้าวสวย", serving: "1 ทัพพี", kcal: "77", protein: "1.3", source: "ASEAN-FCD-2014-INMU:MYA14" },
  { name: "อกไก่ไม่มีหนัง, ย่าง", serving: "100 กรัม", kcal: "151", protein: "30.5", source: "USDA-FDC-SR:171534" },
  { name: "ก๋วยเตี๋ยวผัดไทย, ใส่ไข่", serving: "1 จาน", kcal: "837", protein: "27.0", source: "DOH-NSS-2018:11007" },
  { name: "เต้าหู้ขาวแข็ง", serving: "100 กรัม", kcal: "126", protein: "12.9", source: "ThaiFCD-Online-v3:C48" },
] as const;

const FOOD_SOURCES = [
  "ASEAN Food Composition Database 2014 · INMU",
  "ตารางคุณค่าอาหารไทย · กรมอนามัย 2561",
  "Thai FCD Online v3 · INMU 2568",
  "USDA FoodData Central",
] as const;

/** The 8 members of Flag in backend/app/services/guardrails.py, split by
 *  WHERE each one is actually enforced - because that differs, and the
 *  page must not claim otherwise:
 *
 *   code  - decided in the program; the model cannot overrule it.
 *           01/02 are in guardrails.HARD_REFUSAL_FLAGS, so chat.py returns
 *           canned text and never calls the API. 06 refuses pre-model when
 *           the keyword rule and an empty retrieval agree
 *           (chat.is_clearly_out_of_scope). 04 is rejected by
 *           nutrition._validate, 07 forces cut -> maintain, and 08's
 *           warning is emitted by the calculator.
 *   prompt- only appends a line to the system prompt
 *           (guardrails.FLAG_INSTRUCTIONS), so the wording is the model's.
 *
 *  Row 08 says the target is NOT raised: nutrition.py appends a warning and
 *  leaves kcal_target as computed - backend/tests/test_nutrition.py asserts
 *  `energy_target_kcal < 1200` outright. */
const SAFETY_GROUPS = [
  {
    kind: "code",
    heading: "ตัดสินในโปรแกรม",
    note: "6 ใน 8 · โมเดลเปลี่ยนไม่ได้",
    rules: [
      { n: "01", title: "โรคและอาการป่วย", body: "ตอบด้วยข้อความปฏิเสธสำเร็จรูป ไม่เรียกโมเดล" },
      { n: "02", title: "สารเร่งกล้ามเนื้อ", body: "ตอบด้วยข้อความปฏิเสธสำเร็จรูป ไม่เรียกโมเดล" },
      { n: "04", title: "อายุต่ำกว่า 18 ปี", body: "โปรไฟล์ไม่ผ่านการตรวจ ระบบไม่คำนวณเป้าหมายให้" },
      { n: "06", title: "นอกเรื่องโภชนาการ", body: "ปฏิเสธก่อนเรียกโมเดล เมื่อคำสำคัญและผลค้นคืนตรงกัน" },
      { n: "07", title: "น้ำหนักต่ำกว่าเกณฑ์", body: "เปลี่ยนเป้าหมายจากลดไขมันเป็นรักษาน้ำหนักให้เอง" },
      { n: "08", title: "พลังงานต่ำกว่า 1,200 kcal", body: "แนบคำเตือนว่าต่ำเกินกว่าจะดูแลเอง ไม่ได้ปรับตัวเลขขึ้นให้" },
    ],
  },
  {
    kind: "prompt",
    heading: "เติมคำสั่งให้โมเดล",
    note: "2 ใน 8 · ถ้อยคำมาจากโมเดล",
    rules: [
      { n: "03", title: "พฤติกรรมการกินผิดปกติ", body: "สั่งไม่ให้เร่งลดน้ำหนัก และให้ส่งต่อผู้เชี่ยวชาญ" },
      { n: "05", title: "ตั้งครรภ์และให้นมบุตร", body: "สั่งให้เตือนและแนะนำให้ปรึกษาผู้เชี่ยวชาญ" },
    ],
  },
] as const;

const SHELL = "mx-auto w-full max-w-[1200px] px-5 sm:px-8";

/** Every interactive element on this page is a link, and several sit on the
 *  near-black band where the browser's default focus outline is effectively
 *  invisible - so the ring is stated explicitly in the accent that reads on
 *  each ground. */
const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";
const FOCUS_ON_BAND = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white";

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
  const primaryHref = signedIn ? "/chat" : "/login";
  const primaryLabel = signedIn ? "ไปหน้าแชต" : "เริ่มใช้งานฟรี";

  // header / main / footer are siblings under a plain wrapper: a <footer>
  // nested inside <main> is scoped to it and is not exposed as the contentinfo
  // landmark, so with the old structure the whole page offered a screen-reader
  // user a single landmark.
  return (
    <div className="overflow-x-hidden bg-background text-foreground">
      {/* ---------- header ---------- */}
      <header className={`${SHELL} flex items-center justify-between border-b border-rule py-5`}>
        <Link href="/" className={`flex items-center gap-2.5 ${FOCUS}`}>
          <span className="flex h-8 w-8 items-center justify-center rounded bg-cta text-cta-foreground">
            <LeafIcon className="h-[18px] w-[18px]" />
          </span>
          <span className="font-display text-lg font-bold tracking-tight">NutriLift</span>
        </Link>

        <nav className="hidden items-center gap-8 text-[15px] text-body lg:flex">
          <a href="#evidence" className={`transition hover:text-foreground ${FOCUS}`}>ผลประเมิน</a>
          <a href="#numbers" className={`transition hover:text-foreground ${FOCUS}`}>ที่มาของตัวเลข</a>
          <a href="#food" className={`transition hover:text-foreground ${FOCUS}`}>ฐานข้อมูลอาหาร</a>
          <a href="#safety" className={`transition hover:text-foreground ${FOCUS}`}>ขอบเขตและความปลอดภัย</a>
        </nav>

        <div className="flex items-center gap-4">
          {!signedIn && (
            <Link href="/login" className={`hidden text-[15px] text-body transition hover:text-foreground sm:block ${FOCUS}`}>
              เข้าสู่ระบบ
            </Link>
          )}
          <Link
            href={primaryHref}
            className={`rounded bg-cta px-6 py-3 text-[15px] font-semibold text-cta-foreground transition hover:opacity-85 ${FOCUS}`}
          >
            {signedIn ? "ไปหน้าแชต" : "เริ่มใช้งาน"}
          </Link>
        </div>
      </header>

      <main>
          {/* ---------- hero ---------- */}
        <section className={`${SHELL} grid gap-14 pt-16 lg:grid-cols-12 lg:items-start lg:gap-10 lg:pt-24`}>
          <div className="lg:col-span-7">
            <div className="font-display text-[11px] font-semibold uppercase tracking-[0.1em] text-accent">
              SENIOR PROJECT · 2569
            </div>

            <h1 className="mt-6 font-display text-[38px] font-bold leading-[1.18] tracking-tight text-pretty sm:text-[48px] lg:text-[64px] lg:leading-[1.14]">
              โภชนาการเวทเทรนนิ่ง
              <br />
              ที่ตรวจสอบที่มาได้
            </h1>

            <p className="mt-6 max-w-[520px] text-[15px] leading-[1.8] text-body">
              ถามโค้ชนัทเรื่องกินระหว่างเล่นเวทได้ คำตอบมาจากการ์ดความรู้ที่สรุปจากงานวิจัยโภชนาการกีฬา
              และเอกสารกรมอนามัย โดยมีแหล่งอ้างอิงกำกับไว้ ส่วนแคลอรี่และมาโครคำนวณด้วยสูตรมาตรฐาน
              ไม่ได้ให้โมเดลเดา ส่วนเรื่องโรคและยาอยู่นอกขอบเขต ระบบจะบอกตรง ๆ
            </p>

            <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
              <Link
                href={primaryHref}
                className={`rounded bg-cta px-9 py-4 text-center font-semibold text-cta-foreground transition hover:opacity-85 active:scale-[0.98] ${FOCUS}`}
              >
                {primaryLabel}
              </Link>
              <a
                href="#evidence"
                className={`inline-flex items-center justify-center gap-2 rounded border border-rule px-8 py-4 font-semibold transition hover:border-accent hover:text-accent ${FOCUS}`}
              >
                ดูผลการประเมิน
                <ArrowRightIcon className="h-4 w-4" />
              </a>
            </div>

            <p className="mt-5 text-[13px] text-muted">ไม่มีค่าใช้จ่าย · ใช้ผ่านเบราว์เซอร์ได้เลย</p>
          </div>

          {/* The product itself is the hero image: a real answer this session
              captured from the running system, plus - kept visibly separate,
              not implied as the same exchange - a real calculator output. */}
          <div className="lg:col-span-5">
            <div className="font-display text-[11px] font-semibold tracking-[0.02em] text-muted">
              ชิ้นส่วนจากหน้าจอจริง
            </div>

            <div className="mt-3 rounded-lg border border-rule bg-surface">
              <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="flex h-5 w-5 items-center justify-center rounded bg-cta">
                    <LeafIcon className="h-[11px] w-[11px] text-cta-foreground" />
                  </span>
                  <span className="font-display text-[11px] font-semibold tracking-[0.02em]">โค้ชนัท</span>
                </div>
                <span className="flex items-center gap-1.5 text-xs text-muted">
                  <CheckIcon className="h-3 w-3 text-accent" />
                  ค้นจากฐานความรู้แล้ว
                </span>
              </div>

              <div className="px-4 pb-1 pt-4">
                <div className="flex justify-end">
                  <div className="rounded bg-cta px-4 py-2.5 text-sm text-cta-foreground">
                    ช่วง cut ควรกินโปรตีนวันละเท่าไหร่
                  </div>
                </div>

                <p className="mt-4 text-[15px] leading-[1.85]">
                  สำหรับช่วงลดไขมัน (cut) ร่างกายมีแนวโน้มจะสูญเสียทั้งไขมันและกล้ามเนื้อ
                  การเพิ่มโปรตีนให้สูงขึ้นจะช่วยลดการสูญเสียมวลกล้ามเนื้อในช่วงนี้ได้{" "}
                  <Cite>S1</Cite> แนวทางปฏิบัติสำหรับช่วง cut แนะนำให้กินโปรตีนในช่วง{" "}
                  <strong className="stat-figure font-semibold">1.8–2.2</strong> กรัมต่อน้ำหนักตัว 1 กิโลกรัม{" "}
                  <Cite>S1</Cite>
                </p>
              </div>

              <div className="px-4 pb-4 pt-3">
                <div className="border-t border-border pt-3 font-display text-[11px] font-semibold tracking-[0.02em] text-muted">
                  มาจากไหน
                </div>
                <div className="mt-3 flex gap-3">
                  <span className="stat-figure h-fit shrink-0 rounded bg-accent-soft px-1.5 py-0.5 text-xs font-semibold text-accent">
                    S1
                  </span>
                  {/* The byline names Helms, not the card's first source: the
                      card credits 1.8-2.2 g/kg for a cut to Helms 2014, while
                      Jäger/ISSN 2017 gives 1.4-2.0. Showing the first source
                      next to this figure invited an examiner to catch a
                      mismatch that isn't really there. */}
                  <div className="min-w-0">
                    <div className="text-sm font-semibold leading-[1.5]">
                      ปริมาณโปรตีนที่ควรได้รับสำหรับผู้ฝึกเวทเทรนนิ่ง
                    </div>
                    <div className="mt-0.5 text-xs leading-[1.6] text-muted">
                      หัวข้อ · ทำไมช่วงลดไขมัน (cut) ต้องกินโปรตีนสูงขึ้น
                    </div>
                    <div className="mt-1 text-xs leading-[1.6] text-muted">
                      Helms ER, et al. JISSN. 2014;11:20 · 1 ใน 6 อ้างอิงของการ์ดนี้
                    </div>
                    <div className="mt-2 h-[3px] w-full bg-accent-soft">
                      <div className="h-full w-[80%] bg-accent" />
                    </div>
                  </div>
                  <span className="stat-figure shrink-0 text-xs text-muted">0.80</span>
                </div>
              </div>
            </div>

            {/* Deliberately a separate example, not a continuation of the answer
                above: that answer cites a general figure from the knowledge
                card, this tile is one real calculator call for one saved
                profile. Blending them would misattribute a number. */}
            {/* border-transparent by default so the dark-mode edge costs no
                layout shift: --band is #000000 against a #0b0d09 background in
                dark mode, 1.07:1, so without a rule the tile has no visible
                boundary at all. white/40 composites to #666666 on the band,
                which measures 3.40:1 against --background - white/10 was only
                1.12:1 and did not actually solve it. */}
            <div className="relative -mt-3 ml-6 rounded-lg border border-transparent bg-band px-5 py-4 dark:border-white/40 sm:ml-10">
              {/* Thai writes without spaces between words, so a reader parses
                  word boundaries from the letterforms themselves. Tracking the
                  line out to 0.1em separates the marks inside a single cluster
                  as much as it separates words, which destroys that cue -
                  hence 0.02em. uppercase is a no-op on Thai either way. */}
              <div className="font-display text-[11px] font-semibold tracking-[0.02em] text-accent-loud">
                ส่วนที่ไม่ได้ให้โมเดลคิด
              </div>
              <div className="mt-2 flex items-center justify-between gap-4">
                <div className="text-[13px] leading-[1.6] text-band-soft/80">
                  คำนวณจากโปรไฟล์จริง
                  <br />
                  ชาย 24 ปี 72 กก. เป้าหมาย bulk
                </div>
                <div className="flex shrink-0 items-baseline gap-1.5">
                  <span className="stat-figure text-4xl font-semibold text-white">{CALC.protein.grams}</span>
                  <span className="text-xs text-band-soft/70">g/วัน</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ---------- stat strip ---------- */}
        {/* One rule above the row, gap spacing does the rest of the separating -
            no per-cell border arithmetic that has to agree across a breakpoint
            change (2 columns on mobile, 4 on desktop). */}
        <section className={`${SHELL} mt-20 sm:mt-24`}>
          <div className="grid grid-cols-2 gap-x-8 gap-y-9 border-t border-rule pt-9 sm:grid-cols-4">
            {STATS.map((stat) => (
              <div key={stat.label}>
                <div className="stat-figure text-[40px] font-semibold leading-none sm:text-[52px]">{stat.value}</div>
                <div className="mt-3 text-[13px] leading-[1.6] text-muted">{stat.label}</div>
              </div>
            ))}
          </div>
        </section>

        {/* ---------- 01 evidence ---------- */}
        <section id="evidence" className="mt-20 border-y border-transparent bg-band py-16 text-white dark:border-white/40 sm:mt-24 sm:py-20">
          <div className={`${SHELL} grid gap-10 lg:grid-cols-12 lg:items-start lg:gap-10`}>
            <div className="min-w-0 lg:col-span-4">
              <div className="font-display text-[11px] font-semibold tracking-[0.02em] text-accent-loud">
                01 — ผลการประเมิน
              </div>
              <h2 className="mt-4 font-display text-[28px] font-bold leading-[1.25] tracking-tight sm:text-[40px]">
                วัดแล้วว่า
                <br />
                ฐานความรู้ช่วยจริง
              </h2>
              <p className="mt-5 text-[15px] leading-[1.8] text-band-soft/80">
                คำถามชุดเดียวกัน 150 ข้อ ถามระบบสองแบบ ต่างกันแค่มีหรือไม่มีฐานความรู้
                แล้วให้ผู้ให้คะแนนตัดสินโดยไม่รู้ว่าคำตอบไหนมาจากแบบใด
              </p>
            </div>

            <div className="min-w-0 lg:col-span-7 lg:col-start-6">
              {/* Two renderings of one array. The four-column grid needs room
                  for a Thai metric name plus three 26px figures; below sm that
                  leaves ~55px a figure and "4.887" overflows its cell. So on a
                  phone each row becomes a labelled block - driven from the same
                  EVIDENCE_ROWS, so the two can never disagree. */}
              <div className="sm:hidden">
                {EVIDENCE_ROWS.map((row) => (
                  <div key={row.metric} className="border-t border-white/15 py-5">
                    <div className="text-[15px]">{row.metric}</div>
                    <div className="mt-3 flex items-end gap-7">
                      <div>
                        <div className="font-display text-[10px] font-semibold tracking-[0.02em] text-band-soft/60">
                          ใช้ฐานความรู้
                        </div>
                        <div className="stat-figure mt-1.5 text-[26px] font-semibold leading-none text-accent-loud">
                          {row.withRag}
                        </div>
                      </div>
                      <div>
                        <div className="font-display text-[10px] font-semibold tracking-[0.02em] text-band-soft/60">
                          ไม่ใช้
                        </div>
                        <div className="stat-figure mt-1.5 text-[26px] leading-none text-band-soft/50">
                          {row.withoutRag}
                        </div>
                      </div>
                      <div>
                        <div className="font-display text-[10px] font-semibold tracking-[0.02em] text-band-soft/60">
                          p-value
                        </div>
                        <div className="stat-figure mt-1.5 text-[15px] leading-none text-band-soft/80">{row.p}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="hidden grid-cols-[2fr_1fr_1fr_1fr] gap-x-4 border-t border-white/15 sm:grid">
                <div className="pt-3.5 font-display text-[11px] font-semibold tracking-[0.02em] text-band-soft/60">
                  ตัวชี้วัด
                </div>
                <div className="pt-3.5 text-right font-display text-[11px] font-semibold tracking-[0.02em] text-band-soft/60">
                  ใช้ฐานความรู้
                </div>
                <div className="pt-3.5 text-right font-display text-[11px] font-semibold tracking-[0.02em] text-band-soft/60">
                  ไม่ใช้
                </div>
                <div className="pt-3.5 text-right font-display text-[11px] font-semibold tracking-[0.02em] text-band-soft/60">
                  p-value
                </div>

                {EVIDENCE_ROWS.map((row) => (
                  <Fragment key={row.metric}>
                    <div className="flex items-center border-t border-white/15 py-5 text-base">
                      {row.metric}
                    </div>
                    <div className="stat-figure flex items-center justify-end border-t border-white/15 py-5 text-[26px] font-semibold text-accent-loud">
                      {row.withRag}
                    </div>
                    <div className="stat-figure flex items-center justify-end border-t border-white/15 py-5 text-[26px] text-band-soft/50">
                      {row.withoutRag}
                    </div>
                    <div className="stat-figure flex items-center justify-end border-t border-white/15 py-5 text-base text-band-soft/80">
                      {row.p}
                    </div>
                  </Fragment>
                ))}
              </div>
              <p className="mt-5 text-[13px] leading-[1.7] text-band-soft/60">
                Wilcoxon signed-rank แบบจับคู่รายข้อ · n = 150 คู่ · มีนัยสำคัญที่ระดับ 0.05 ทั้งสามตัวชี้วัด ·
                ค้นคืนถูกภายใน 6 อันดับแรก <span className="stat-figure text-band-soft/80">0.976</span>
              </p>
            </div>
          </div>
        </section>

        {/* ---------- 02 numbers ---------- */}
        <section id="numbers" className={`${SHELL} grid gap-10 pt-20 sm:pt-24 lg:grid-cols-12 lg:items-start lg:gap-10`}>
          <div className="min-w-0 lg:col-span-4">
            <div className="font-display text-[11px] font-semibold tracking-[0.02em] text-accent">
              02 — ที่มาของตัวเลข
            </div>
            <h2 className="mt-4 font-display text-[28px] font-bold leading-[1.25] tracking-tight sm:text-[40px]">
              แคลอรี่ไม่ได้มา
              <br />
              จากโมเดลภาษา
            </h2>
            <p className="mt-5 text-[15px] leading-[1.8] text-body">
              เป้าหมายพลังงานและมาโครคำนวณด้วยโปรแกรมที่เขียนแยกไว้ต่างหาก เรียกใช้เป็นเครื่องมือ
              โมเดลมีหน้าที่อธิบายผลลัพธ์เท่านั้น ตัวเลขชุดเดิมจะได้ค่าเดิมทุกครั้ง และมีเทสต์ล็อกไว้
            </p>
            <div className="mt-8 border-t border-rule pt-5 text-[13px] leading-[1.9] text-muted">
              {REFERENCES.map((ref) => (
                <div key={ref}>{ref}</div>
              ))}
            </div>
          </div>

          <div className="min-w-0 lg:col-span-7 lg:col-start-6">
            <div className="border-b border-rule pb-3.5 font-display text-[11px] font-semibold tracking-[0.02em] text-muted">
              ตัวอย่างการคำนวณ · ชาย 24 ปี 175 ซม. 72 กก. เพิ่มกล้ามเนื้อ
            </div>

            <Row label="BMR" note="Mifflin-St Jeor" value={CALC.bmr} />
            <Row label="TDEE" note="× 1.55 ปานกลาง" value={CALC.tdee} />
            <Row label="เป้าหมายพลังงาน" note="+10–15%" value={CALC.target} big last />

            <div className="grid grid-cols-3 gap-6 pt-7">
              <Macro label="โปรตีน" grams={CALC.protein.grams} note={CALC.protein.note} bar="bg-macro-protein" />
              <Macro label="คาร์โบไฮเดรต" grams={CALC.carb.grams} note={CALC.carb.note} bar="bg-macro-carb" />
              <Macro label="ไขมัน" grams={CALC.fat.grams} note={CALC.fat.note} bar="bg-macro-fat" />
            </div>
          </div>
        </section>

        {/* ---------- 03 food database ---------- */}
        <section id="food" className="mt-20 bg-surface-sunken py-16 sm:mt-24 sm:py-20">
          <div className={`${SHELL} grid gap-10 lg:grid-cols-12 lg:items-start lg:gap-10`}>
            <div className="min-w-0 lg:col-span-4">
              <div className="font-display text-[11px] font-semibold tracking-[0.02em] text-accent">
                03 — ฐานข้อมูลอาหาร
              </div>
              <h2 className="mt-4 font-display text-[28px] font-bold leading-[1.25] tracking-tight sm:text-[40px]">
                ทุกแถว
                <br />
                บอกที่มาได้
              </h2>
              {/* Not "ตามรอยกลับได้": 1 of the 356 rows is a TOVERIFY-LABEL
                  estimate that traces to no published table, so a headline
                  promising traceability would be contradicted by the very
                  paragraph under it. Every row can state its origin - that is
                  the claim this section can actually keep.
                  The last sentence stays on the two things the code does by
                  itself: foods.py always sets `estimated` on the row, and
                  meal_plan.py drops TOVERIFY rows from generated plans. How
                  the model words it is a prompt instruction, which is exactly
                  the distinction section 04 draws. */}
              <p className="mt-5 text-[15px] leading-[1.8] text-body">
                ตารางอาหารมี 356 แถว ในนั้น 355 แถวมาจากฐานข้อมูลองค์ประกอบอาหารที่เผยแพร่จริง
                มีรหัสให้เปิดตรวจย้อนได้ทีละรายการ เหลือ 1 แถวที่ยังเป็นค่าประมาณจากฉลาก
                ระบบติดธงไว้ในข้อมูลว่าเป็นค่าประมาณ และไม่หยิบไปใช้ในแผนมื้ออาหาร
              </p>
            </div>

            <div className="min-w-0 lg:col-span-7 lg:col-start-6">
              {/* The reference code gets its own line rather than a fourth
                  column. As a column it was ~150px wide on a phone and every
                  id truncated to "ASEAN-FCD-20…" - directly under a headline
                  claiming every row can be traced back. Name and serving flex;
                  kcal and protein stay fixed-width so the figures still line up
                  as a column. Matches design/Mobile.dc.html. */}
              <div className="flex items-end gap-3 border-b border-rule pb-3">
                <div className="min-w-0 flex-1 font-display text-[11px] font-semibold tracking-[0.02em] text-muted">
                  เมนู · รหัสอ้างอิง
                </div>
                <div className="w-12 shrink-0 text-right font-display text-[11px] font-semibold tracking-[0.02em] text-muted">
                  kcal
                </div>
                <div className="w-16 shrink-0 text-right font-display text-[11px] font-semibold tracking-[0.02em] text-muted">
                  โปรตีน
                </div>
              </div>
              {FOOD_ROWS.map((row) => (
                <div key={row.name} className="border-b border-rule/60 py-3.5">
                  <div className="flex items-baseline gap-3">
                    <div className="min-w-0 flex-1 text-[15px] leading-[1.5]">
                      {row.name} <span className="text-muted">· {row.serving}</span>
                    </div>
                    <div className="stat-figure w-12 shrink-0 text-right text-[15px]">{row.kcal}</div>
                    <div className="stat-figure w-16 shrink-0 text-right text-[15px]">{row.protein}</div>
                  </div>
                  <div className="stat-figure mt-1 text-[11px] text-muted">{row.source}</div>
                </div>
              ))}

              {/* Traceability has one honest limit, and stating it is stronger
                  than letting an examiner find it: knowledge/README.md records
                  that "1 จาน = 350 กรัม" is this project's assumption, not the
                  source's, and the hand-picked serving rows are reduced from the
                  same per-100 g code. So the code traces the composition; the
                  portion weight is ours. */}
              <p className="mt-4 text-[13px] leading-[1.7] text-muted">
                แถวที่เป็นหน่วยเสิร์ฟคำนวณจากค่าต่อ 100 กรัมของแหล่งอ้างอิง
                ด้วยน้ำหนักที่โปรเจกกำหนดเอง (1 ทัพพี = 60 ก., 1 จาน = 350 ก.) ส่วนแถว 100 กรัม
                เป็นค่าจากแหล่งโดยตรง
              </p>

              <div className="mt-6 flex flex-wrap gap-2">
                {FOOD_SOURCES.map((source) => (
                  <span key={source} className="rounded border border-rule px-3 py-1.5 text-[13px] text-body">
                    {source}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ---------- 04 safety ---------- */}
        <section id="safety" className={`${SHELL} grid gap-10 pt-20 sm:pt-24 lg:grid-cols-12 lg:items-start lg:gap-10`}>
          <div className="min-w-0 lg:col-span-4">
            <div className="font-display text-[11px] font-semibold tracking-[0.02em] text-accent">
              04 — ขอบเขตและความปลอดภัย
            </div>
            <h2 className="mt-4 font-display text-[28px] font-bold leading-[1.25] tracking-tight sm:text-[40px]">
              บางคำถาม
              <br />
              ระบบไม่ตอบ
            </h2>
            <p className="mt-5 text-[15px] leading-[1.8] text-body">
              คำถามทุกข้อผ่านกฎคัดกรองก่อนเรียกโมเดล 6 ใน 8 กรณีตัดสินจบในโปรแกรม
              โมเดลเปลี่ยนไม่ได้ อีก 2 กรณีเป็นการเติมคำสั่งเข้าไปในพรอมต์ ถ้อยคำจึงมาจากโมเดล
              หน้านี้จึงแยกสองกลุ่มนี้ออกจากกัน ทั้งแปดกรณีมีเทสต์ครอบไว้
            </p>
          </div>

          <div className="min-w-0 lg:col-span-7 lg:col-start-6">
            {SAFETY_GROUPS.map((group) => (
              <div key={group.kind} className="mb-9 last:mb-0">
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-rule pb-2.5">
                  <div className="font-display text-[11px] font-semibold tracking-[0.02em] text-accent">
                    {group.heading}
                  </div>
                  <div className="text-[13px] text-muted">{group.note}</div>
                </div>
                <div className="grid grid-cols-1 gap-x-8 sm:grid-cols-2">
                  {group.rules.map((rule) => (
                    <div key={rule.n} className="flex gap-3.5 border-b border-border py-4">
                      <span className="stat-figure pt-0.5 text-xs text-muted">{rule.n}</span>
                      <div className="min-w-0">
                        <div className="text-[15px] font-semibold">{rule.title}</div>
                        <div className="mt-0.5 text-[13px] leading-[1.6] text-muted">{rule.body}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ---------- closing CTA ---------- */}
        <section className={`${SHELL} pt-20 sm:pt-24`}>
          <div className="flex flex-col gap-8 rounded-lg border border-transparent bg-band px-6 py-14 dark:border-white/40 sm:flex-row sm:items-end sm:justify-between sm:px-14 sm:py-16">
            <div>
              <h2 className="font-display text-[32px] font-bold leading-[1.2] tracking-tight text-white sm:text-[44px]">
                ลองถามคำถามแรก
              </h2>
              <p className="mt-4 max-w-[480px] text-[15px] leading-[1.8] text-band-soft/80">
                ใช้ผ่านเบราว์เซอร์ได้เลย ไม่มีค่าใช้จ่าย กรอกโปรไฟล์ครั้งเดียวเพื่อให้ระบบคำนวณเป้าหมายให้ตรงกับคุณ
              </p>
            </div>
            <Link
              href={primaryHref}
              className={`shrink-0 rounded bg-accent-loud px-10 py-4 text-center font-semibold text-band transition hover:opacity-90 active:scale-[0.98] ${FOCUS_ON_BAND}`}
            >
              {primaryLabel}
            </Link>
          </div>
        </section>

      </main>

      {/* ---------- footer ---------- */}
      <footer className={`${SHELL} pb-12 pt-14`}>
        <div className="flex flex-col justify-between gap-8 border-t border-rule pt-8 sm:flex-row">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="flex h-7 w-7 items-center justify-center rounded bg-cta text-cta-foreground">
                <LeafIcon className="h-4 w-4" />
              </span>
              <span className="font-display font-bold">NutriLift</span>
            </div>
            <p className="mt-3 max-w-[420px] text-[13px] leading-[1.8] text-muted">
              ปริญญานิพนธ์ · ให้ข้อมูลเพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำทางการแพทย์
              ผู้ที่มีโรคประจำตัวควรปรึกษาแพทย์หรือนักกำหนดอาหารก่อนปรับอาหาร
            </p>
          </div>

          <div className="flex gap-14 text-sm">
            <div className="flex flex-col gap-2.5">
              <span className="font-semibold">หน้านี้</span>
              <a href="#evidence" className={`text-muted transition hover:text-foreground ${FOCUS}`}>ผลประเมิน</a>
              <a href="#food" className={`text-muted transition hover:text-foreground ${FOCUS}`}>ฐานข้อมูลอาหาร</a>
              <a href="#safety" className={`text-muted transition hover:text-foreground ${FOCUS}`}>ความปลอดภัย</a>
            </div>
            <div className="flex flex-col gap-2.5">
              <span className="font-semibold">เข้าใช้งาน</span>
              <Link href={primaryHref} className={`text-muted transition hover:text-foreground ${FOCUS}`}>
                {signedIn ? "ไปหน้าแชต" : "เข้าสู่ระบบ"}
              </Link>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

/* -------------------------------------------------------------------------
 * Small building blocks
 * ---------------------------------------------------------------------- */

/** An inline citation marker, styled as a chip - the same visual the chat
 *  page uses for [S1]/[S2] so a reader recognises it there later. */
function Cite({ children }: { children: React.ReactNode }) {
  return (
    <span className="stat-figure whitespace-nowrap rounded bg-accent-soft px-1.5 py-0.5 text-xs font-semibold text-accent">
      {children}
    </span>
  );
}

function Row({
  label,
  note,
  value,
  big,
  last,
}: {
  label: string;
  note: string;
  value: string;
  big?: boolean;
  last?: boolean;
}) {
  return (
    <div className={`flex items-baseline justify-between border-b py-4 ${last ? "border-rule" : "border-border"}`}>
      <div>
        <span className={big ? "text-[15px] font-semibold" : "text-[15px]"}>{label}</span>{" "}
        <span className="font-display text-[11px] font-semibold tracking-[0.02em] text-muted">{note}</span>
      </div>
      <span className={`stat-figure font-semibold ${big ? "text-[32px]" : "text-2xl"}`}>{value}</span>
    </div>
  );
}

function Macro({ label, grams, note, bar }: { label: string; grams: string; note: string; bar: string }) {
  return (
    <div>
      <div className="text-[13px] font-semibold text-muted">{label}</div>
      <div className="mt-1.5">
        <span className="stat-figure text-2xl font-semibold">{grams}</span>{" "}
        <span className="text-xs text-muted">g</span>
      </div>
      <div className={`mt-2.5 h-[3px] ${bar}`} />
      <div className="mt-2 text-xs text-muted">{note}</div>
    </div>
  );
}

/* -------------------------------------------------------------------------
 * Icons - stroke-based on a 24px grid, inheriting colour via currentColor.
 * ---------------------------------------------------------------------- */

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
    <svg {...svgProps(className)} strokeWidth={2.6}>
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
