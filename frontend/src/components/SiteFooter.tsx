import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="footer-surface relative z-[2] mt-auto">
      <div className="mx-auto flex max-w-5xl flex-col items-center gap-2 px-4 py-10 text-center text-base text-[var(--text-secondary)]">
        <p>&copy; {new Date().getFullYear()} Mirada Studio</p>
        <Link href="/credits" className="text-sm underline-offset-4 hover:text-[var(--primary)] hover:underline">
          Авторы изображений
        </Link>
      </div>
    </footer>
  );
}
