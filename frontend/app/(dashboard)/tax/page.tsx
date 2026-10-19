"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Download,
  FileText,
  Landmark,
  Printer,
  RefreshCw,
  Scale,
  ShieldCheck,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PageLoader } from "@/components/ui/page-loader";
import { Spinner } from "@/components/ui/spinner";
import { ApiError, normalizeApiBase } from "@/lib/api";
import {
  classifyTaxPeriod,
  fetchTaxFramework,
  fetchTaxProfile,
  generateTaxReturn,
  getTaxReturn,
  listTaxReturns,
  saveTaxProfile,
  updateTaxReturnStatus,
  type TaxProfile,
  type TaxReportPack,
  type TaxReturnSummary,
  type TaxSchedule,
} from "@/lib/tax";
import { formatCurrency } from "@/lib/utils";
import { createClient } from "@/lib/supabase/client";

type Tab = "overview" | "profile" | "classify" | "report";

function money(n: unknown, currency = "NGN") {
  const v = typeof n === "number" ? n : Number(n || 0);
  return formatCurrency(v, currency === "NGN" ? "NGN" : currency);
}

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "FINALIZED"
      ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
      : status === "IN_REVIEW"
        ? "bg-amber-500/15 text-amber-200 border-amber-500/30"
        : "bg-slate-500/15 text-slate-300 border-slate-500/30";
  return <span className={`rounded border px-2 py-0.5 text-xs ${tone}`}>{status}</span>;
}

