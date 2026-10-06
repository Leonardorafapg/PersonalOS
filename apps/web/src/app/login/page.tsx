"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, inputCls } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const j = await res.json().catch(() => null);
      if (!res.ok) throw new Error(j?.error?.message || "Não foi possível entrar");
      router.replace("/");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro inesperado");
      setBusy(false);
    }
  };

  return (
    <main className="grid min-h-dvh place-items-center px-5">
      <form onSubmit={submit} className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <span className="relative grid size-14 place-items-center rounded-2xl bg-ink">
            <span className="size-6 rounded-full border-[3px] border-inkfg" />
            <span className="absolute right-3 top-3 size-2.5 rounded-full bg-accent" />
          </span>
          <h1 className="text-2xl font-semibold tracking-tight">Personal OS</h1>
          <p className="text-sm text-muted">Sua agenda, tarefas e estudos. Operados pelo Claude.</p>
        </div>
        <div className="space-y-3">
          <input className={inputCls} type="email" autoComplete="username" placeholder="E-mail" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
          <input className={inputCls} type="password" autoComplete="current-password" placeholder="Senha" value={password} onChange={(e) => setPassword(e.target.value)} required />
          {error && <p className="px-1 text-sm text-danger" role="alert">{error}</p>}
          <Button type="submit" className="w-full" loading={busy}>Entrar</Button>
        </div>
      </form>
    </main>
  );
}
