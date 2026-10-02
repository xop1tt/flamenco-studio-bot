import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="mt-auto border-t border-black/10 bg-[var(--background)]">
      <div className="mx-auto flex max-w-5xl flex-col gap-2 px-4 py-6 text-sm text-[var(--foreground)]/70 sm:flex-row sm:items-center sm:justify-between">
        <p>&copy; {new Date().getFullYear()} Flamenco Studio</p>
        <Link href="/contact" className="hover:text-[var(--accent)]">
          Связаться со студией
        </Link>
      </div>
    </footer>
  );
}
