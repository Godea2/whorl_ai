-- Nigeria Tax & Statutory Reporting module (NTA 2025 framework)
-- Supports taxpayer profile, per-transaction tax classifications, and filed report packs.

CREATE TABLE IF NOT EXISTS public.tax_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  legal_name TEXT NOT NULL,
  trading_name TEXT,
  tin TEXT,
  rc_number TEXT,
  tax_office TEXT,
  business_address TEXT,
  state_of_operation TEXT,
  sector TEXT,
  entity_type TEXT NOT NULL DEFAULT 'COMPANY'
    CHECK (entity_type IN ('COMPANY', 'ENTERPRISE', 'PARTNERSHIP', 'INDIVIDUAL')),
  accounting_year_end_month INT NOT NULL DEFAULT 12
    CHECK (accounting_year_end_month BETWEEN 1 AND 12),
  currency TEXT NOT NULL DEFAULT 'NGN',
  fixed_assets_ngn NUMERIC DEFAULT 0,
  vat_registered BOOLEAN NOT NULL DEFAULT TRUE,
  vat_filing_frequency TEXT NOT NULL DEFAULT 'MONTHLY'
    CHECK (vat_filing_frequency IN ('MONTHLY', 'QUARTERLY')),
  default_wht_counterparty_type TEXT NOT NULL DEFAULT 'CORPORATE_RESIDENT'
    CHECK (default_wht_counterparty_type IN (
      'CORPORATE_RESIDENT', 'CORPORATE_NON_RESIDENT',
      'NON_CORPORATE_RESIDENT', 'NON_CORPORATE_NON_RESIDENT'
    )),
  contact_name TEXT,
  contact_email TEXT,
  contact_phone TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id)
);

CREATE TABLE IF NOT EXISTS public.tax_transaction_classifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  transaction_id UUID NOT NULL REFERENCES public.transactions(id) ON DELETE CASCADE,
  vat_treatment TEXT NOT NULL DEFAULT 'OUT_OF_SCOPE'
    CHECK (vat_treatment IN (
      'STANDARD_OUTPUT', 'STANDARD_INPUT', 'ZERO_RATED', 'EXEMPT',
      'OUT_OF_SCOPE', 'BANK_CHARGE_VAT', 'NON_DEDUCTIBLE_INPUT'
    )),
  vat_rate NUMERIC NOT NULL DEFAULT 0.075,
  vat_amount NUMERIC NOT NULL DEFAULT 0,
  net_amount NUMERIC NOT NULL DEFAULT 0,
  gross_amount NUMERIC NOT NULL DEFAULT 0,
  wht_category TEXT NOT NULL DEFAULT 'NONE',
  wht_rate NUMERIC NOT NULL DEFAULT 0,
  wht_amount NUMERIC NOT NULL DEFAULT 0,
  wht_role TEXT NOT NULL DEFAULT 'NONE'
    CHECK (wht_role IN ('NONE', 'AGENT_DEDUCTED', 'SUFFERED')),
  cit_treatment TEXT NOT NULL DEFAULT 'NEUTRAL'
    CHECK (cit_treatment IN (
      'TAXABLE_INCOME', 'DEDUCTIBLE_EXPENSE', 'NON_DEDUCTIBLE',
      'CAPITAL', 'TRANSFER', 'NEUTRAL'
    )),
  levy_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
  confidence NUMERIC NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'AUTO'
    CHECK (source IN ('AUTO', 'MANUAL', 'RULE', 'SYNTHETIC')),
  rationale TEXT,
  classified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, transaction_id)
);

CREATE INDEX IF NOT EXISTS idx_tax_classifications_user_txn
  ON public.tax_transaction_classifications (user_id, transaction_id);

CREATE TABLE IF NOT EXISTS public.tax_returns (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  profile_id UUID REFERENCES public.tax_profiles(id) ON DELETE SET NULL,
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  period_label TEXT NOT NULL,
  return_type TEXT NOT NULL DEFAULT 'COMBINED_STATUTORY'
    CHECK (return_type IN (
      'COMBINED_STATUTORY', 'VAT', 'WHT', 'CIT', 'DEVELOPMENT_LEVY', 'CUSTOM'
    )),
  status TEXT NOT NULL DEFAULT 'DRAFT'
    CHECK (status IN ('DRAFT', 'IN_REVIEW', 'FINALIZED', 'SUPERSEDED')),
  currency TEXT NOT NULL DEFAULT 'NGN',
  framework TEXT NOT NULL DEFAULT 'Nigeria Tax Act 2025',
  report_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  methodology_notes TEXT,
  prepared_by UUID REFERENCES public.users(id) ON DELETE SET NULL,
  reviewed_by UUID REFERENCES public.users(id) ON DELETE SET NULL,
  approved_by UUID REFERENCES public.users(id) ON DELETE SET NULL,
  prepared_at TIMESTAMPTZ,
  reviewed_at TIMESTAMPTZ,
  finalized_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tax_returns_user_period
  ON public.tax_returns (user_id, period_end DESC);

CREATE TABLE IF NOT EXISTS public.tax_return_schedules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  return_id UUID NOT NULL REFERENCES public.tax_returns(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  schedule_code TEXT NOT NULL,
  schedule_title TEXT NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  totals_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  lines_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tax_return_schedules_return
  ON public.tax_return_schedules (return_id, sort_order);

ALTER TABLE public.tax_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tax_transaction_classifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tax_returns ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tax_return_schedules ENABLE ROW LEVEL SECURITY;

CREATE POLICY tax_profiles_self ON public.tax_profiles
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY tax_classifications_self ON public.tax_transaction_classifications
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY tax_returns_self ON public.tax_returns
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY tax_return_schedules_self ON public.tax_return_schedules
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
