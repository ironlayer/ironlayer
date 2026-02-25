import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { createCheckoutSession, createEnvironment, fetchBillingPlans, setLLMKey, testLLMKey } from '../api/client';
import type { BillingPlanTier } from '../api/types';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

type Step = 'databricks' | 'plan' | 'llm-key' | 'environment';

interface DatabricksConfig {
  workspaceUrl: string;
  token: string;
}

interface EnvironmentConfig {
  name: string;
  catalog: string;
  schemaPrefix: string;
}

/* ------------------------------------------------------------------ */
/* Sub-components                                                      */
/* ------------------------------------------------------------------ */

function StepIndicator({ current }: { current: Step }) {
  const steps: { key: Step; label: string }[] = [
    { key: 'databricks', label: 'Connect Databricks' },
    { key: 'plan', label: 'Choose Plan' },
    { key: 'llm-key', label: 'AI Setup' },
    { key: 'environment', label: 'Create Environment' },
  ];

  return (
    <div className="mb-8 flex items-center justify-center gap-2">
      {steps.map((step, i) => {
        const isActive = step.key === current;
        const isPast =
          steps.findIndex((s) => s.key === current) > i;
        return (
          <div key={step.key} className="flex items-center gap-2">
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold ${
                isActive
                  ? 'bg-ironlayer-600 text-white'
                  : isPast
                    ? 'bg-green-500 text-white'
                    : 'bg-gray-200 text-gray-500'
              }`}
            >
              {isPast ? '✓' : i + 1}
            </div>
            <span
              className={`text-sm ${
                isActive ? 'font-semibold text-gray-900' : 'text-gray-500'
              }`}
            >
              {step.label}
            </span>
            {i < steps.length - 1 && (
              <div className="mx-2 h-px w-12 bg-gray-300" />
            )}
          </div>
        );
      })}
    </div>
  );
}

function DatabricksStep({
  config,
  onChange,
  onNext,
}: {
  config: DatabricksConfig;
  onChange: (c: DatabricksConfig) => void;
  onNext: () => void;
}) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<'success' | 'error' | null>(null);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      // Validate the workspace URL is reachable by calling the API info endpoint.
      const url = config.workspaceUrl.replace(/\/$/, '');
      const resp = await fetch(`${url}/api/2.0/clusters/list`, {
        method: 'GET',
        headers: { Authorization: `Bearer ${config.token}` },
      });
      setTestResult(resp.ok ? 'success' : 'error');
    } catch {
      setTestResult('error');
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">Connect Databricks</h2>
        <p className="mt-1 text-sm text-gray-500">
          Provide your Databricks workspace URL and a personal access token so IronLayer
          can manage your transformation models.
        </p>
      </div>

      <div>
        <label htmlFor="workspace-url" className="block text-sm font-medium text-gray-700">
          Workspace URL
        </label>
        <input
          id="workspace-url"
          type="url"
          placeholder="https://dbc-abc123.cloud.databricks.com"
          value={config.workspaceUrl}
          onChange={(e) => onChange({ ...config, workspaceUrl: e.target.value })}
          className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
        />
      </div>

      <div>
        <label htmlFor="pat" className="block text-sm font-medium text-gray-700">
          Personal Access Token
        </label>
        <input
          id="pat"
          type="password"
          placeholder="dapi..."
          value={config.token}
          onChange={(e) => onChange({ ...config, token: e.target.value })}
          className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
        />
        <p className="mt-1 text-xs text-gray-400">
          Your token is encrypted at rest and never logged.
        </p>
      </div>

      {testResult === 'success' && (
        <div className="rounded-md bg-green-50 px-4 py-3 text-sm text-green-800">
          Connection successful — we can reach your workspace.
        </div>
      )}
      {testResult === 'error' && (
        <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-800">
          Could not connect. Check the URL and token, then try again.
        </div>
      )}

      <div className="flex gap-3">
        <button
          type="button"
          onClick={handleTest}
          disabled={!config.workspaceUrl || !config.token || testing}
          className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          {testing ? 'Testing…' : 'Test Connection'}
        </button>
        <button
          type="button"
          onClick={onNext}
          disabled={!config.workspaceUrl || !config.token}
          className="rounded-md bg-ironlayer-600 px-4 py-2 text-sm font-medium text-white hover:bg-ironlayer-700 disabled:opacity-50"
        >
          Continue
        </button>
      </div>
    </div>
  );
}

function PlanStep({ onNext, onSkip }: { onNext: (priceId: string) => void; onSkip: () => void }) {
  const [tiers, setTiers] = useState<BillingPlanTier[]>([]);
  const [plansLoading, setPlansLoading] = useState(true);
  const controllerRef = useRef<AbortController | null>(null);

  const loadPlans = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setPlansLoading(true);
    try {
      const resp = await fetchBillingPlans(controller.signal);
      if (!controller.signal.aborted) {
        setTiers(resp.plans);
      }
    } catch {
      // On error, fall through to empty state -- the user can retry.
    } finally {
      if (!controller.signal.aborted) {
        setPlansLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadPlans();
    return () => { controllerRef.current?.abort(); };
  }, [loadPlans]);

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="text-center">
        <h2 className="text-xl font-semibold text-gray-900">Choose Your Plan</h2>
        <p className="mt-1 text-sm text-gray-500">
          Start free and upgrade when you&apos;re ready. You can change plans anytime.
        </p>
      </div>

      {plansLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-ironlayer-600 border-t-transparent" />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          {tiers.map((tier) => (
            <div
              key={tier.tier}
              className="rounded-lg border border-gray-200 p-5 shadow-sm transition hover:border-ironlayer-400 hover:shadow-md"
            >
              <h3 className="text-lg font-semibold text-gray-900">{tier.label}</h3>
              <p className="mt-1 text-2xl font-bold text-ironlayer-600">{tier.price_label}</p>
              <ul className="mt-4 space-y-2 text-sm text-gray-600">
                {tier.features.map((f) => (
                  <li key={f} className="flex items-start gap-2">
                    <span className="text-green-500">✓</span>
                    {f}
                  </li>
                ))}
              </ul>
              <button
                type="button"
                onClick={() => {
                  if (tier.price_id) {
                    onNext(tier.price_id);
                  } else {
                    onSkip();
                  }
                }}
                className={`mt-5 w-full rounded-md px-4 py-2 text-sm font-medium ${
                  tier.price_id
                    ? 'bg-ironlayer-600 text-white hover:bg-ironlayer-700'
                    : 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                }`}
              >
                {tier.price_id ? 'Subscribe' : 'Get Started Free'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function EnvironmentStep({
  config,
  onChange,
  onFinish,
  loading,
}: {
  config: EnvironmentConfig;
  onChange: (c: EnvironmentConfig) => void;
  onFinish: () => void;
  loading: boolean;
}) {
  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">Create Your First Environment</h2>
        <p className="mt-1 text-sm text-gray-500">
          Environments map to Databricks catalogs. Start with a development environment.
        </p>
      </div>

      <div>
        <label htmlFor="env-name" className="block text-sm font-medium text-gray-700">
          Environment Name
        </label>
        <input
          id="env-name"
          type="text"
          placeholder="dev"
          value={config.name}
          onChange={(e) => onChange({ ...config, name: e.target.value })}
          className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
        />
      </div>

      <div>
        <label htmlFor="env-catalog" className="block text-sm font-medium text-gray-700">
          Databricks Catalog
        </label>
        <input
          id="env-catalog"
          type="text"
          placeholder="analytics"
          value={config.catalog}
          onChange={(e) => onChange({ ...config, catalog: e.target.value })}
          className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
        />
      </div>

      <div>
        <label htmlFor="env-schema" className="block text-sm font-medium text-gray-700">
          Schema Prefix
        </label>
        <input
          id="env-schema"
          type="text"
          placeholder="ironlayer_dev"
          value={config.schemaPrefix}
          onChange={(e) => onChange({ ...config, schemaPrefix: e.target.value })}
          className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
        />
      </div>

      <button
        type="button"
        onClick={onFinish}
        disabled={!config.name || !config.catalog || !config.schemaPrefix || loading}
        className="w-full rounded-md bg-ironlayer-600 px-4 py-2 text-sm font-medium text-white hover:bg-ironlayer-700 disabled:opacity-50"
      >
        {loading ? 'Creating…' : 'Create Environment & Go to Dashboard'}
      </button>
    </div>
  );
}

function LLMKeyStep({ onNext, onSkip }: { onNext: () => void; onSkip: () => void }) {
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [status, setStatus] = useState<'idle' | 'saved' | 'valid' | 'invalid'>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSaveAndTest = async () => {
    if (!apiKey.trim()) return;
    setSaving(true);
    setErrorMsg(null);
    try {
      await setLLMKey(apiKey.trim());
      setStatus('saved');

      // Immediately test the key.
      setTesting(true);
      const result = await testLLMKey();
      if (result.valid) {
        setStatus('valid');
      } else {
        setStatus('invalid');
        setErrorMsg(result.error ?? 'Key validation failed');
      }
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to save key');
    } finally {
      setSaving(false);
      setTesting(false);
    }
  };

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">AI-Powered Features</h2>
        <p className="mt-1 text-sm text-gray-500">
          IronLayer uses AI for semantic classification, cost prediction, and SQL optimization.
          Provide your Anthropic API key to enable these features, or skip this step and add
          one later in Settings.
        </p>
      </div>

      <div>
        <label htmlFor="llm-key" className="block text-sm font-medium text-gray-700">
          Anthropic API Key
        </label>
        <input
          id="llm-key"
          type="password"
          placeholder="sk-ant-..."
          value={apiKey}
          onChange={(e) => {
            setApiKey(e.target.value);
            setStatus('idle');
            setErrorMsg(null);
          }}
          className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
        />
        <p className="mt-1 text-xs text-gray-400">
          Your key is encrypted at rest and never logged. Get one from{' '}
          <a
            href="https://console.anthropic.com/settings/keys"
            target="_blank"
            rel="noopener noreferrer"
            className="text-ironlayer-600 underline"
          >
            console.anthropic.com
          </a>
        </p>
      </div>

      {status === 'valid' && (
        <div className="rounded-md bg-green-50 px-4 py-3 text-sm text-green-800">
          Key is valid and working. AI features are now enabled.
        </div>
      )}
      {status === 'invalid' && (
        <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-800">
          {errorMsg ?? 'Key validation failed. Check your key and try again.'}
        </div>
      )}
      {errorMsg && status === 'idle' && (
        <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-800">{errorMsg}</div>
      )}

      <div className="flex gap-3">
        <button
          type="button"
          onClick={handleSaveAndTest}
          disabled={!apiKey.trim() || saving || testing}
          className="rounded-md bg-ironlayer-600 px-4 py-2 text-sm font-medium text-white hover:bg-ironlayer-700 disabled:opacity-50"
        >
          {saving ? 'Saving…' : testing ? 'Testing…' : 'Save & Test Key'}
        </button>
        {status === 'valid' && (
          <button
            type="button"
            onClick={onNext}
            className="rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
          >
            Continue
          </button>
        )}
        <button
          type="button"
          onClick={onSkip}
          className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Skip for now
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Main page                                                           */
/* ------------------------------------------------------------------ */

export default function OnboardingPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [step, setStep] = useState<Step>('databricks');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [databricks, setDatabricks] = useState<DatabricksConfig>({
    workspaceUrl: '',
    token: '',
  });

  const [environment, setEnvironment] = useState<EnvironmentConfig>({
    name: 'dev',
    catalog: '',
    schemaPrefix: '',
  });

  const handlePlanSelect = async (priceId: string) => {
    setError(null);
    try {
      const { checkout_url } = await createCheckoutSession(
        priceId,
        `${window.location.origin}/onboarding?step=llm-key`,
        `${window.location.origin}/onboarding?step=plan`,
      );
      window.location.href = checkout_url;
    } catch (err: any) {
      setError(err.message || 'Failed to create checkout session');
    }
  };

  const handleFinish = async () => {
    setError(null);
    setLoading(true);
    try {
      await createEnvironment({
        name: environment.name,
        catalog: environment.catalog,
        schema_prefix: environment.schemaPrefix,
        created_by: user?.email || 'system',
      });
      navigate('/');
    } catch (err: any) {
      setError(err.message || 'Failed to create environment');
    } finally {
      setLoading(false);
    }
  };

  // Restore step from URL params (e.g., after Stripe redirect).
  useState(() => {
    const params = new URLSearchParams(window.location.search);
    const urlStep = params.get('step');
    if (urlStep === 'environment' || urlStep === 'plan' || urlStep === 'llm-key') {
      setStep(urlStep);
    }
  });

  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      <header className="border-b bg-white px-6 py-4">
        <h1 className="text-lg font-bold text-ironlayer-600">IronLayer Setup</h1>
      </header>

      <main className="flex-1 px-6 py-10">
        <StepIndicator current={step} />

        {error && (
          <div className="mx-auto mb-6 max-w-lg rounded-md bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        )}

        {step === 'databricks' && (
          <DatabricksStep
            config={databricks}
            onChange={setDatabricks}
            onNext={() => setStep('plan')}
          />
        )}

        {step === 'plan' && (
          <PlanStep
            onNext={handlePlanSelect}
            onSkip={() => setStep('llm-key')}
          />
        )}

        {step === 'llm-key' && (
          <LLMKeyStep
            onNext={() => setStep('environment')}
            onSkip={() => setStep('environment')}
          />
        )}

        {step === 'environment' && (
          <EnvironmentStep
            config={environment}
            onChange={setEnvironment}
            onFinish={handleFinish}
            loading={loading}
          />
        )}
      </main>
    </div>
  );
}
