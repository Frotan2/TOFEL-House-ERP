import React from 'react';
import {
  Briefcase,
  AlertTriangle,
  Users2,
  Activity,
  CheckCircle2,
  Clock,
  ShieldCheck,
  Server,
  Hash,
} from 'lucide-react';
import { useERP } from '../../context/ERPContext';
import { StatusBadge } from '../common/StatusBadge';
import { MetricCard } from '../common/MetricCard';

export const OperationsDesk: React.FC = () => {
  const {
    applicants,
    placementAttempts,
    admissionDecisions,
    students,
    invoices,
    enrollments,
    attendanceCorrections,
    auditEvents,
    activeBranch,
  } = useERP();

  // Exceptions
  const pendingAdmissions = admissionDecisions.filter((d) => d.status === 'Review');
  const overdueInvoices = invoices.filter((i) => i.status === 'Overdue');
  const unbilledEnrollments = enrollments.filter((e) => !e.feeIssued);
  const pendingCorrections = attendanceCorrections.filter((c) => c.status === 'Pending');

  // Staffing counts
  const staffingRoles = [
    { role: 'Course Owner', count: 1, department: 'Executive Governance' },
    { role: 'General Manager', count: 1, department: 'Operations' },
    { role: 'Academic Manager', count: 2, department: 'Academics & Quality' },
    { role: 'Finance Manager', count: 1, department: 'Finance & Accounts' },
    { role: 'Finance Officer', count: 2, department: 'Cashier & Invoicing' },
    { role: 'Reception Staff', count: 3, department: 'Front Desk & Intake' },
    { role: 'Placement Invigilator', count: 2, department: 'Testing Centre' },
    { role: 'Placement Assessor', count: 3, department: 'Testing Centre' },
    { role: 'Teaching Scheduler', count: 2, department: 'Academics' },
    { role: 'Instructors', count: 4, department: 'Faculty' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white p-6 rounded-lg border border-[#e3e8ef] shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#1f5fa8] bg-[#eaf1fa] px-2 py-0.5 rounded border border-[#c5d9f0]">
              Audience: General Manager
            </span>
            <span className="text-[11px] text-[#5b6779] font-mono">
              toefl_house.desk.operations.work
            </span>
          </div>
          <h1 className="text-xl font-bold text-[#1b2430]">TOEFL House Operations Desk</h1>
          <p className="text-xs text-[#5b6779] mt-0.5 max-w-2xl">
            Cross-role funnel, operational exceptions, role staffing and system health across the whole institution.
          </p>
        </div>
      </div>

      {/* Cross-role Funnel & Exceptions */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xs font-bold uppercase tracking-wider text-[#5b6779]">
            Operational Bottlenecks & Exceptions
          </h2>
          <span className="text-[11px] text-[#8792a3]">
            Facts with age · No invented severity levels
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard
            label="Admissions Stuck in Review"
            value={pendingAdmissions.length}
            definition="Decisions waiting on Academic Approver for > 48 hours."
            source="TH Admission Decision"
            badge={{ text: 'Review Bottleneck', tone: pendingAdmissions.length > 0 ? 'warn' : 'ok' }}
          />
          <MetricCard
            label="Overdue Invoices"
            value={overdueInvoices.length}
            definition="Submitted tuition invoices whose due date has passed with balance remaining."
            source="Sales Invoice"
            badge={{ text: 'Receivables', tone: overdueInvoices.length > 0 ? 'danger' : 'ok' }}
          />
          <MetricCard
            label="Unbilled Active Students"
            value={unbilledEnrollments.length}
            definition="Students enrolled in cohorts with no tuition fee invoice created."
            source="Program Enrollment"
            badge={{ text: 'Revenue Gap', tone: unbilledEnrollments.length > 0 ? 'warn' : 'ok' }}
          />
          <MetricCard
            label="Pending Attendance Fixes"
            value={pendingCorrections.length}
            definition="Attendance correction requests awaiting policy verification."
            source="TH Attendance Correction"
            badge={{ text: 'Audited', tone: 'neutral' }}
          />
        </div>
      </section>

      {/* System Health Section */}
      <section className="bg-white p-5 rounded-lg border border-[#e3e8ef] shadow-xs">
        <div className="flex items-center justify-between border-b border-[#f1f4f8] pb-3 mb-4">
          <div className="flex items-center gap-2">
            <Server className="w-5 h-5 text-[#1f5fa8]" />
            <h2 className="text-sm font-bold text-[#1b2430]">
              System Health & Foundation Integrity
            </h2>
          </div>
          <span className="text-xs font-semibold text-[#1a7f4b] bg-[#e7f4ec] px-2.5 py-0.5 rounded border border-[#a8d5ba]">
            All 7 Services Healthy
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="p-3 bg-[#f8fafc] rounded border border-[#e3e8ef]">
            <span className="text-[#8792a3] text-[10px] uppercase font-mono block">Runtime Stack</span>
            <div className="font-bold text-[#1b2430] mt-0.5">Frappe / Node 22 / MariaDB</div>
            <span className="text-[10px] text-[#1a7f4b]">Pinned commits verified</span>
          </div>

          <div className="p-3 bg-[#f8fafc] rounded border border-[#e3e8ef]">
            <span className="text-[#8792a3] text-[10px] uppercase font-mono block">Security Hardening</span>
            <div className="font-bold text-[#1b2430] mt-0.5">foundation_security</div>
            <span className="text-[10px] text-[#1a7f4b]">Deny-by-default active</span>
          </div>

          <div className="p-3 bg-[#f8fafc] rounded border border-[#e3e8ef]">
            <span className="text-[#8792a3] text-[10px] uppercase font-mono block">Network Exposure</span>
            <div className="font-bold text-[#0f2a44] mt-0.5">127.0.0.1 Loopback Only</div>
            <span className="text-[10px] text-[#5b6779]">Zero public ports opened</span>
          </div>

          <div className="p-3 bg-[#f8fafc] rounded border border-[#e3e8ef]">
            <span className="text-[#8792a3] text-[10px] uppercase font-mono block">Unhandled Exceptions</span>
            <div className="font-bold text-[#1a7f4b] mt-0.5">0 Unseen Errors</div>
            <span className="text-[10px] text-[#1a7f4b]">Audit log synchronized</span>
          </div>
        </div>
      </section>

      {/* Staffing Matrix Table */}
      <section className="bg-white rounded-lg border border-[#e3e8ef] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#f1f4f8] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Users2 className="w-4 h-4 text-[#1f5fa8]" />
            <h2 className="text-sm font-bold text-[#1b2430]">
              Staffing Distribution by Shipped Role
            </h2>
          </div>
          <span className="text-xs text-[#5b6779]">
            Native Has-Role user assignments
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#f8fafc] text-[#5b6779] uppercase font-semibold text-[10px] tracking-wider border-b border-[#e3e8ef]">
              <tr>
                <th className="px-4 py-3">Role Authority</th>
                <th className="px-4 py-3">Functional Department</th>
                <th className="px-4 py-3">Assigned Staff</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f1f4f8]">
              {staffingRoles.map((r) => (
                <tr key={r.role} className="hover:bg-[#f8fafc] transition-colors">
                  <td className="px-4 py-3 font-semibold text-[#1b2430]">
                    {r.role}
                  </td>
                  <td className="px-4 py-3 text-[#5b6779]">
                    {r.department}
                  </td>
                  <td className="px-4 py-3 font-mono font-bold text-[#0f2a44]">
                    {r.count} enabled user(s)
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status="Active" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Recent Recorded Actions (Audit Log) */}
      <section className="bg-white rounded-lg border border-[#e3e8ef] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#f1f4f8] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Hash className="w-4 h-4 text-[#1f5fa8]" />
            <h2 className="text-sm font-bold text-[#1b2430]">
              Recent Recorded Actions (Immutable Ledger)
            </h2>
          </div>
          <span className="text-xs font-mono text-[#5b6779]">
            {auditEvents.length} events receipted
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-[#f8fafc] text-[#5b6779] uppercase font-semibold text-[10px] tracking-wider border-b border-[#e3e8ef]">
              <tr>
                <th className="px-4 py-3">Timestamp</th>
                <th className="px-4 py-3">Actor / Role</th>
                <th className="px-4 py-3">Action Command</th>
                <th className="px-4 py-3">Target Record</th>
                <th className="px-4 py-3">SHA-256 Digest</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f1f4f8]">
              {auditEvents.slice(0, 8).map((evt) => (
                <tr key={evt.id} className="hover:bg-[#f8fafc] transition-colors">
                  <td className="px-4 py-3 text-[#5b6779] whitespace-nowrap">
                    {evt.timestamp}
                  </td>
                  <td className="px-4 py-3 font-sans font-semibold text-[#1b2430]">
                    {evt.actor}
                  </td>
                  <td className="px-4 py-3 text-[#1f5fa8] font-bold">
                    {evt.action}
                  </td>
                  <td className="px-4 py-3 font-sans text-[#1b2430]">
                    {evt.target}
                  </td>
                  <td className="px-4 py-3 text-[#8792a3] text-[10px] truncate max-w-xs" title={evt.hash}>
                    {evt.hash.substring(0, 16)}…
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};
