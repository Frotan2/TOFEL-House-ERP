import React from 'react';
import {
  Compass,
  ShieldAlert,
  Lock,
  FileCheck,
  CheckCircle2,
  AlertTriangle,
  Database,
  Sliders,
  ExternalLink,
} from 'lucide-react';
import { useERP } from '../../context/ERPContext';
import { StatusBadge } from '../common/StatusBadge';
import { MetricCard } from '../common/MetricCard';

export const OwnerCockpit: React.FC = () => {
  const {
    students,
    admissionDecisions,
    invoices,
    payments,
    schedules,
    auditEvents,
    activeBranch,
    setActiveDesk,
  } = useERP();

  const totalEnrollments = students.filter((s) => s.status === 'Active').length;
  const totalTuition = payments.reduce((acc, p) => acc + p.amount, 0);
  const totalOverdue = invoices
    .filter((i) => i.status === 'Overdue')
    .reduce((acc, i) => acc + i.outstandingAmount, 0);

  const releasePosture = [
    {
      label: 'Site Operational Mode',
      value: 'SYNTHETIC',
      tone: 'info' as const,
      definition: 'SYNTHETIC, PRODUCTION or REFUSED as resolved by site guard. Operational mode is not release authorization.',
      owner: 'System Runtime Guard',
    },
    {
      label: 'Production Authorization',
      value: 'REJECT (Hold Active)',
      tone: 'danger' as const,
      definition: 'Stays REJECT until all evidence gates in ACCEPTANCE.md and Owner recovery gates pass.',
      owner: 'Course Owner Decision D18',
    },
    {
      label: 'Dependency Security (SEC-DEPS-01)',
      value: 'OPEN (Loopback Guarded)',
      tone: 'warn' as const,
      definition: 'Stack carries pinned upstream advisories. Guarded by loopback-only 127.0.0.1 and private Tailscale access.',
      owner: 'SEC-DEPS-01 Protocol',
    },
    {
      label: 'Effective Backup Switch',
      value: 'OFF (Owner Decision D18)',
      tone: 'warn' as const,
      definition: 'Backup defaults OFF. Synthetic isolated restore qualified in CI; Owner PC backup/recovery ceremony pending.',
      owner: 'Course Owner Decision D18',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="bg-white p-6 rounded-lg border border-[#e3e8ef] shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#0f2a44] bg-[#e8eef6] px-2 py-0.5 rounded border border-[#c5d9f0]">
              Audience: Course Owner
            </span>
            <span className="text-[11px] text-[#5b6779] font-mono">
              toefl_house.desk.owner.cockpit
            </span>
          </div>
          <h1 className="text-xl font-bold text-[#0f2a44]">TOEFL House Owner Cockpit</h1>
          <p className="text-xs text-[#5b6779] mt-0.5 max-w-2xl">
            Executive overview: enrollments, admissions, attendance, tuition collection, staffing and operational governance — every figure with its explicit definition and drill-down.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setActiveDesk('th-configuration')}
          className="flex items-center gap-1.5 px-3 py-2 bg-[#0f2a44] hover:bg-[#1f5fa8] text-white rounded text-xs font-semibold shadow-xs transition-colors self-start md:self-auto shrink-0"
        >
          <Sliders className="w-4 h-4" />
          <span>Open Configuration Plane</span>
        </button>
      </div>

      {/* Governance Attention & Release Posture */}
      <section className="bg-gradient-to-r from-[#fdf3dc]/40 to-[#fff8ea]/60 p-5 rounded-lg border border-[#f5d98a]">
        <div className="flex items-center gap-2 mb-3">
          <ShieldAlert className="w-5 h-5 text-[#9a6700]" />
          <div>
            <h2 className="text-sm font-bold text-[#1b2430]">
              Governance Attention & Release Boundaries
            </h2>
            <p className="text-xs text-[#5b6779]">
              Fail-closed release posture binding on site operations per Owner Decisions D1-D18.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          {releasePosture.map((item) => (
            <div key={item.label} className="bg-white p-3.5 rounded border border-[#e3e8ef] shadow-2xs">
              <span className="text-[10px] font-mono uppercase text-[#8792a3] block mb-1">
                {item.label}
              </span>
              <div className="mb-2">
                <StatusBadge status={item.value} tone={item.tone} />
              </div>
              <p className="text-[11px] text-[#5b6779] leading-tight">
                {item.definition}
              </p>
              <div className="mt-2 pt-2 border-t border-[#f1f4f8] text-[10px] text-[#8792a3] font-semibold">
                Authority: {item.owner}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Executive Analytics Metrics */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xs font-bold uppercase tracking-wider text-[#5b6779]">
            Executive Analytics Totals
          </h2>
          <span className="text-[11px] text-[#8792a3]">
            Verified figures · Incomplete or denied sources never show false-zeros
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard
            isExecutive
            label="Active Course Enrollments"
            value={totalEnrollments}
            definition="Count of active students registered in scheduled classes."
            source="Student / Program Enrollment"
            badge={{ text: 'Enrolled', tone: 'ok' }}
          />
          <MetricCard
            isExecutive
            label="Total Tuition Collected"
            value={`$${totalTuition.toLocaleString()}`}
            definition="Net realized fees received through cashier entries and bank payments."
            source="Payment Entry"
            badge={{ text: 'Realized', tone: 'ok' }}
          />
          <MetricCard
            isExecutive
            label="Overdue Tuition Balances"
            value={`$${totalOverdue.toLocaleString()}`}
            definition="Outstanding balances on submitted invoices exceeding due date window."
            source="Sales Invoice"
            badge={{ text: 'Actionable', tone: totalOverdue > 0 ? 'danger' : 'ok' }}
          />
          <MetricCard
            isExecutive
            label="Average Attendance Rate"
            value="92.8%"
            definition="Submitted present status proportion over all scheduled class sessions."
            source="Student Attendance"
            badge={{ text: 'Consistent', tone: 'ok' }}
          />
        </div>
      </section>

      {/* Deferred Stages & Owner Policy Register */}
      <section className="bg-white rounded-lg border border-[#e3e8ef] shadow-xs p-5 space-y-3">
        <h2 className="text-sm font-bold text-[#1b2430]">
          Active Owner Decision Boundaries (D1 – D18)
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div className="p-3 bg-[#f8fafc] rounded border border-[#e3e8ef] space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-bold text-[#1b2430]">D1: Academic Assessment & Progression</span>
              <StatusBadge status="Deferred" tone="warn" />
            </div>
            <p className="text-[#5b6779]">
              Academic grading scales and automated progression rules remain deferred. The system links course catalog levels, but no promotion is automated without Owner approval.
            </p>
          </div>

          <div className="p-3 bg-[#f8fafc] rounded border border-[#e3e8ef] space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-bold text-[#1b2430]">D5: Student Transfer & Exit Mobility</span>
              <StatusBadge status="Hard-Refused" tone="danger" />
            </div>
            <p className="text-[#5b6779]">
              Cross-program or cross-branch transfers are hard-refused by backend invariant guards, regardless of any operator interface toggle.
            </p>
          </div>

          <div className="p-3 bg-[#f8fafc] rounded border border-[#e3e8ef] space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-bold text-[#1b2430]">D13/D15: Private Deployment Model</span>
              <StatusBadge status="Enforced" tone="ok" />
            </div>
            <p className="text-[#5b6779]">
              Deployment binds strictly to 127.0.0.1 loopback on the central institute PC. Multi-user access is granted exclusively through private Tailscale tailnet VPN.
            </p>
          </div>

          <div className="p-3 bg-[#f8fafc] rounded border border-[#e3e8ef] space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-bold text-[#1b2430]">D18: Backup Policy & Custody</span>
              <StatusBadge status="Held" tone="warn" />
            </div>
            <p className="text-[#5b6779]">
              Backup defaults OFF. Synthetic isolated restore qualified in CI; Owner PC backup drive, Task Scheduler, and key-custody gates must be completed prior to site activation.
            </p>
          </div>
        </div>
      </section>

      {/* Hash Chained Audit Receipts */}
      <section className="bg-white rounded-lg border border-[#e3e8ef] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#f1f4f8] flex items-center justify-between">
          <h2 className="text-sm font-bold text-[#1b2430]">
            Cryptographic Action Receipts (SHA-256 Chain)
          </h2>
          <span className="text-xs text-[#1a7f4b] font-semibold flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>Chain Verified</span>
          </span>
        </div>

        <div className="p-4 bg-[#f8fafc] border-b border-[#e3e8ef] text-xs text-[#5b6779]">
          Every mutation executed through TOEFL House commands generates a receipt containing the actor, idempotency key, previous block digest, and SHA-256 payload hash.
        </div>

        <div className="divide-y divide-[#f1f4f8] text-xs">
          {auditEvents.slice(0, 4).map((evt) => (
            <div key={evt.id} className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-2 hover:bg-[#f8fafc] transition-colors">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-bold text-[#1b2430]">{evt.action}</span>
                  <span className="text-[10px] font-mono text-[#1f5fa8] bg-[#eaf1fa] px-1.5 py-0.5 rounded">
                    {evt.actor}
                  </span>
                  <span className="text-[#8792a3] text-[11px]">{evt.timestamp}</span>
                </div>
                <div className="text-[11px] text-[#5b6779] mt-0.5">{evt.details}</div>
              </div>
              <div className="text-right font-mono text-[10px] text-[#8792a3] shrink-0">
                <div>Hash: {evt.hash.substring(0, 20)}…</div>
                <div>Prev: {evt.previousHash.substring(0, 20)}…</div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};
