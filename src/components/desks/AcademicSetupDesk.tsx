import React, { useState } from 'react';
import {
  SlidersHorizontal,
  Layers,
  Clock,
  BookOpen,
  Info,
  CheckCircle2,
  AlertCircle,
  Plus,
} from 'lucide-react';
import { useERP } from '../../context/ERPContext';
import { StatusBadge } from '../common/StatusBadge';
import { MetricCard } from '../common/MetricCard';

export const AcademicSetupDesk: React.FC = () => {
  const { programs, levels, durationPolicies } = useERP();
  const [selectedProgramCode, setSelectedProgramCode] = useState<string>('TOEFL-PREP');

  const activeProgram = programs.find((p) => p.code === selectedProgramCode) || programs[0];
  const programLevels = levels.filter((l) => l.programCode === selectedProgramCode);

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
              toefl_house.desk.setup.work
            </span>
          </div>
          <h1 className="text-xl font-bold text-[#1b2430]">TOEFL House Academic Setup</h1>
          <p className="text-xs text-[#5b6779] mt-0.5 max-w-2xl">
            Programs, ordered levels, effective-dated durations and progression — the configuration the whole institution runs on.
          </p>
        </div>
      </div>

      {/* Owner D1 Deferral Boundary Notice */}
      <div className="p-4 bg-[#fdf3dc]/70 border border-[#f5d98a] rounded-lg text-xs flex items-start gap-3">
        <Info className="w-5 h-5 text-[#9a6700] shrink-0 mt-0.5" />
        <div className="space-y-1">
          <h3 className="font-bold text-[#1b2430]">
            Owner Decision D1 — Academic Grading & Promotion Rules Deferred
          </h3>
          <p className="text-[#5b6779] leading-relaxed">
            The catalog linkage between programs and courses is active and enforced. However, automated promotion decisions, grade-boundary calculations, and assessment policies remain reference facets only. No automated promotion rule operates without explicit Course Owner release authorization.
          </p>
        </div>
      </div>

      {/* Program Family Selector */}
      <section className="bg-white p-4 rounded-lg border border-[#e3e8ef] shadow-xs">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-bold uppercase tracking-wider text-[#5b6779]">
            Active Academic Program Families
          </span>
          <span className="text-xs text-[#8792a3]">
            {programs.length} program curricula active
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {programs.map((p) => {
            const isSelected = p.code === selectedProgramCode;
            return (
              <button
                key={p.code}
                type="button"
                onClick={() => setSelectedProgramCode(p.code)}
                className={`p-3.5 rounded-lg border text-left transition-all ${
                  isSelected
                    ? 'border-[#1f5fa8] bg-[#eaf1fa] shadow-xs ring-1 ring-[#1f5fa8]'
                    : 'border-[#e3e8ef] bg-white hover:bg-[#f8fafc]'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-xs font-bold text-[#1f5fa8]">
                    {p.code}
                  </span>
                  <StatusBadge status={p.status} />
                </div>
                <div className="font-bold text-sm text-[#1b2430]">{p.name}</div>
                <div className="text-[11px] text-[#5b6779] mt-1 line-clamp-2">
                  {p.description}
                </div>
                {p.targetExam && (
                  <div className="mt-2 text-[10px] text-[#8792a3] font-semibold">
                    Target: {p.targetExam}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </section>

      {/* Program Ordered Levels */}
      <section className="bg-white rounded-lg border border-[#e3e8ef] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#f1f4f8] flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-[#1b2430]">
              Ordered Levels for {activeProgram.name}
            </h2>
            <p className="text-xs text-[#5b6779] mt-0.5">
              Governing durations, standard weekly session counts, and CEFR benchmarks.
            </p>
          </div>
          <span className="text-xs font-mono text-[#5b6779]">
            {programLevels.length} tier(s)
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#f8fafc] text-[#5b6779] uppercase font-semibold text-[10px] tracking-wider border-b border-[#e3e8ef]">
              <tr>
                <th className="px-4 py-3">Order</th>
                <th className="px-4 py-3">Level Name</th>
                <th className="px-4 py-3">CEFR Benchmark</th>
                <th className="px-4 py-3">Standard Duration</th>
                <th className="px-4 py-3">Instructional Hours</th>
                <th className="px-4 py-3">Catalog Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f1f4f8]">
              {programLevels.map((lvl) => (
                <tr key={lvl.id} className="hover:bg-[#f8fafc] transition-colors">
                  <td className="px-4 py-3 font-mono font-bold text-[#1f5fa8]">
                    Tier {lvl.levelOrder}
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-bold text-[#1b2430]">{lvl.levelName}</div>
                    <div className="text-[10px] text-[#8792a3] font-mono">{lvl.id}</div>
                  </td>
                  <td className="px-4 py-3 font-semibold text-[#0f2a44]">
                    {lvl.cefrEquivalent}
                  </td>
                  <td className="px-4 py-3 font-mono text-[#5b6779]">
                    {lvl.standardDurationWeeks} weeks (4x/week)
                  </td>
                  <td className="px-4 py-3 font-mono font-bold text-[#1b2430]">
                    {lvl.totalHours} contact hours
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={lvl.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Effective-Dated Duration Policies */}
      <section className="bg-white rounded-lg border border-[#e3e8ef] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#f1f4f8] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-[#1f5fa8]" />
            <div>
              <h2 className="text-sm font-bold text-[#1b2430]">
                Effective-Dated Level Duration Policies
              </h2>
              <p className="text-xs text-[#5b6779]">
                Configured duration terms that governing class schedules and student group creation inherit.
              </p>
            </div>
          </div>
          <span className="text-xs font-mono text-[#5b6779]">
            {durationPolicies.length} policy model(s)
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#f8fafc] text-[#5b6779] uppercase font-semibold text-[10px] tracking-wider border-b border-[#e3e8ef]">
              <tr>
                <th className="px-4 py-3">Policy Code</th>
                <th className="px-4 py-3">Title & Model</th>
                <th className="px-4 py-3">Term Length</th>
                <th className="px-4 py-3">Weekly Schedule</th>
                <th className="px-4 py-3">Total Hours</th>
                <th className="px-4 py-3">Effective Date</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f1f4f8]">
              {durationPolicies.map((pol) => (
                <tr key={pol.id} className="hover:bg-[#f8fafc] transition-colors">
                  <td className="px-4 py-3 font-mono font-semibold text-[#1b2430]">
                    {pol.code}
                  </td>
                  <td className="px-4 py-3 font-bold text-[#1b2430]">
                    {pol.title}
                  </td>
                  <td className="px-4 py-3 font-mono">
                    {pol.weeks} weeks
                  </td>
                  <td className="px-4 py-3 text-[#5b6779]">
                    {pol.sessionsPerWeek} sessions/wk ({pol.hoursPerSession} hrs/session)
                  </td>
                  <td className="px-4 py-3 font-mono font-bold text-[#0f2a44]">
                    {pol.totalHours} hrs
                  </td>
                  <td className="px-4 py-3 text-[#5b6779] font-mono">
                    {pol.effectiveFrom}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={pol.status} />
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
