import { useEffect, useRef } from "react";
import type { FormEventHandler, ReactNode, RefObject } from "react";
import { useOutsideClick } from "../hooks/useOutsideClick";
import { CloseIcon } from "./Icons";

interface Props {
  children: ReactNode;
  labelledBy: string;
  onClose: () => void;
  closeDisabled?: boolean;
  as?: "div" | "form";
  onSubmit?: FormEventHandler<HTMLFormElement>;
  size?: "default" | "wide";
}

export function Modal({ children, labelledBy, onClose, closeDisabled = false, as = "div", onSubmit, size = "default" }: Props) {
  const contentRef = useRef<HTMLDivElement | HTMLFormElement>(null);
  useOutsideClick(contentRef, onClose, !closeDisabled);
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !closeDisabled) onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [closeDisabled, onClose]);

  const className = `relative max-h-[calc(100dvh-1rem)] w-full min-w-0 overflow-x-hidden overflow-y-auto rounded-xl bg-white p-4 shadow-2xl sm:max-h-[calc(100dvh-2rem)] sm:rounded-2xl sm:p-6 ${size === "wide" ? "max-w-5xl" : "max-w-lg"}`;
  const closeButton = (
    <button aria-label="Закрыть" className="absolute right-4 top-4 rounded-lg p-1.5 text-admin-muted transition hover:bg-admin-soft hover:text-admin-ink disabled:opacity-40" disabled={closeDisabled} onClick={onClose} type="button">
      <CloseIcon className="size-5" />
    </button>
  );
  return (
    <div className="fixed inset-0 z-50 grid min-w-0 place-items-center overflow-hidden bg-black/45 p-2 sm:p-4" role="dialog" aria-modal="true" aria-labelledby={labelledBy}>
      {as === "form" ? (
        <form ref={contentRef as RefObject<HTMLFormElement>} className={className} onSubmit={onSubmit}>{closeButton}{children}</form>
      ) : (
        <div ref={contentRef as RefObject<HTMLDivElement>} className={className}>{closeButton}{children}</div>
      )}
    </div>
  );
}
