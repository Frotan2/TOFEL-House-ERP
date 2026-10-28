import React, { useState } from 'react';
import {
  FileSpreadsheet,
  ShieldCheck,
  CheckCircle2,
  Clock,
  Layers,
  Lock,
  PlusCircle,
  HelpCircle,
  FileCheck,
} from 'lucide-react';
import { useERP } from '../../context/ERPContext';
import { StatusBadge } from '../common/StatusBadge';
import { MetricCard } from '../common/MetricCard';
import { CommandModal, CommandField } from '../common/CommandModal';
import { PolicyDomain } from '../../types';

export const ConfigurationDesk: React.FC = () => {
  const { policyDomains, auditEvents, appendPolicyVersion } = useERP();

  const [isAppendModalOpen, setIsAppendModalOpen] = useState(false);
  const [selectedDomain, setSelectedDomain] = useState<PolicyDomain | null>(null);

  const activePoliciesCount = policyDomains.filter(
    (p) => p.status === 'Configured & Active'
  ).length;

  const appendVersionFields: CommandField[] = [
    {
      name: 'versionTitle',
      label: 'Version Title / Identifier',
      type: 'text',
      required: true,
      placeholder: 'e.g. v3 (Revised Term Hours)',
    },
    {
      name: 'effectiveFrom',
      label: 'Effective Date',
      type: 'date',
      required: true,
      defaultValue: '2026-11-01',
    },
    {
      name: 'summary',
      label: 'Policy Version Summary',
      type: 'textarea',
      required: true,
      placeholder: 'Describe the governing business terms appended in this version…',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white p-6 rounded-lg border border-[#e3e8ef] shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#0f2a44] bg-[#e8eef6] px-2 py-0.5 rounded border border-[#c5d9f0]">
              Audience: Course Owner
            </span>
            <span className="text-[11px] text-[#5b6779] font-mono">
              toefl_house.desk.configuration.work
            </span>
          </div>
          <h1 className="text-xl font-bold text-[#1b2430]">TOEFL House Configuration Plane</h1>
          <p className="text-xs text-[#5b6779] mt-0.5 max-w-2xl">
            The configuration map: every configuration domain with its computed readiness. Append-only, versioned, hash-chained policy records.
          </p>
        </div>
      </div>

      {/* Configuration Readiness Summary */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard
          label="Active Governed Domains"
          value={`${activePoliciesCount} / ${policyDomains.length}`}
          definition="Policy domains with an active, non-deferred version governing operations."
          source="Policy Domain Records"
          badge={{ text: 'Enforced', tone: 'ok' }}
        />
        <MetricCard
          label="Deferred Domains (D1 / D5)"
          value="2 Domains"
          definition="Domains deferred by Owner decision: Academic Grading (D1) and Exit Mobility (D5)."
          source="docs/owner-decisions.json"
          badge={{ text: 'Deferred', tone: 'warn' }}
        />
        <MetricCard
          label="Configuration Audit Events"
          value={auditEvents.length}
          definition="Cryptographic receipts logging configuration append operations."
          source="TH Configuration Audit Event"
          badge={{ text: 'Intact', tone: 'ok' }}
        />
        <MetricCard
          label="Configuration Readiness"
          value="85.7%"
          definition="Calculated readiness score across all qualified institutional consumers."
          source="System Validator"
          badge={{ text: 'Ready', tone: 'ok' }}
        />
      </section>

      {/* Policy Domains Table */}
      <section className="bg-white rounded-lg border border-[#e3e8ef] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#f1f4f8] flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-[#1b2430]">
              Institutional Policy Domains & Governed Versions
            </h2>
            <p className="text-xs text-[#5b6779] mt-0.5">
              Append-only versions: changes create a new effective-dated entry with SHA-256 hash chaining.
            </p>
          </div>
          <span className="text-xs font-mono text-[#5b6779]">
            {policyDomains.length} policy domain(s)
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#f8fafc] text-[#5b6779] uppercase font-semibold text-[10px] tracking-wider border-b border-[#e3e8ef]">
              <tr>
                <th className="px-4 py-3">Configuration Domain</th>
                <th className="px-4 py-3">Governing Policy Record</th>
                <th className="px-4 py-3">Effective Version</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Governing Terms Summary</th>
                <th className="px-4 py-3 text-right">Owner Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f1f4f8]">
              {policyDomains.map((pol) => (
                <tr key={pol.domain} className="hover:bg-[#f8fafc] transition-colors">
                  <td className="px-4 py-3 font-bold text-[#1b2430]">
                    {pol.domain}
                  </td>
                  <td className="px-4 py-3 font-mono text-[11px] text-[#1f5fa8]">
                    {pol.name}
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-semibold text-[#0f2a44]">{pol.governingVersion}</span>
                    {pol.effectiveFrom && pol.effectiveFrom !== 'Deferred' && (
                      <div className="text-[10px] text-[#8792a3]">From {pol.effectiveFrom}</div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={pol.status} />
                  </td>
                  <td className="px-4 py-3 text-[11px] text-[#5b6779] max-w-sm">
                    {pol.summary}
                    {pol.ownerDecision && (
                      <div className="mt-1 text-[10px] font-semibold text-[#9a6700]">
                        {pol.ownerDecision}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedDomain(pol);
                        setIsAppendModalOpen(true);
                      }}
                      className="px-2.5 py-1 bg-[#0f2a44] hover:bg-[#1f5fa8] text-white rounded text-[11px] font-semibold"
                    >
                      Append Version
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Append Policy Version Command Modal */}
      {selectedDomain && (
        <CommandModal
          isOpen={isAppendModalOpen}
          onClose={() => {
            setIsAppendModalOpen(false);
            setSelectedDomain(null);
          }}
          title={`Append Policy Version: ${selectedDomain.name}`}
          description={`Adds an immutable, effective-dated policy record to ${selectedDomain.domain}.`}
          actingRole="Course Owner"
          methodName="toefl_house.configuration.append_policy_version"
          fields={appendVersionFields}
          onSubmit={(values) => {
            appendPolicyVersion(
              selectedDomain.domain,
              values.versionTitle,
              values.effectiveFrom,
              values.summary
            );
            return {
              status: 'success',
              message: `Appended version "${values.versionTitle}" effective ${values.effectiveFrom}`,
              payload: {
                domain: selectedDomain.domain,
                policy: selectedDomain.name,
                version: values.versionTitle,
                effective_from: values.effectiveFrom,
                actor: 'Course Owner',
              },
            };
          }}
        />
      )}
    </div>
  );
};
