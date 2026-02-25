import { useCallback, useEffect, useState } from 'react';
import {
  Key,
  Shield,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
  Eye,
  EyeOff,
  Trash2,
  Settings,
  Cpu,
} from 'lucide-react';
import {
  fetchSettings,
  setLLMKey,
  deleteLLMKey,
  testLLMKey,
  listApiKeys,
  createApiKey,
  revokeApiKey,
} from '../api/client';
import type { TenantSettings, ApiKeyInfo, ApiKeyCreated } from '../api/client';

/* ------------------------------------------------------------------ */
/* LLM API Key Card                                                    */
/* ------------------------------------------------------------------ */

function LLMKeyCard({
  settings,
  onUpdated,
}: {
  settings: TenantSettings;
  onUpdated: () => void;
}) {
  const [keyInput, setKeyInput] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [testResult, setTestResult] = useState<{
    valid: boolean;
    model: string | null;
    error: string | null;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const clearMessages = () => {
    setError(null);
    setSuccess(null);
    setTestResult(null);
  };

  const handleSave = async () => {
    if (!keyInput.trim()) return;
    clearMessages();
    setSaving(true);
    try {
      const result = await setLLMKey(keyInput.trim());
      setSuccess(`API key saved (${result.key_prefix}...)`);
      setKeyInput('');
      onUpdated();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save key');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    clearMessages();
    setTesting(true);
    try {
      const result = await testLLMKey();
      setTestResult(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to test key');
    } finally {
      setTesting(false);
    }
  };

  const handleDelete = async () => {
    clearMessages();
    setDeleting(true);
    try {
      await deleteLLMKey();
      setSuccess('API key removed');
      onUpdated();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to remove key');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-50">
          <Cpu className="h-5 w-5 text-purple-600" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-gray-900">LLM API Key</h2>
          <p className="text-sm text-gray-500">
            Provide your own Anthropic API key for AI-powered features
          </p>
        </div>
      </div>

      {/* Current status */}
      <div className="mb-4 rounded-md border border-gray-100 bg-gray-50 px-4 py-3">
        <div className="flex items-center gap-2">
          {settings.llm_key.has_key ? (
            <>
              <CheckCircle className="h-4 w-4 text-green-500" />
              <span className="text-sm font-medium text-green-700">Key configured</span>
              <span className="text-sm text-gray-500">
                ({settings.llm_key.key_prefix}...)
              </span>
              {settings.llm_key.stored_at && (
                <span className="ml-auto text-xs text-gray-400">
                  Added {new Date(settings.llm_key.stored_at).toLocaleDateString()}
                </span>
              )}
            </>
          ) : (
            <>
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              <span className="text-sm font-medium text-amber-700">No key configured</span>
              <span className="text-sm text-gray-500">
                AI features will be disabled until a key is provided
              </span>
            </>
          )}
        </div>
      </div>

      {/* Input */}
      <div className="mb-4">
        <label htmlFor="llm-key" className="mb-1 block text-sm font-medium text-gray-700">
          {settings.llm_key.has_key ? 'Replace API Key' : 'API Key'}
        </label>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              id="llm-key"
              type={showKey ? 'text' : 'password'}
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              placeholder="sk-ant-..."
              className="w-full rounded-md border border-gray-300 px-3 py-2 pr-10 text-sm shadow-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
            />
            <button
              type="button"
              onClick={() => setShowKey(!showKey)}
              aria-label={showKey ? 'Hide API key' : 'Show API key'}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              {showKey ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
            </button>
          </div>
          <button
            onClick={handleSave}
            disabled={saving || !keyInput.trim()}
            className="inline-flex items-center gap-1.5 rounded-md bg-ironlayer-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-ironlayer-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Key className="h-4 w-4" />}
            Save
          </button>
        </div>
        <p className="mt-1 text-xs text-gray-500">
          Your key is encrypted at rest and never logged. Get a key from{' '}
          <a
            href="https://console.anthropic.com/settings/keys"
            target="_blank"
            rel="noopener noreferrer"
            className="text-ironlayer-600 underline hover:text-ironlayer-700"
          >
            console.anthropic.com
          </a>
        </p>
      </div>

      {/* Actions */}
      {settings.llm_key.has_key && (
        <div className="flex items-center gap-2">
          <button
            onClick={handleTest}
            disabled={testing}
            className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50"
          >
            {testing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Shield className="h-4 w-4" />
            )}
            Test Key
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-white px-3 py-1.5 text-sm font-medium text-red-600 shadow-sm hover:bg-red-50 disabled:opacity-50"
          >
            {deleting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
            Remove Key
          </button>
        </div>
      )}

      {/* Feedback messages */}
      {error && (
        <div className="mt-3 rounded-md bg-red-50 px-3 py-2">
          <div className="flex items-center gap-2 text-sm text-red-700">
            <XCircle className="h-4 w-4 flex-shrink-0" />
            {error}
          </div>
        </div>
      )}
      {success && (
        <div className="mt-3 rounded-md bg-green-50 px-3 py-2">
          <div className="flex items-center gap-2 text-sm text-green-700">
            <CheckCircle className="h-4 w-4 flex-shrink-0" />
            {success}
          </div>
        </div>
      )}
      {testResult && (
        <div
          className={`mt-3 rounded-md px-3 py-2 ${
            testResult.valid ? 'bg-green-50' : 'bg-red-50'
          }`}
        >
          <div
            className={`flex items-center gap-2 text-sm ${
              testResult.valid ? 'text-green-700' : 'text-red-700'
            }`}
          >
            {testResult.valid ? (
              <>
                <CheckCircle className="h-4 w-4 flex-shrink-0" />
                Key is valid &mdash; connected to {testResult.model}
              </>
            ) : (
              <>
                <XCircle className="h-4 w-4 flex-shrink-0" />
                {testResult.error ?? 'Key validation failed'}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Platform API Keys Card                                              */
/* ------------------------------------------------------------------ */

function PlatformApiKeysCard() {
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [newKeyName, setNewKeyName] = useState('');
  const [creating, setCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<ApiKeyCreated | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadKeys = useCallback(async () => {
    try {
      const data = await listApiKeys();
      setKeys(data);
    } catch {
      /* silent */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadKeys();
  }, [loadKeys]);

  const handleCreate = async () => {
    if (!newKeyName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const created = await createApiKey(newKeyName.trim());
      setCreatedKey(created);
      setNewKeyName('');
      await loadKeys();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create key');
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (keyId: string) => {
    try {
      await revokeApiKey(keyId);
      await loadKeys();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to revoke key');
    }
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-ironlayer-50">
          <Key className="h-5 w-5 text-ironlayer-600" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-gray-900">API Keys</h2>
          <p className="text-sm text-gray-500">
            Manage API keys for CLI and programmatic access
          </p>
        </div>
      </div>

      {/* Create new key */}
      <div className="mb-4 flex gap-2">
        <input
          type="text"
          value={newKeyName}
          onChange={(e) => setNewKeyName(e.target.value)}
          placeholder="Key name (e.g. CI/CD, Local Dev)"
          aria-label="New API key name"
          className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
        />
        <button
          onClick={handleCreate}
          disabled={creating || !newKeyName.trim()}
          className="inline-flex items-center gap-1.5 rounded-md bg-ironlayer-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-ironlayer-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {creating && <Loader2 className="h-4 w-4 animate-spin" />}
          Create Key
        </button>
      </div>

      {/* Newly created key warning */}
      {createdKey && (
        <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 p-3">
          <div className="mb-1 flex items-center gap-2 text-sm font-medium text-amber-800">
            <AlertTriangle className="h-4 w-4" />
            Copy your API key now &mdash; it won&apos;t be shown again
          </div>
          <code className="block rounded bg-amber-100 px-2 py-1 text-xs font-mono text-amber-900 select-all">
            {createdKey.plaintext_key}
          </code>
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Key list */}
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-gray-400" role="status" aria-label="Loading API keys" />
        </div>
      ) : keys.length === 0 ? (
        <div className="rounded-md border border-dashed border-gray-300 py-8 text-center">
          <Key className="mx-auto h-8 w-8 text-gray-300" />
          <p className="mt-2 text-sm text-gray-500">No API keys yet</p>
          <p className="text-xs text-gray-400">
            Create a key to use with the CLI or CI/CD pipelines
          </p>
        </div>
      ) : (
        <div className="divide-y divide-gray-100">
          {keys.map((key) => (
            <div key={key.id} className="flex items-center justify-between py-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-900">{key.name}</span>
                  <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
                    {key.key_prefix}...
                  </code>
                </div>
                <div className="mt-0.5 text-xs text-gray-400">
                  Created{' '}
                  {key.created_at
                    ? new Date(key.created_at).toLocaleDateString()
                    : 'unknown'}
                  {key.expires_at && (
                    <> &middot; Expires {new Date(key.expires_at).toLocaleDateString()}</>
                  )}
                </div>
              </div>
              <button
                onClick={() => handleRevoke(key.id)}
                aria-label={`Revoke API key ${key.name}`}
                className="rounded-md border border-red-200 px-2.5 py-1 text-xs font-medium text-red-600 hover:bg-red-50"
              >
                Revoke
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Settings Page                                                       */
/* ------------------------------------------------------------------ */

export default function SettingsPage() {
  const [settings, setSettings] = useState<TenantSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    try {
      const data = await fetchSettings();
      setSettings(data);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load settings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-ironlayer-500" role="status" aria-label="Loading settings" />
      </div>
    );
  }

  if (error || !settings) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8">
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center">
          <XCircle className="mx-auto h-8 w-8 text-red-400" />
          <p className="mt-2 text-sm text-red-700">{error ?? 'Failed to load settings'}</p>
          <button
            onClick={loadSettings}
            className="mt-3 text-sm font-medium text-red-600 underline hover:text-red-700"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      {/* Header */}
      <div className="mb-8 flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-ironlayer-50">
          <Settings className="h-6 w-6 text-ironlayer-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
          <p className="text-sm text-gray-500">
            Manage your workspace configuration and API keys
          </p>
        </div>
      </div>

      <div className="space-y-6">
        <LLMKeyCard settings={settings} onUpdated={loadSettings} />
        <PlatformApiKeysCard />
      </div>
    </div>
  );
}
