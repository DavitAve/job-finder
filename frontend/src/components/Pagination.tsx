import type { RefObject } from "react";
import { ChevronLeftIcon, ChevronRightIcon } from "./Icons";

interface Props {
  page: number;
  pages: number;
  onChange: (page: number) => void;
  scrollTarget?: RefObject<HTMLElement | null>;
}

export function Pagination({ page, pages, onChange, scrollTarget }: Props) {
  const changePage = (nextPage: number) => {
    onChange(nextPage);
    window.requestAnimationFrame(() => scrollTarget?.current?.scrollIntoView?.({ behavior: "smooth", block: "start" }));
  };
  return (
    <div className="flex items-center gap-2">
      <button aria-label="Назад" className="pager-button inline-flex items-center gap-1" disabled={page === 1} onClick={() => changePage(page - 1)} type="button"><ChevronLeftIcon className="size-4" /> Назад</button>
      <span>{page} / {pages}</span>
      <button aria-label="Далее" className="pager-button inline-flex items-center gap-1" disabled={page === pages} onClick={() => changePage(page + 1)} type="button">Далее <ChevronRightIcon className="size-4" /></button>
    </div>
  );
}
