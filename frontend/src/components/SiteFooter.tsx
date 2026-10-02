export function SiteFooter() {
  return (
    <footer className="glass-bar mt-auto">
      <div className="mx-auto max-w-5xl px-4 py-8 text-center text-base text-[var(--text-secondary)]">
        <p>&copy; {new Date().getFullYear()} Mirada Studio</p>
      </div>
    </footer>
  );
}
