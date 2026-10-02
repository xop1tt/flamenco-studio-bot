import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="mt-auto border-t border-[var(--border)] bg-[var(--surface)]">
      <div className="mx-auto flex max-w-5xl flex-col gap-2 px-4 py-6 text-sm text-[var(--text-secondary)] sm:flex-row sm:items-center sm:justify-between">
        <p>&copy; {new Date().getFullYear()} Flamenco Studio</p>
        <Link href="/contact" className="hover:text-[var(--primary)]">
          Связаться со студией
        </Link>
      </div>
    </footer>
  );
}
