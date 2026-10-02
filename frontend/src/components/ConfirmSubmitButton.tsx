"use client";

// Кнопка submit с подтверждением перед отправкой формы — для необратимых
// на вид действий (отмена записи и т.п.). Сама форма/server action не
// меняется, это только клиентская защита от случайного клика.
export function ConfirmSubmitButton({
  confirmMessage,
  className,
  children,
}: {
  confirmMessage: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="submit"
      className={className}
      onClick={(event) => {
        if (!window.confirm(confirmMessage)) {
          event.preventDefault();
        }
      }}
    >
      {children}
    </button>
  );
}