function ScheduleLines({ lines }: { lines: unknown }) {
  const flat: Array<Record<string, unknown>> = [];
  if (Array.isArray(lines)) {
    for (const x of lines) if (x && typeof x === "object") flat.push(x as Record<string, unknown>);
  } else if (lines && typeof lines === "object") {
    for (const v of Object.values(lines as Record<string, unknown>)) {
      if (Array.isArray(v)) {
        for (const x of v) if (x && typeof x === "object") flat.push(x as Record<string, unknown>);
      }
    }
  }
  if (flat.length === 0) {
    return <p className="text-sm text-slate-500">No line items in this schedule.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead>
          <tr className="border-b border-slate-800 text-slate-400">
            <th className="py-2 pr-3 font-medium">Date</th>
            <th className="py-2 pr-3 font-medium">Description</th>
            <th className="py-2 pr-3 font-medium">VAT</th>
            <th className="py-2 pr-3 font-medium">WHT</th>
            <th className="py-2 pr-3 font-medium text-right">Gross</th>
            <th className="py-2 font-medium text-right">Tax amt</th>
          </tr>
        </thead>
        <tbody>
          {flat.slice(0, 200).map((line, i) => (
            <tr key={i} className="border-b border-slate-800/60">
              <td className="py-2 pr-3 text-slate-300">{String(line.date || "—")}</td>
              <td className="py-2 pr-3 text-slate-200">
                <div>{String(line.description || "—")}</div>
                <div className="text-xs text-slate-500">{String(line.merchant || "")}</div>
              </td>
              <td className="py-2 pr-3 text-xs text-slate-400">{String(line.vat_treatment || "—")}</td>
              <td className="py-2 pr-3 text-xs text-slate-400">{String(line.wht_category || "—")}</td>
              <td className="py-2 pr-3 text-right tabular-nums text-slate-200">
                {money(line.gross_amount)}
              </td>
              <td className="py-2 text-right tabular-nums text-slate-200">
                {money(Number(line.vat_amount || 0) + Number(line.wht_amount || 0))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {flat.length > 200 && (
        <p className="mt-2 text-xs text-slate-500">Showing first 200 of {flat.length} lines. Export CSV for full pack.</p>
      )}
    </div>
  );
}

export default function TaxPage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<TaxProfile | null>(null);
  const [framework, setFramework] = useState<Record<string, unknown> | null>(null);
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [returns, setReturns] = useState<TaxReturnSummary[]>([]);
  const [activeReturnId, setActiveReturnId] = useState<string | null>(null);
  const [report, setReport] = useState<TaxReportPack | null>(null);
  const [returnStatus, setReturnStatus] = useState<string>("DRAFT");
  const [classifyPreview, setClassifyPreview] = useState<Array<Record<string, unknown>>>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [fw, pf, list] = await Promise.all([
        fetchTaxFramework(),
        fetchTaxProfile(),
        listTaxReturns(),
      ]);
      setFramework(fw.references);
      setPeriodStart(fw.default_period_start);
      setPeriodEnd(fw.default_period_end);
      setProfile(pf);
      setReturns(list.items);
      if (list.items[0]?.id) {
        setActiveReturnId(list.items[0].id);
        const full = await getTaxReturn(list.items[0].id);
        setReturnStatus(full.return.status);
        setReport(full.return.report_json || null);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load tax module");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const liabilities = report?.liabilities || report?.cover?.liabilities;

  const tabs: { id: Tab; label: string }[] = [
    { id: "overview", label: "Statutory Overview" },
    { id: "profile", label: "Taxpayer Profile" },
    { id: "classify", label: "Classification" },
    { id: "report", label: "Report Pack" },
  ];

  async function onSaveProfile() {
    if (!profile) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await saveTaxProfile(profile);
      setProfile(saved);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to save profile");
    } finally {
      setBusy(false);
    }
  }

  async function onClassify() {
    if (!periodStart || !periodEnd) return;
    setBusy(true);
    setError(null);
    try {
      const res = await classifyTaxPeriod({
        date_from: periodStart,
        date_to: periodEnd,
        persist: true,
      });
      setClassifyPreview(res.items.slice(0, 100));
      setTab("classify");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Classification failed");
    } finally {
      setBusy(false);
    }
  }

  async function onGenerate() {
    if (!periodStart || !periodEnd) return;
    setBusy(true);
    setError(null);
    try {
      const res = await generateTaxReturn({
        period_start: periodStart,
        period_end: periodEnd,
        include_books_pnl: true,
        persist_classifications: true,
      });
      setReport(res.report);
      setActiveReturnId(res.return.id);
      setReturnStatus(res.return.status || "DRAFT");
      const list = await listTaxReturns();
      setReturns(list.items);
      setTab("report");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to generate tax report");
    } finally {
      setBusy(false);
    }
  }

  async function onOpenReturn(id: string) {
    setBusy(true);
    try {
      const full = await getTaxReturn(id);
      setActiveReturnId(id);
      setReturnStatus(full.return.status);
      setReport(full.return.report_json || null);
      setPeriodStart(full.return.period_start);
      setPeriodEnd(full.return.period_end);
      setTab("report");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to open return");
    } finally {
      setBusy(false);
    }
  }

  async function onStatus(status: "DRAFT" | "IN_REVIEW" | "FINALIZED") {
    if (!activeReturnId) return;
    setBusy(true);
    try {
      const updated = await updateTaxReturnStatus(activeReturnId, status);
      setReturnStatus(updated.status);
      const list = await listTaxReturns();
      setReturns(list.items);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Status update failed");
    } finally {
      setBusy(false);
    }
  }

  async function onExportCsv() {
    if (!activeReturnId) return;
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session?.access_token) {
      setError("Sign in required to export");
      return;
    }
    const base = normalizeApiBase(process.env.NEXT_PUBLIC_FASTAPI_URL);
    const res = await fetch(`${base}/tax/returns/${activeReturnId}/export.csv`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
    });
    if (!res.ok) {
      setError("CSV export failed");
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `whorl-nigeria-tax-${activeReturnId}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const schedules: TaxSchedule[] = useMemo(() => report?.schedules || [], [report]);

  if (loading) return <PageLoader label="Loading Nigeria tax workspace…" />;

  return (
    <div className="space-y-6 print:space-y-4">
      <div className="flex flex-col gap-4 print:hidden md:flex-row md:items-end md:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2 text-emerald-400">
            <Scale className="h-5 w-5" />
            <span className="text-xs font-semibold uppercase tracking-[0.18em]">Nigeria Statutory Tax</span>
          </div>
          <h1 className="text-2xl font-semibold text-white md:text-3xl">Tax & Statutory Reporting</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-400">
            Combined VAT, WHT, Companies Income Tax and Development Levy report pack under the{" "}
            <span className="text-slate-200">Nigeria Tax Act, 2025</span> — structured for professional
            review and presentation to FIRS.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => load()} disabled={busy}>
            <RefreshCw className="mr-2 h-4 w-4" /> Refresh
          </Button>
          <Button variant="outline" onClick={onClassify} disabled={busy || !periodStart}>
            {busy ? <Spinner /> : null}
            Classify period
          </Button>
          <Button onClick={onGenerate} disabled={busy || !periodStart}>
            <FileText className="mr-2 h-4 w-4" />
            Generate report pack
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200 print:hidden">
          {error}
        </div>
      )}

      <div className="grid gap-3 print:hidden md:grid-cols-4">
        <Card className="border-slate-800 bg-slate-950/80">
          <CardHeader className="pb-2">
            <CardDescription>Report period</CardDescription>
            <div className="mt-2 flex gap-2">
              <Input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
              <Input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
            </div>
          </CardHeader>
        </Card>
        <Card className="border-slate-800 bg-slate-950/80">
          <CardHeader className="pb-2">
            <CardDescription>Net VAT</CardDescription>
            <CardTitle className="text-xl tabular-nums">
              {liabilities ? money(liabilities.vat_payable ?? liabilities.net_vat_payable) : "—"}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card className="border-slate-800 bg-slate-950/80">
          <CardHeader className="pb-2">
            <CardDescription>WHT remittable</CardDescription>
            <CardTitle className="text-xl tabular-nums">
              {liabilities ? money(liabilities.wht_remittable) : "—"}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card className="border-slate-800 bg-slate-950/80">
          <CardHeader className="pb-2">
            <CardDescription>CIT + Development Levy</CardDescription>
            <CardTitle className="text-xl tabular-nums">
              {liabilities
                ? money(
                    Number(liabilities.cit_payable || 0) + Number(liabilities.development_levy_payable || 0)
                  )
                : "—"}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-slate-800 pb-2 print:hidden">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`rounded-md px-3 py-1.5 text-sm transition ${
              tab === t.id ? "bg-emerald-600/20 text-emerald-300" : "text-slate-400 hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
          <Card className="border-slate-800 bg-slate-950/70 p-5">
            <div className="mb-4 flex items-center gap-2 text-white">
              <Landmark className="h-5 w-5 text-emerald-400" />
              <h2 className="text-lg font-semibold">Authority framework</h2>
            </div>
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-slate-500">Framework</dt>
                <dd className="text-slate-200">{String(framework?.framework || "Nigeria Tax Act, 2025")}</dd>
              </div>
              <div>
                <dt className="text-slate-500">VAT rate</dt>
                <dd className="text-slate-200">7.5%</dd>
              </div>
              <div>
                <dt className="text-slate-500">CIT (large)</dt>
                <dd className="text-slate-200">30%</dd>
              </div>
              <div>
                <dt className="text-slate-500">Development Levy</dt>
                <dd className="text-slate-200">4% of assessable profits</dd>
              </div>
              <div>
                <dt className="text-slate-500">Small company test</dt>
                <dd className="text-slate-200">Turnover ≤ ₦100m and fixed assets ≤ ₦250m</dd>
              </div>
              <div>
                <dt className="text-slate-500">Filing cadence</dt>
                <dd className="text-slate-200">VAT / WHT — due by 21st of following month</dd>
              </div>
            </dl>
            <ul className="mt-5 space-y-2 text-sm text-slate-400">
              {(Array.isArray(framework?.notes) ? (framework?.notes as string[]) : []).map((n) => (
                <li key={n} className="flex gap-2">
                  <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                  <span>{n}</span>
                </li>
              ))}
            </ul>
          </Card>

          <Card className="border-slate-800 bg-slate-950/70 p-5">
            <h2 className="mb-3 text-lg font-semibold text-white">Recent report packs</h2>
            <div className="space-y-2">
              {returns.length === 0 && <p className="text-sm text-slate-500">No packs generated yet.</p>}
              {returns.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => onOpenReturn(r.id)}
                  className="flex w-full items-center justify-between rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2 text-left hover:border-emerald-500/40"
                >
                  <div>
                    <p className="text-sm text-white">{r.period_label}</p>
                    <p className="text-xs text-slate-500">{r.return_type}</p>
                  </div>
                  <StatusBadge status={r.status} />
                </button>
              ))}
            </div>
          </Card>
        </div>
      )}

      {tab === "profile" && profile && (
        <Card className="border-slate-800 bg-slate-950/70 p-5 print:hidden">
          <h2 className="mb-4 text-lg font-semibold text-white">Taxpayer profile</h2>
          <div className="grid gap-3 md:grid-cols-2">
            {(
              [
                ["legal_name", "Legal name"],
                ["trading_name", "Trading name"],
                ["tin", "TIN"],
                ["rc_number", "RC number"],
                ["tax_office", "Tax office"],
                ["state_of_operation", "State of operation"],
                ["business_address", "Business address"],
                ["sector", "Sector"],
                ["contact_name", "Contact name"],
                ["contact_email", "Contact email"],
                ["contact_phone", "Contact phone"],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="text-sm">
                <span className="mb-1 block text-slate-400">{label}</span>
                <Input
                  value={String(profile[key] ?? "")}
                  onChange={(e) => setProfile({ ...profile, [key]: e.target.value })}
                />
              </label>
            ))}
            <label className="text-sm">
              <span className="mb-1 block text-slate-400">Fixed assets (₦)</span>
              <Input
                type="number"
                value={profile.fixed_assets_ngn ?? 0}
                onChange={(e) =>
                  setProfile({ ...profile, fixed_assets_ngn: Number(e.target.value || 0) })
                }
              />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-400">Entity type</span>
              <select
                className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
                value={profile.entity_type}
                onChange={(e) =>
                  setProfile({
                    ...profile,
                    entity_type: e.target.value as TaxProfile["entity_type"],
                  })
                }
              >
                <option value="COMPANY">Company</option>
                <option value="ENTERPRISE">Enterprise</option>
                <option value="PARTNERSHIP">Partnership</option>
                <option value="INDIVIDUAL">Individual</option>
              </select>
            </label>
          </div>
          <div className="mt-4">
            <Button onClick={onSaveProfile} disabled={busy}>
              Save taxpayer profile
            </Button>
          </div>
        </Card>
      )}

      {tab === "classify" && (
        <Card className="border-slate-800 bg-slate-950/70 p-5 print:hidden">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-white">Period classification</h2>
              <p className="text-sm text-slate-400">
                Auto-tagged for VAT, WHT, CIT and levies from Nigerian narrations and categories.
              </p>
            </div>
            <Button onClick={onClassify} disabled={busy}>
              Re-run classification
            </Button>
          </div>
          {classifyPreview.length === 0 ? (
            <p className="text-sm text-slate-500">Run classification for the selected period to preview tags.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400">
                    <th className="py-2 pr-3">Date</th>
                    <th className="py-2 pr-3">Description</th>
                    <th className="py-2 pr-3">VAT</th>
                    <th className="py-2 pr-3">WHT</th>
                    <th className="py-2 pr-3">CIT</th>
                    <th className="py-2 text-right">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {classifyPreview.map((row) => (
                    <tr key={String(row.transaction_id)} className="border-b border-slate-800/50">
                      <td className="py-2 pr-3 text-slate-300">{String(row.date || "")}</td>
                      <td className="py-2 pr-3 text-slate-200">
                        <div>{String(row.description || "")}</div>
                        <div className="text-xs text-slate-500">{String(row.rationale || "")}</div>
                      </td>
                      <td className="py-2 pr-3 text-xs">{String(row.vat_treatment)}</td>
                      <td className="py-2 pr-3 text-xs">{String(row.wht_category)}</td>
                      <td className="py-2 pr-3 text-xs">{String(row.cit_treatment)}</td>
                      <td className="py-2 text-right tabular-nums">{money(row.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === "report" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 print:hidden">
            {activeReturnId && <StatusBadge status={returnStatus} />}
            <Button variant="outline" size="sm" onClick={() => onStatus("IN_REVIEW")} disabled={!activeReturnId || busy}>
              Mark in review
            </Button>
            <Button variant="outline" size="sm" onClick={() => onStatus("FINALIZED")} disabled={!activeReturnId || busy}>
              Finalize pack
            </Button>
            <Button variant="outline" size="sm" onClick={onExportCsv} disabled={!activeReturnId}>
              <Download className="mr-2 h-4 w-4" /> Export CSV
            </Button>
            <Button variant="outline" size="sm" onClick={() => window.print()} disabled={!report}>
              <Printer className="mr-2 h-4 w-4" /> Print / Save PDF
            </Button>
          </div>

          {!report ? (
            <Card className="border-slate-800 bg-slate-950/70 p-8 text-center text-slate-400">
              Generate a statutory report pack for the selected period to present schedules to advisers or FIRS.
            </Card>
          ) : (
            <div className="tax-print-root space-y-6 rounded-xl border border-slate-800 bg-white text-slate-900 shadow-xl print:border-0 print:shadow-none">
              <header className="border-b border-slate-200 bg-gradient-to-br from-slate-900 via-slate-900 to-emerald-950 px-8 py-10 text-white print:bg-slate-900">
                <p className="text-xs font-semibold uppercase tracking-[0.25em] text-emerald-300">
                  Whorl AI Statutory Reporting
                </p>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight">{report.cover.document_title}</h2>
                <p className="mt-2 text-slate-300">{report.cover.subtitle}</p>
                <div className="mt-6 grid gap-3 text-sm md:grid-cols-3">
                  <div>
                    <p className="text-slate-400">Taxpayer</p>
                    <p className="font-medium">{String(report.cover.generated_for.legal_name || "—")}</p>
                    <p className="text-slate-300">TIN: {String(report.cover.generated_for.tin || "—")}</p>
                    <p className="text-slate-300">RC: {String(report.cover.generated_for.rc_number || "—")}</p>
                  </div>
                  <div>
                    <p className="text-slate-400">Period</p>
                    <p className="font-medium">{report.cover.period_label}</p>
                    <p className="text-slate-300">
                      {report.cover.period_start} → {report.cover.period_end}
                    </p>
                    <p className="text-slate-300">Size band: {report.cover.company_size_band}</p>
                  </div>
                  <div>
                    <p className="text-slate-400">Framework</p>
                    <p className="font-medium">{report.cover.framework}</p>
                    <p className="text-slate-300">{report.cover.authority}</p>
                  </div>
                </div>
              </header>

              <section className="px-8">
                <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
                  Liability summary (₦)
                </h3>
                <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {[
                    ["VAT payable", liabilities?.vat_payable],
                    ["WHT remittable", liabilities?.wht_remittable],
                    ["CIT payable", liabilities?.cit_payable],
                    ["Development Levy", liabilities?.development_levy_payable],
                  ].map(([label, value]) => (
                    <div key={String(label)} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
                      <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">
                        {money(value)}
                      </p>
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-sm text-slate-600">
                  Estimated total due to FIRS:{" "}
                  <strong>{money(liabilities?.total_due_to_firs_estimate)}</strong>
                  {" · "}Filing due: <strong>{String(liabilities?.filing_due_date || "—")}</strong>
                </p>
              </section>

              {schedules
                .filter((s) => s.schedule_code !== "COVER")
                .map((sch) => (
                  <section key={sch.schedule_code} className="border-t border-slate-200 px-8 py-6">
                    <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                      <div>
                        <Badge className="mb-2 bg-emerald-700 text-white hover:bg-emerald-700">
                          {sch.schedule_code}
                        </Badge>
                        <h3 className="text-lg font-semibold text-slate-900">{sch.schedule_title}</h3>
                      </div>
                    </div>
                    {sch.notes && <p className="mb-3 text-sm text-slate-600">{sch.notes}</p>}
                    <div className="mb-4 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
                      {Object.entries(sch.totals_json || {})
                        .filter(([, v]) => typeof v !== "object")
                        .slice(0, 9)
                        .map(([k, v]) => (
                          <div key={k} className="rounded border border-slate-200 px-3 py-2">
                            <p className="text-xs uppercase text-slate-500">{k.replaceAll("_", " ")}</p>
                            <p className="font-medium text-slate-800">
                              {typeof v === "number" ? money(v) : String(v)}
                            </p>
                          </div>
                        ))}
                    </div>
                    <ScheduleLines lines={sch.lines_json} />
                  </section>
                ))}

              <section className="border-t border-slate-200 px-8 py-8">
                <h3 className="text-lg font-semibold text-slate-900">Attestation</h3>
                <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-700">
                  {report.cover.attestation.statement}
                </p>
                <div className="mt-8 grid gap-8 md:grid-cols-3">
                  {report.cover.attestation.sign_off_roles.map((role) => (
                    <div key={role} className="border-t border-slate-400 pt-3">
                      <p className="text-sm font-medium text-slate-800">{role}</p>
                      <p className="mt-8 text-xs text-slate-500">Signature / date</p>
                    </div>
                  ))}
                </div>
                <div className="mt-8">
                  <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Methodology</h4>
                  <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-slate-700">
                    {report.cover.methodology.map((m) => (
                      <li key={m}>{m}</li>
                    ))}
                  </ol>
                </div>
              </section>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
