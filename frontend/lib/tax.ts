import { apiFetch } from "@/lib/api";

export type TaxProfile = {
  id?: string;
  legal_name: string;
  trading_name?: string | null;
  tin?: string | null;
  rc_number?: string | null;
  tax_office?: string | null;
  business_address?: string | null;
  state_of_operation?: string | null;
  sector?: string | null;
  entity_type: "COMPANY" | "ENTERPRISE" | "PARTNERSHIP" | "INDIVIDUAL";
  accounting_year_end_month: number;
  currency: string;
  fixed_assets_ngn: number;
  vat_registered: boolean;
  vat_filing_frequency: "MONTHLY" | "QUARTERLY";
  default_wht_counterparty_type:
    | "CORPORATE_RESIDENT"
    | "CORPORATE_NON_RESIDENT"
    | "NON_CORPORATE_RESIDENT"
    | "NON_CORPORATE_NON_RESIDENT";
  contact_name?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  notes?: string | null;
};

export type TaxReturnSummary = {
  id: string;
  period_start: string;
  period_end: string;
  period_label: string;
  return_type: string;
  status: string;
  summary_json?: Record<string, unknown>;
  framework?: string;
  created_at?: string;
  finalized_at?: string | null;
};

export type TaxSchedule = {
  schedule_code: string;
  schedule_title: string;
  sort_order: number;
  totals_json: Record<string, unknown>;
  lines_json: unknown;
  notes?: string | null;
};

export type TaxReportPack = {
  cover: {
    document_title: string;
    subtitle: string;
    framework: string;
    authority: string;
    period_label: string;
    period_start: string;
    period_end: string;
    generated_for: Record<string, unknown>;
    company_size_band: string;
    currency: string;
    liabilities: Record<string, number | string>;
    attestation: { statement: string; sign_off_roles: string[] };
    methodology: string[];
    statutory_references: Record<string, unknown>;
  };
  schedules: TaxSchedule[];
  liabilities: Record<string, number | string>;
  summary: Record<string, unknown>;
};

export async function fetchTaxFramework() {
  return apiFetch<{
    references: Record<string, unknown>;
    default_period_start: string;
    default_period_end: string;
    suggested_workflows: string[];
  }>("/tax/framework");
}

export async function fetchTaxProfile() {
  return apiFetch<TaxProfile>("/tax/profile");
}

export async function saveTaxProfile(body: TaxProfile) {
  return apiFetch<TaxProfile>("/tax/profile", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function classifyTaxPeriod(body: {
  date_from: string;
  date_to: string;
  account_ids?: string[];
  persist?: boolean;
}) {
  return apiFetch<{ count: number; persisted: number; items: Array<Record<string, unknown>> }>(
    "/tax/classify",
    { method: "POST", body: JSON.stringify(body), timeoutMs: 120_000 }
  );
}

export async function generateTaxReturn(body: {
  period_start: string;
  period_end: string;
  account_ids?: string[];
  include_books_pnl?: boolean;
  persist_classifications?: boolean;
}) {
  return apiFetch<{
    return: TaxReturnSummary & { report_json?: TaxReportPack; id: string };
    report: TaxReportPack;
    classification_count: number;
  }>("/tax/returns/generate", {
    method: "POST",
    body: JSON.stringify(body),
    timeoutMs: 180_000,
  });
}

export async function listTaxReturns() {
  return apiFetch<{ items: TaxReturnSummary[] }>("/tax/returns");
}

export async function getTaxReturn(id: string) {
  return apiFetch<{
    return: TaxReturnSummary & { report_json?: TaxReportPack; status: string };
    schedules: TaxSchedule[];
    references: Record<string, unknown>;
  }>(`/tax/returns/${id}`);
}

export async function updateTaxReturnStatus(id: string, status: "DRAFT" | "IN_REVIEW" | "FINALIZED") {
  return apiFetch<TaxReturnSummary>(`/tax/returns/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export function taxExportCsvUrl(id: string) {
  const base = (process.env.NEXT_PUBLIC_FASTAPI_URL || "http://localhost:8000").replace(/\/$/, "");
  return `${base}/tax/returns/${id}/export.csv`;
}
