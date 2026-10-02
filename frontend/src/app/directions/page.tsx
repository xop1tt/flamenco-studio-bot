import type { Metadata } from "next";
import Link from "next/link";
import { getDirections } from "@/lib/directions";

export const metadata: Metadata = {
  title: "Направления",
};

// Подписи направлений приходят с backend — страницу нельзя кэшировать
// статически на этапе сборки, см. frontend/README.md.
export const dynamic = "force-dynamic";

export default async function DirectionsPage() {
  const directions = await getDirections();

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-12">
      <h1 className="text-3xl font-bold">Направления</h1>
      <div className="flex flex-col gap-6">
        {directions.map((direction) => (
          <div
            key={direction.key}
            className="rounded-lg border border-black/10 p-6"
          >
            <h2 className="mb-2 text-xl font-semibold">{direction.label}</h2>
            <p className="mb-4 text-[var(--foreground)]/80">
              {direction.description}
            </p>
            <Link
              href={`/schedule?class_key=${direction.key}`}
              className="text-sm font-medium text-[var(--accent)] hover:underline"
            >
              Расписание этого направления →
            </Link>
          </div>
        ))}
      </div>
    </div>
  );
}
