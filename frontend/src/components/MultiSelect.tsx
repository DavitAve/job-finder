import { useCallback, useRef, useState } from "react";
import { useOutsideClick } from "../hooks/useOutsideClick";
import { ChevronDownIcon } from "./Icons";

interface Props {
  label: string;
  options: string[];
  selected: string[];
  emptyLabel: string;
  selectedLabel: (count: number) => string;
  onToggle: (option: string) => void;
  controlClassName: string;
}

export function MultiSelect({ label, options, selected, emptyLabel, selectedLabel, onToggle, controlClassName }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useOutsideClick(rootRef, close, open);
  return (
    <div className="grid min-w-0 gap-1.5 text-xs font-medium text-admin-muted" ref={rootRef}>
      <span>{label}</span>
      <div className="relative min-w-0">
        <button aria-expanded={open} aria-haspopup="listbox" className={`${controlClassName} flex w-full items-center justify-between`} onClick={() => setOpen((value) => !value)} type="button">
          <span className="truncate">{selected.length ? selectedLabel(selected.length) : emptyLabel}</span>
          <ChevronDownIcon className={`size-4 shrink-0 transition ${open ? "rotate-180" : ""}`} />
        </button>
        {open && (
          <div className="absolute z-20 mt-1 max-h-64 w-full min-w-48 overflow-auto rounded-lg border border-admin-border bg-white p-2 shadow-lg" role="listbox" aria-label={label}>
            {options.length ? options.map((option) => (
              <label className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm text-admin-ink hover:bg-admin-soft" key={option}>
                <input className="accent-admin-primary" type="checkbox" checked={selected.includes(option)} onChange={() => onToggle(option)} />{option}
              </label>
            )) : <p className="p-2 text-sm font-normal text-admin-muted">Нет данных</p>}
          </div>
        )}
      </div>
    </div>
  );
}
