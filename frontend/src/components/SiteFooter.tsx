import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="mt-auto bg-[var(--surface-secondary)]">
      <div className="mx-auto flex max-w-5xl flex-col gap-2 px-4 py-8 text-base text-[var(--text-secondary)] sm:flex-row sm:items-center sm:justify-between">
        <p>&copy; {new Date().getFullYear()} Flamenco Studio</p>
        <Link
          href="/contact"
          className="font-medium text-[var(--accent-dark)] hover:underline"
        >
          Связаться со студией
        </Link>
      </div>
    </footer>
  );
}
