import Link from "next/link";
import type { LessonPackage } from "@/lib/api";
import { startCheckoutAction } from "@/lib/actions";

type Props = {
  packages: LessonPackage[];
  // Кнопка «Купить» показывается только когда передан этот проп (страница
  // /packages). На главной PackagesGrid используется как читательский
  // тизер без него — см. src/app/page.tsx.
  isAuthenticated?: boolean;
};

export function PackagesGrid({ packages, isAuthenticated }: Props) {
  if (packages.length === 0) {
    return (
      <p className="text-[var(--text-secondary)]">
        Каталог абонементов сейчас недоступен. Попробуйте обновить страницу
        позже.
      </p>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {packages.map((lessonPackage) => (
        <div
          key={lessonPackage.key}
          className="flex flex-col gap-3 rounded-2xl border border-[var(--border-strong)] bg-[var(--surface)] p-6 shadow-[var(--shadow-card)] transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-card-hover)]"
        >
          <div className="text-lg font-semibold">{lessonPackage.title}</div>
          <div className="text-base text-[var(--text-secondary)]">
            {lessonPackage.lessons} {lessonsWord(lessonPackage.lessons)}
          </div>
          <div className="text-3xl font-bold text-[var(--primary)]">
            {lessonPackage.price_rub} ₽
          </div>
          {isAuthenticated !== undefined && (
            <div className="mt-auto pt-2">
              {isAuthenticated ? (
                <form action={startCheckoutAction}>
                  <input type="hidden" name="package_key" value={lessonPackage.key} />
                  <button
                    type="submit"
                    className="w-full rounded-full bg-[var(--primary)] px-4 py-2.5 text-sm font-medium text-[var(--surface)] shadow-[var(--shadow-card)] transition hover:bg-[var(--primary-hover)] hover:shadow-[var(--shadow-card-hover)]"
                  >
                    Купить
                  </button>
                </form>
              ) : (
                <Link
                  href="/login"
                  className="block w-full rounded-full bg-[var(--primary)] px-4 py-2.5 text-center text-sm font-medium text-[var(--surface)] shadow-[var(--shadow-card)] transition hover:bg-[var(--primary-hover)] hover:shadow-[var(--shadow-card-hover)]"
                >
                  Войти и купить
                </Link>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function lessonsWord(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return "занятие";
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) {
    return "занятия";
  }
  return "занятий";
}
