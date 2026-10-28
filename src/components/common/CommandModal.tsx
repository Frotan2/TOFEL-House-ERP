import React, { useState } from 'react';
import { X, CheckCircle, AlertTriangle, ShieldCheck, RefreshCw } from 'lucide-react';
import { StatusBadge } from './StatusBadge';

export interface CommandField {
  name: string;
  label: string;
  type: 'text' | 'number' | 'select' | 'textarea' | 'date';
  options?: string[];
  required?: boolean;
  defaultValue?: string | number;
  placeholder?: string;
  readOnly?: boolean;
  description?: string;
}

interface CommandModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  description: string;
  actingRole: string;
  methodName: string;
  fields: CommandField[];
  onSubmit: (values: Record<string, any>) => { status: 'success' | 'warning' | 'error'; message: string; payload?: Record<string, any> };
}

export const CommandModal: React.FC<CommandModalProps> = ({
  isOpen,
  onClose,
  title,
  description,
  actingRole,
  methodName,
  fields,
  onSubmit,
}) => {
  const generateKey = () => {
    const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    let res = '';
    for (let i = 0; i < 20; i++) res += chars.charAt(Math.floor(Math.random() * chars.length));
    return res;
  };

  const [requestKey, setRequestKey] = useState(generateKey());
  const [formData, setFormData] = useState<Record<string, any>>(() => {
    const initial: Record<string, any> = {};
    fields.forEach((f) => {
      initial[f.name] = f.defaultValue !== undefined ? f.defaultValue : '';
    });
    return initial;
  });

  const [result, setResult] = useState<{
    status: 'success' | 'warning' | 'error';
    message: string;
    payload?: Record<string, any>;
  } | null>(null);

  if (!isOpen) return null;

  const handleChange = (name: string, value: any) => {
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const res = onSubmit({ ...formData, request_key: requestKey });
    setResult(res);
  };

  const handleReset = () => {
    setResult(null);
    setRequestKey(generateKey());
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
      <div className="bg-white rounded-lg shadow-xl border border-[#cdd5e0] w-full max-w-xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="bg-[#f6f8fa] border-b border-[#e3e8ef] px-6 py-4 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[11px] font-bold uppercase tracking-wider text-[#1f5fa8] bg-[#eaf1fa] px-2 py-0.5 rounded border border-[#c5d9f0]">
                {actingRole}
              </span>
              <span className="text-[11px] font-mono text-[#8792a3]">{methodName}</span>
            </div>
            <h2 className="text-lg font-bold text-[#1b2430]">{title}</h2>
            <p className="text-xs text-[#5b6779] mt-0.5">{description}</p>
          </div>
          <button
            onClick={handleReset}
            className="text-[#8792a3] hover:text-[#1b2430] p-1 rounded-md transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-4 text-sm flex-1">
          {result ? (
            /* Result Projection View */
            <div className="space-y-4">
              <div
                className={`p-4 rounded-md border flex items-start gap-3 ${
                  result.status === 'success'
                    ? 'bg-[#e7f4ec] border-[#a8d5ba] text-[#1a7f4b]'
                    : result.status === 'warning'
                    ? 'bg-[#fdf3dc] border-[#f5d98a] text-[#9a6700]'
                    : 'bg-[#fdecea] border-[#f5b5b0] text-[#b42318]'
                }`}
              >
                {result.status === 'success' ? (
                  <CheckCircle className="w-5 h-5 shrink-0 mt-0.5" />
                ) : (
                  <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
                )}
                <div>
                  <h3 className="font-bold text-sm">
                    {result.status === 'success'
                      ? `${title} succeeded.`
                      : result.status === 'warning'
                      ? `${title} needs attention.`
                      : `${title} refused.`}
                  </h3>
                  <p className="text-xs mt-1 text-[#1b2430]">{result.message}</p>
                </div>
              </div>

              {result.payload && (
                <div className="border border-[#e3e8ef] rounded-md p-4 bg-[#f8fafc]">
                  <h4 className="text-xs font-bold uppercase text-[#5b6779] tracking-wider mb-2">
                    Action Facts & Receipt
                  </h4>
                  <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                    {Object.entries(result.payload).map(([k, v]) => (
                      <div key={k} className="flex flex-col">
                        <dt className="text-[#8792a3] uppercase font-mono text-[10px]">
                          {k.replace(/_/g, ' ')}
                        </dt>
                        <dd className="font-semibold text-[#1b2430]">
                          {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                        </dd>
                      </div>
                    ))}
                    <div className="flex flex-col col-span-2 pt-2 border-t border-[#e3e8ef]">
                      <dt className="text-[#8792a3] uppercase font-mono text-[10px]">
                        Idempotency Key
                      </dt>
                      <dd className="font-mono text-[11px] text-[#5b6779]">{requestKey}</dd>
                    </div>
                  </dl>
                </div>
              )}

              <div className="flex justify-end pt-2">
                <button
                  type="button"
                  onClick={handleReset}
                  className="px-4 py-2 bg-[#1f5fa8] hover:bg-[#164a85] text-white rounded text-xs font-semibold"
                >
                  Close & Return to Desk
                </button>
              </div>
            </div>
          ) : (
            /* Input Form */
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Request Key Info */}
              <div className="bg-[#f8fafc] border border-[#e3e8ef] p-3 rounded text-xs flex items-center justify-between">
                <div>
                  <span className="font-mono text-[#5b6779] font-semibold">Idempotency Request Key</span>
                  <p className="text-[11px] text-[#8792a3] font-mono">{requestKey}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setRequestKey(generateKey())}
                  title="Generate fresh request key"
                  className="p-1 text-[#8792a3] hover:text-[#1f5fa8] transition-colors"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Dynamic Fields */}
              {fields.map((field) => (
                <div key={field.name} className="flex flex-col gap-1">
                  <label className="text-xs font-semibold text-[#1b2430]">
                    {field.label} {field.required && <span className="text-[#b42318]">*</span>}
                  </label>

                  {field.type === 'select' ? (
                    <select
                      value={formData[field.name]}
                      onChange={(e) => handleChange(field.name, e.target.value)}
                      required={field.required}
                      disabled={field.readOnly}
                      className="border border-[#cdd5e0] rounded px-3 py-1.5 text-xs focus:outline-none focus:border-[#1f5fa8] bg-white"
                    >
                      <option value="">-- Select {field.label} --</option>
                      {field.options?.map((opt) => (
                        <option key={opt} value={opt}>
                          {opt}
                        </option>
                      ))}
                    </select>
                  ) : field.type === 'textarea' ? (
                    <textarea
                      value={formData[field.name]}
                      onChange={(e) => handleChange(field.name, e.target.value)}
                      required={field.required}
                      placeholder={field.placeholder}
                      disabled={field.readOnly}
                      rows={3}
                      className="border border-[#cdd5e0] rounded px-3 py-1.5 text-xs focus:outline-none focus:border-[#1f5fa8]"
                    />
                  ) : (
                    <input
                      type={field.type}
                      value={formData[field.name]}
                      onChange={(e) => handleChange(field.name, e.target.value)}
                      required={field.required}
                      placeholder={field.placeholder}
                      readOnly={field.readOnly}
                      className={`border border-[#cdd5e0] rounded px-3 py-1.5 text-xs focus:outline-none focus:border-[#1f5fa8] ${
                        field.readOnly ? 'bg-[#f1f4f8] text-[#5b6779]' : 'bg-white'
                      }`}
                    />
                  )}

                  {field.description && (
                    <span className="text-[11px] text-[#8792a3]">{field.description}</span>
                  )}
                </div>
              ))}

              <div className="pt-4 border-t border-[#e3e8ef] flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-[11px] text-[#5b6779]">
                  <ShieldCheck className="w-3.5 h-3.5 text-[#1a7f4b]" />
                  <span>Guarded execution · Server checks authority & locks</span>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-3 py-1.5 border border-[#cdd5e0] hover:bg-[#f1f4f8] text-[#5b6779] rounded text-xs font-semibold"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-1.5 bg-[#1f5fa8] hover:bg-[#164a85] text-white rounded text-xs font-semibold shadow-xs"
                  >
                    Execute Command
                  </button>
                </div>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};
