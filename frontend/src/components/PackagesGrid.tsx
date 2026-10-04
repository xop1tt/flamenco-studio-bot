import Link from "next/link";
import { GLASS_BUTTON_CLASS } from "@/lib/glass";
import type { LessonPackage } from "@/lib/api";
import { startCheckoutAction } from "@/lib/actions";
import { formatPrice } from "@/lib/format";

type Props = {
  packages: LessonPackage[];
  // Если проп не передан (тизер на главной — см. src/app/page.tsx),
  // карточка ведёт на /packages вместо покупки. Покупка доступна только на
  // самой странице /packages, где isAuthenticated передаётся явно.
  isAuthenticated?: boolean;
};

export function PackagesGrid({ packages, isAuthenticated }: Props) {
  if (packages.length === 0) {
    return (
      <div className="glass-medium flex flex-col items-start gap-3 rounded-[24px] p-6">
        <p className="text-[var(--text-secondary)]">
          Каталог абонементов сейчас недоступен. Попробуйте обновить страницу
          позже.
        </p>
        <Link
          href="/contact"
          className="btn-primary rounded-full px-5 py-2 text-sm font-medium"
        >
          Написать, чтобы уточнить цены
        </Link>
      </div>
    );
  }

  // Цена одного занятия в абонементе дешевле всего и даёт экономию относительно
  // разовых занятий — это видно из уже имеющихся цен, без новых бизнес-правил.
  const baseline = packages.find((item) => item.lessons === 1);
  const bestValueKey =
    packages.length > 1
      ? packages.reduce((best, item) =>
          item.price_rub / item.lessons < best.price_rub / best.lessons ? item : best,
        ).key
      : undefined;

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {packages.map((lessonPackage) => {
        const pricePerLesson = Math.round(lessonPackage.price_rub / lessonPackage.lessons);
        const savings =
          baseline && lessonPackage.lessons > 1
            ? baseline.price_rub * lessonPackage.lessons - lessonPackage.price_rub
            : 0;
        const isBestValue = lessonPackage.key === bestValueKey && lessonPackage.lessons > 1;

        return (
        <div
          key={lessonPackage.key}
          className={`relative flex flex-col gap-3 rounded-[28px] glass-medium glass-specular p-7 ${
            isBestValue ? "outline-2 outline-[var(--primary)]" : ""
          }`}
        >
          {isBestValue ? (
            <span className="absolute -top-3 left-6 rounded-full bg-[var(--primary)] px-3 py-1 text-xs font-semibold text-[var(--on-primary)] shadow-[var(--shadow-card)]">
              Выгодно
            </span>
          ) : (
            savings > 0 && (
              <span className="absolute -top-3 left-6 rounded-full bg-[var(--primary-light)] px-3 py-1 text-xs font-semibold text-[var(--accent-dark)] shadow-[var(--shadow-card)]">
                Экономия {formatPrice(savings)}
              </span>
            )
          )}
          {/* Название уже содержит количество занятий ("Абонемент на 4
              занятия") — отдельная строка с тем же числом дублировала его. */}
          <div className="font-heading text-lg font-bold tracking-tight">{lessonPackage.title}</div>
          <div>
            <div className="font-heading text-4xl font-bold tracking-tight text-[var(--primary)]">
              {formatPrice(lessonPackage.price_rub)}
            </div>
            {lessonPackage.lessons > 1 && (
              <div className="text-sm text-[var(--text-secondary)]">
                {formatPrice(pricePerLesson)} за занятие
              </div>
            )}
          </div>
          <div className="mt-auto pt-2">
            {isAuthenticated === undefined ? (
              <Link
                href="/packages"
                className={`${GLASS_BUTTON_CLASS} block w-full px-4 py-2.5 text-center text-sm`}
              >
                Подробнее →
              </Link>
            ) : isAuthenticated ? (
              <form action={startCheckoutAction}>
                <input type="hidden" name="package_key" value={lessonPackage.key} />
                <button
                  type="submit"
                  className="btn-primary w-full rounded-full px-4 py-2.5 text-sm font-medium"
                >
                  Оплатить {formatPrice(lessonPackage.price_rub)}
                </button>
              </form>
            ) : (
              <Link
                href="/login"
                className="btn-primary flex w-full rounded-full px-4 py-2.5 text-center text-sm font-medium"
              >
                Войти и оплатить
              </Link>
            )}
          </div>
        </div>
        );
      })}
    </div>
  );
}
