import type { Metadata } from "next";
import { getPackages } from "@/lib/api";
import { PackagesGrid } from "@/components/PackagesGrid";

export const metadata: Metadata = {
  title: "Абонементы",
};

// Цены и состав абонементов задаёт backend — не кэшируем статически на
// этапе сборки, иначе сайт будет показывать устаревший каталог.
export const dynamic = "force-dynamic";

export default async function PackagesPage() {
  const packages = await getPackages();

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-12">
      <h1 className="text-3xl font-bold">Абонементы</h1>
      <p className="max-w-2xl text-[var(--foreground)]/80">
        Разовое занятие или абонемент на несколько занятий — цены и состав
        всегда актуальны, их определяет студия.
      </p>
      <PackagesGrid packages={packages} />
    </div>
  );
}
