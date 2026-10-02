import type { Metadata } from "next";
import { getMyBookings, type UserBooking } from "@/lib/account";
import { formatClassDateTime } from "@/lib/format";

export const metadata: Metadata = {
  title: "Мои занятия",
};

export default async function AccountBookingsPage() {
  const bookings = await getMyBookings();
  const { upcoming, past } = splitByTime(bookings);

  return (
    <div className="flex flex-col gap-8">
      <section>
        <h2 className="mb-4 text-xl font-semibold">Предстоящие</h2>
        {upcoming.length === 0 ? (
          <p className="text-[var(--foreground)]/70">
            Пока нет предстоящих занятий. Запись на сайте появится на
            следующем этапе — выберите занятие в боте или в расписании.
          </p>
        ) : (
          <BookingList bookings={upcoming} />
        )}
      </section>

      <section>
        <h2 className="mb-4 text-xl font-semibold">Прошедшие</h2>
        {past.length === 0 ? (
          <p className="text-[var(--foreground)]/70">Пока нет истории занятий.</p>
        ) : (
          <BookingList bookings={past} />
        )}
      </section>
    </div>
  );
}

// Отдельная обычная функция, а не логика прямо в теле компонента: вызов
// Date.now() внутри функции компонента помечается линтером как нечистый.
function splitByTime(bookings: UserBooking[]) {
  const now = Date.now();
  return {
    upcoming: bookings.filter(
      (booking) => new Date(booking.starts_at).getTime() >= now,
    ),
    past: bookings.filter(
      (booking) => new Date(booking.starts_at).getTime() < now,
    ),
  };
}

function BookingList({ bookings }: { bookings: UserBooking[] }) {
  return (
    <ul className="flex flex-col gap-3">
      {bookings.map((booking) => (
        <li
          key={booking.id}
          className="flex flex-wrap items-baseline justify-between gap-2 rounded-lg border border-black/10 p-4"
        >
          <span className="font-medium">{booking.class_label}</span>
          <span className="text-sm text-[var(--foreground)]/70">
            {formatClassDateTime(booking.starts_at)}
          </span>
          {booking.slot_status !== "open" && (
            <span className="text-sm text-[var(--foreground)]/60">
              Занятие отменено студией
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
