import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";
import { API_UNAVAILABLE_EVENT } from "../lib/events";
import { CloseIcon } from "./Icons";

export type ToastTone = "info" | "success" | "warning" | "error";

interface ToastInput {
  title: string;
  message?: string;
  tone?: ToastTone;
  dedupeKey?: string;
  duration?: number;
}

interface ToastItem extends ToastInput {
  id: number;
}

interface ToastContextValue {
  showToast: (toast: ToastInput) => void;
  closeToast: (id: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const toneClasses: Record<ToastTone, string> = {
  info: "border-admin-primary/30 text-admin-primary",
  success: "border-emerald-300 text-emerald-700",
  warning: "border-amber-300 text-amber-700",
  error: "border-red-300 text-red-700",
};

export function ToastProvider({ children }: PropsWithChildren) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const closeToast = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback((input: ToastInput) => {
    setToasts((current) => {
      if (input.dedupeKey && current.some((toast) => toast.dedupeKey === input.dedupeKey)) {
        return current;
      }
      return [...current, { ...input, id: nextId.current++ }];
    });
  }, []);

  useEffect(() => {
    const showUnavailable = () => showToast({
      title: "API недоступен",
      message: "Не удалось подключиться к backend. Проверьте, запущен ли сервер.",
      tone: "error",
      dedupeKey: "api-unavailable",
      duration: 8_000,
    });
    window.addEventListener(API_UNAVAILABLE_EVENT, showUnavailable);
    return () => window.removeEventListener(API_UNAVAILABLE_EVENT, showUnavailable);
  }, [showToast]);

  const value = useMemo(() => ({ showToast, closeToast }), [closeToast, showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[calc(100%-2rem)] max-w-sm flex-col gap-3"
        aria-label="Уведомления"
      >
        {toasts.map((toast) => (
          <ToastCard key={toast.id} toast={toast} onClose={closeToast} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastCard({ toast, onClose }: { toast: ToastItem; onClose: (id: number) => void }) {
  useEffect(() => {
    const timer = window.setTimeout(() => onClose(toast.id), toast.duration ?? 6_000);
    return () => window.clearTimeout(timer);
  }, [onClose, toast.duration, toast.id]);

  const tone = toast.tone ?? "info";
  return (
    <div
      className={`pointer-events-auto flex items-start gap-3 rounded-xl border bg-white p-4 shadow-lg ${toneClasses[tone]}`}
      role={tone === "error" ? "alert" : "status"}
    >
      <span className="mt-1 size-2 shrink-0 rounded-full bg-current" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-admin-ink">{toast.title}</p>
        {toast.message && <p className="mt-1 text-sm leading-5 text-admin-muted">{toast.message}</p>}
      </div>
      <button
        className="-mr-1 -mt-1 grid size-8 shrink-0 place-items-center rounded-lg text-admin-muted transition hover:bg-admin-soft hover:text-admin-ink"
        onClick={() => onClose(toast.id)}
        type="button"
        aria-label={`Закрыть уведомление «${toast.title}»`}
      >
        <CloseIcon className="size-4" />
      </button>
    </div>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside ToastProvider");
  return context;
}
