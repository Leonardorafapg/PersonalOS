"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, Copy, LogOut, Plus, ShieldAlert, X } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Button, Chip, Field, Spinner, Toggle, cx, inputCls } from "@/components/ui";
import { useToast } from "@/components/providers";
import { api } from "@/lib/api";
import { useAct, usePrefs } from "@/lib/hooks";
import { WEEKDAYS } from "@/lib/time";
import type { Meal, Preferences } from "@/lib/types";

function Card({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="mt-5 rounded-2xl border border-line bg-surface p-5">
      <h2 className="text-[17px] font-semibold tracking-tight">{title}</h2>
      {hint && <p className="mt-0.5 text-sm text-muted">{hint}</p>}
      <div className="mt-4 space-y-4">{children}</div>
    </section>
  );
}

function PrefsForm({ prefs }: { prefs: Preferences }) {
  const act = useAct();
  const [f, setF] = useState(prefs);
  const zones = useMemo(() => {
    try { return (Intl as unknown as { supportedValuesOf: (k: string) => string[] }).supportedValuesOf("timeZone"); } catch { return [prefs.timezone]; }
  }, [prefs.timezone]);
  const set = <K extends keyof Preferences>(k: K, v: Preferences[K]) => setF((s) => ({ ...s, [k]: v }));
  const dirty = JSON.stringify(f) !== JSON.stringify(prefs);

  const save = () =>
    act(
      () =>
        api.patch("/preferences", {
          version: prefs.version, timezone: f.timezone, wake_time: f.wake_time, sleep_time: f.sleep_time,
          work_days: f.work_days, work_start: f.work_start, work_end: f.work_end, meals: f.meals,
          planning_rules: f.planning_rules.filter((r) => r.trim()), context_notes: f.context_notes,
          min_free_window_minutes: f.min_free_window_minutes,
        }),
      "Preferências salvas",
    );

  const setMeal = (i: number, patch: Partial<Meal>) => set("meals", f.meals.map((m, j) => (j === i ? { ...m, ...patch } : m)));

  return (
    <Card title="Rotina e preferências" hint="O Claude lê isto antes de planejar qualquer dia.">
      <Field label="Fuso horário">
        <select className={inputCls} value={f.timezone} onChange={(e) => set("timezone", e.target.value)}>
          {zones.map((z) => <option key={z} value={z}>{z}</option>)}
        </select>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Acordo às"><input type="time" className={inputCls} value={f.wake_time} onChange={(e) => set("wake_time", e.target.value)} /></Field>
        <Field label="Durmo às"><input type="time" className={inputCls} value={f.sleep_time} onChange={(e) => set("sleep_time", e.target.value)} /></Field>
      </div>
      <Field label="Dias de trabalho">
        <div className="flex gap-1.5">
          {WEEKDAYS.map((d, i) => (
            <button key={d} type="button" onClick={() => set("work_days", f.work_days.includes(i) ? f.work_days.filter((x) => x !== i) : [...f.work_days, i].sort())}
              className={cx("h-10 flex-1 rounded-lg text-xs font-medium transition", f.work_days.includes(i) ? "bg-ink text-inkfg" : "bg-surface2 text-muted")}>{d}</button>
          ))}
        </div>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Expediente: início"><input type="time" className={inputCls} value={f.work_start} onChange={(e) => set("work_start", e.target.value)} /></Field>
        <Field label="Expediente: fim"><input type="time" className={inputCls} value={f.work_end} onChange={(e) => set("work_end", e.target.value)} /></Field>
      </div>
      <Field label="Refeições">
        <div className="space-y-2">
          {f.meals.map((m, i) => (
            <div key={i} className="flex items-center gap-2">
              <input className={inputCls} value={m.name} onChange={(e) => setMeal(i, { name: e.target.value })} aria-label="Nome" />
              <input type="time" className={`${inputCls} w-32`} value={m.start} onChange={(e) => setMeal(i, { start: e.target.value })} aria-label="Início" />
              <input type="time" className={`${inputCls} w-32`} value={m.end} onChange={(e) => setMeal(i, { end: e.target.value })} aria-label="Fim" />
              <button type="button" aria-label="Remover" className="p-2 text-muted" onClick={() => set("meals", f.meals.filter((_, j) => j !== i))}><X className="size-4" /></button>
            </div>
          ))}
          <Button variant="ghost" size="sm" onClick={() => set("meals", [...f.meals, { name: "Refeição", start: "19:00", end: "19:30" }])}><Plus className="size-4" />Adicionar</Button>
        </div>
      </Field>
      <Field label="Regras de planejamento" hint="Em linguagem natural. Ex.: “Não estudar depois das 22h”, “Treino nunca na segunda”.">
        <div className="space-y-2">
          {f.planning_rules.map((r, i) => (
            <div key={i} className="flex gap-2">
              <input className={inputCls} value={r} onChange={(e) => set("planning_rules", f.planning_rules.map((x, j) => (j === i ? e.target.value : x)))} />
              <button type="button" aria-label="Remover" className="p-2 text-muted" onClick={() => set("planning_rules", f.planning_rules.filter((_, j) => j !== i))}><X className="size-4" /></button>
            </div>
          ))}
          <Button variant="ghost" size="sm" onClick={() => set("planning_rules", [...f.planning_rules, ""])}><Plus className="size-4" />Adicionar regra</Button>
        </div>
      </Field>
      <Field label="Contexto pessoal" hint="Qualquer coisa útil para o Claude entender sua rotina e prioridades.">
        <textarea className={inputCls} rows={4} value={f.context_notes} onChange={(e) => set("context_notes", e.target.value)} />
      </Field>
      <Button onClick={save} disabled={!dirty} className="w-full">Salvar preferências</Button>
    </Card>
  );
}

