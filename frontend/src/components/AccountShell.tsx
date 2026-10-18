import Link from "next/link";

export const accountInputClass = "mt-1.5 w-full rounded-sm border border-border bg-surface-sunken px-3.5 py-2.5 outline-none focus:border-accent focus:bg-surface";
export const accountButtonClass = "rounded-md bg-cta px-5 py-2.5 text-sm font-medium text-cta-foreground transition hover:opacity-85 disabled:opacity-40";

export default function AccountShell({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return <main className="mx-auto min-h-screen max-w-lg px-6 py-12 sm:py-20">
    <Link href="/" className="font-display text-sm font-bold">NutriLift</Link>
    <h1 className="mt-7 font-display text-2xl font-bold">{title}</h1>
    {description && <p className="mt-3 text-sm leading-relaxed text-muted">{description}</p>}
    <div className="mt-6 rounded-lg border border-border bg-surface p-6">{children}</div>
    <Link href="/login" className="mt-6 inline-block text-sm text-muted underline underline-offset-4">กลับไปเข้าสู่ระบบ</Link>
  </main>;
}
