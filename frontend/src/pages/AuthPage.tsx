import { useMutation } from "@tanstack/react-query";
import { type FormEvent, type InputHTMLAttributes, useState } from "react";
import { api } from "../lib/api";
import type { AuthUser } from "../types";

export function AuthPage({ onAuthenticated }: { onAuthenticated: (user: AuthUser) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [localError, setLocalError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (values: { email: string; password: string; display_name?: string }) =>
      mode === "login"
        ? api.login({ email: values.email, password: values.password })
        : api.register({ email: values.email, password: values.password, display_name: values.display_name ?? "" }),
    onSuccess: (user) => onAuthenticated(user),
  });

  function switchMode(next: "login" | "register") {
    setMode(next);
    setLocalError(null);
    mutation.reset();
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLocalError(null);
    const data = new FormData(event.currentTarget);
    const password = String(data.get("password") ?? "");
    if (mode === "register" && password !== String(data.get("password_confirm") ?? "")) {
      setLocalError("Пароли не совпадают.");
      return;
    }
    mutation.mutate({
      email: String(data.get("email") ?? ""),
      password,
      display_name: String(data.get("display_name") ?? ""),
    });
  }

  const error = localError ?? mutation.error?.message;
  return (
    <main className="grid min-h-screen place-items-center bg-admin-bg px-4 py-10">
      <div className="w-full max-w-md overflow-hidden rounded-2xl border border-admin-border bg-white shadow-xl shadow-black/5">
        <div className="bg-admin-sidebar px-7 py-7 text-white">
          <div className="flex items-center gap-3">
            <div className="grid size-11 place-items-center rounded-xl bg-admin-primary text-lg font-bold">JF</div>
            <div><h1 className="text-lg font-semibold">Job Finder</h1><p className="text-sm text-white/55">Frontend вакансии</p></div>
          </div>
        </div>
        <div className="p-7">
          <div className="grid grid-cols-2 rounded-xl bg-admin-bg p-1" role="tablist" aria-label="Авторизация">
            <button className={`rounded-lg px-3 py-2 text-sm font-semibold transition ${mode === "login" ? "bg-white text-admin-primary shadow-sm" : "text-admin-muted"}`} onClick={() => switchMode("login")} role="tab" aria-selected={mode === "login"} type="button">Вход</button>
            <button className={`rounded-lg px-3 py-2 text-sm font-semibold transition ${mode === "register" ? "bg-white text-admin-primary shadow-sm" : "text-admin-muted"}`} onClick={() => switchMode("register")} role="tab" aria-selected={mode === "register"} type="button">Регистрация</button>
          </div>

          <div className="mt-6">
            <h2 className="text-xl font-semibold text-admin-ink">{mode === "login" ? "Войти в аккаунт" : "Создать аккаунт"}</h2>
            <p className="mt-1 text-sm leading-5 text-admin-muted">
              {mode === "login" ? "Ваши компании, вакансии и резюме останутся только на этом компьютере." : "Первый аккаунт автоматически получит ваши существующие локальные данные."}
            </p>
          </div>

          <form className="mt-6 space-y-4" onSubmit={submit}>
            {mode === "register" && <AuthField autoComplete="name" label="Имя" name="display_name" placeholder="David" required />}
            <AuthField autoComplete="email" label="Email" name="email" placeholder="name@example.com" required type="email" />
            <AuthField autoComplete={mode === "login" ? "current-password" : "new-password"} label="Пароль" minLength={8} name="password" placeholder="Минимум 8 символов" required type="password" />
            {mode === "register" && <AuthField autoComplete="new-password" label="Повторите пароль" minLength={8} name="password_confirm" placeholder="Повторите пароль" required type="password" />}
            {error && <p className="rounded-xl bg-red-50 px-3 py-2.5 text-sm text-red-700" role="alert">{error}</p>}
            <button className="w-full rounded-xl bg-admin-primary px-4 py-3 text-sm font-semibold text-white transition hover:bg-admin-primary-dark disabled:cursor-wait disabled:opacity-60" disabled={mutation.isPending} type="submit">
              {mutation.isPending ? "Подождите…" : mode === "login" ? "Войти" : "Создать аккаунт"}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}

function AuthField({ label, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="block text-sm font-medium text-admin-ink">
      {label}
      <input {...props} className="mt-1.5 w-full rounded-xl border border-admin-border bg-white px-3.5 py-3 text-sm outline-none transition placeholder:text-admin-muted/60 focus:border-admin-primary focus:ring-2 focus:ring-admin-primary/10" />
    </label>
  );
}