function CopyField({ value }: { value: string }) {
  const [ok, setOk] = useState(false);
  return (
    <div className="flex items-center gap-2 rounded-xl border border-line bg-surface2 px-3 py-2">
      <code className="min-w-0 flex-1 truncate text-sm">{value}</code>
      <button
        aria-label="Copiar"
        className="grid size-8 place-items-center rounded-lg hover:bg-surface"
        onClick={() => { navigator.clipboard?.writeText(value); setOk(true); setTimeout(() => setOk(false), 1500); }}
      >
        {ok ? <Check className="size-4 text-ok" /> : <Copy className="size-4" />}
      </button>
    </div>
  );
}

export default function SettingsPage() {
  const toast = useToast();
  const prefs = usePrefs();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api.get<{ email: string; mcp_url: string }>("/auth/me") });
  const [pw, setPw] = useState({ current: "", next: "" });
  const [busy, setBusy] = useState(false);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [notifications, setNotifications] = useState<NotificationPermission | "unsupported">(() =>
    typeof Notification === "undefined" ? "unsupported" : Notification.permission,
  );

  const changePw = async () => {
    setBusy(true);
    try {
      await api.post("/auth/change-password", { current_password: pw.current, new_password: pw.next });
      setPw({ current: "", next: "" });
      toast.show("Senha alterada. Outros dispositivos foram desconectados.");
    } catch (e) { toast.error(e); }
    setBusy(false);
  };
  const revoke = async () => {
    try {
      await api.post("/auth/revoke-all");
      setConfirmRevoke(false);
      toast.show("Todos os acessos foram revogados. Reconecte o Claude.");
    } catch (e) { toast.error(e); }
  };
  const logout = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    navigator.serviceWorker?.controller?.postMessage("logout");
    window.location.replace("/login");
  };

  if (prefs.isLoading) return <div className="grid place-items-center py-24"><Spinner /></div>;

  return (
    <div>
      <header className="pb-1 pt-2"><h1 className="text-[28px] font-semibold tracking-tight">Configurações</h1>
        <p className="text-sm text-muted">{me.data?.email}</p></header>

      <Card title="Conectar o Claude" hint="O app não tem IA própria: o Claude opera o app por um conector MCP.">
        <CopyField value={me.data?.mcp_url ?? "…"} />
        <ol className="list-decimal space-y-1.5 pl-5 text-sm text-muted">
          <li>No Claude (desktop): <b className="text-text">Configurações → Conectores → Adicionar conector personalizado</b>.</li>
          <li>Cole a URL acima e confirme. Uma janela abrirá para você entrar com o e-mail e a senha deste app.</li>
          <li>Pronto: peça “organiza meu dia de amanhã”. O acesso não expira; para encerrar, use “Revogar acessos”.</li>
        </ol>
      </Card>

      {prefs.data && <PrefsForm key={prefs.data.version} prefs={prefs.data} />}

      <Card title="Segurança">
        <Field label="Senha atual"><input type="password" autoComplete="current-password" className={inputCls} value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} /></Field>
        <Field label="Nova senha (mín. 8 caracteres)"><input type="password" autoComplete="new-password" className={inputCls} value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} /></Field>
        <Button variant="soft" onClick={changePw} loading={busy} disabled={pw.next.length < 8 || !pw.current}>Alterar senha</Button>
        <div className="rounded-xl border border-danger/30 p-4">
          <div className="flex items-start gap-3">
            <ShieldAlert className="mt-0.5 size-5 shrink-0 text-danger" />
            <div className="min-w-0 flex-1">
              <p className="font-medium">Revogar todos os acessos</p>
              <p className="mt-0.5 text-sm text-muted">Desconecta o Claude e todos os dispositivos (os tokens não expiram sozinhos). Este dispositivo continua conectado.</p>
              <Button variant="danger" size="sm" className="mt-3" onClick={confirmRevoke ? revoke : () => setConfirmRevoke(true)}>{confirmRevoke ? "Confirmar revogação" : "Revogar acessos"}</Button>
            </div>
          </div>
        </div>
      </Card>

      <Card title="Este dispositivo">
        <div className="flex items-center justify-between gap-3">
          <div><p className="text-[15px]">Instalar como app</p><p className="text-sm text-muted">No celular: menu do navegador → “Adicionar à tela inicial”.</p></div>
          <Chip>PWA</Chip>
        </div>
        {notifications !== "unsupported" && (
          <div className="flex items-center justify-between gap-3">
            <div><p className="text-[15px]">Notificações</p><p className="text-sm text-muted">Lembretes chegam em uma versão futura.</p></div>
            <Toggle checked={notifications === "granted"} onChange={() => Notification.requestPermission().then(setNotifications)} label="Notificações" />
          </div>
        )}
        <Button variant="soft" onClick={logout}><LogOut className="size-4" />Sair</Button>
      </Card>
    </div>
  );
}
