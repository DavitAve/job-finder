import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { ErrorState, LoadingState } from "../components/QueryState";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";

export function AccountPage() {
  const client = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const resumes = useQuery({ queryKey: ["resumes"], queryFn: api.resumes });
  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState<"en" | "ru">("en");
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["resumes"] });
    void client.invalidateQueries({ queryKey: ["resume-matches"] });
  };
  const upload = useMutation({
    mutationFn: () => api.uploadResume(file!, language),
    onSuccess: () => {
      setFile(null);
      if (input.current) input.current.value = "";
      refresh();
    },
  });
  const activate = useMutation({ mutationFn: api.activateResume, onSuccess: refresh });
  const remove = useMutation({ mutationFn: api.deleteResume, onSuccess: refresh });
  const full = (resumes.data?.resumes.length ?? 0) >= (resumes.data?.limit ?? 3);
  const error = upload.error ?? activate.error ?? remove.error;

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-4 sm:p-6 lg:p-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-admin-ink">Аккаунт и резюме</h1>
        <p className="mt-1 text-sm text-admin-muted">Добавьте до трёх PDF-резюме и выберите одно для оценки вакансий.</p>
      </header>

      <section className="rounded-xl border border-admin-border bg-white p-5">
        <div className="grid gap-4 md:grid-cols-[1fr_180px_auto] md:items-end">
          <label className="grid gap-1.5 text-xs font-medium text-admin-muted">
            PDF-резюме, максимум 5 МБ
            <input ref={input} className="block h-10 rounded-lg border border-admin-border bg-white px-3 py-2 text-sm file:mr-3 file:border-0 file:bg-transparent file:font-medium file:text-admin-primary" type="file" accept="application/pdf,.pdf" disabled={full} onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          </label>
          <label className="grid gap-1.5 text-xs font-medium text-admin-muted">
            Язык резюме
            <select className="h-10 rounded-lg border border-admin-border bg-white px-3 text-sm" value={language} onChange={(event) => setLanguage(event.target.value as "en" | "ru")}><option value="en">Английский</option><option value="ru">Русский</option></select>
          </label>
          <button className="h-10 rounded-lg bg-admin-primary px-4 text-sm font-semibold text-white transition hover:bg-admin-primary-dark disabled:cursor-not-allowed disabled:opacity-50" disabled={!file || full || upload.isPending} onClick={() => upload.mutate()}>{upload.isPending ? "Загружаем…" : "Добавить резюме"}</button>
        </div>
        <p className="mt-3 text-xs text-admin-muted">Файлы и извлечённый текст хранятся только локально. Сканированные PDF без текстового слоя пока не поддерживаются.</p>
        {full && <p className="mt-3 text-sm font-medium text-admin-primary">Достигнут лимит — удалите одно резюме, чтобы добавить новое.</p>}
      </section>

      {error && <ErrorState message={error.message} />}
      {resumes.isLoading ? <LoadingState /> : resumes.isError ? <ErrorState message={resumes.error.message} onRetry={() => void resumes.refetch()} /> : !resumes.data?.resumes.length ? (
        <div className="rounded-xl border border-dashed border-admin-border bg-white px-6 py-14 text-center"><p className="font-medium text-admin-ink">Резюме ещё не добавлены</p><p className="mt-1 text-sm text-admin-muted">После загрузки первого PDF оно автоматически станет активным.</p></div>
      ) : (
        <section className="grid gap-4 lg:grid-cols-2">
          {resumes.data.resumes.map((resume) => (
            <article className={`rounded-xl border bg-white p-5 transition ${resume.active ? "border-admin-primary ring-2 ring-admin-primary/10" : "border-admin-border"}`} key={resume.id}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0"><h2 className="truncate font-semibold text-admin-ink" title={resume.filename}>{resume.filename}</h2><p className="mt-1 text-xs text-admin-muted">{resume.language === "en" ? "Английский" : "Русский"} · {resume.page_count} стр. · {(resume.size_bytes / 1024).toFixed(0)} КБ</p></div>
                {resume.active && <span className="shrink-0 rounded-full bg-admin-primary/10 px-2.5 py-1 text-xs font-semibold text-admin-primary">Активное</span>}
              </div>
              <p className="mt-3 text-xs text-admin-muted">Добавлено: {formatDate(resume.created_at)}</p>
              <div className="mt-3 flex min-h-7 flex-wrap gap-1.5">{resume.skills.length ? resume.skills.map((skill) => <span className="rounded-md bg-admin-soft px-2 py-1 text-xs text-admin-primary-dark" key={skill}>{skill}</span>) : <span className="text-xs text-admin-muted">Технологии автоматически не определены</span>}</div>
              <div className="mt-5 flex justify-end gap-2">
                {!resume.active && <button className="pager-button" disabled={activate.isPending} onClick={() => activate.mutate(resume.id)}>Сделать активным</button>}
                <button className="h-9 rounded-lg border border-red-200 px-3 text-sm font-medium text-red-700 hover:bg-red-50" disabled={remove.isPending} onClick={() => window.confirm(`Удалить резюме «${resume.filename}»?`) && remove.mutate(resume.id)}>Удалить</button>
              </div>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
