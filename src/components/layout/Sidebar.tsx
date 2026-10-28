import React from 'react';
import {
  Users,
  GraduationCap,
  CircleDollarSign,
  Briefcase,
  SlidersHorizontal,
  Compass,
  FileSpreadsheet,
  Terminal,
  ShieldCheck,
  BookOpen,
} from 'lucide-react';
import { useERP } from '../../context/ERPContext';
import { DeskSlug } from '../../types';

interface NavItem {
  slug: DeskSlug;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  roleAudience: string;
  badgeCount?: number;
}

export const Sidebar: React.FC = () => {
  const {
    activeDesk,
    setActiveDesk,
    activeRole,
    admissionDecisions,
    invoices,
    enrollments,
    attendanceCorrections,
    placementAttempts,
  } = useERP();

  // Pending queue counters
  const pendingAdmissions = admissionDecisions.filter((d) => d.status === 'Review').length;
  const overdueInvoices = invoices.filter((i) => i.status === 'Overdue' || i.status === 'Unpaid').length;
  const unbilledEnrollments = enrollments.filter((e) => !e.feeIssued).length;
  const pendingCorrections = attendanceCorrections.filter((c) => c.status === 'Pending').length;
  const pendingPlacements = placementAttempts.filter(
    (a) => a.status === 'Marking' || a.status === 'Review'
  ).length;

  const navItems: NavItem[] = [
    {
      slug: 'th-reception-desk',
      label: 'Reception Desk',
      icon: Users,
      roleAudience: 'Reception',
      badgeCount: pendingAdmissions > 0 ? pendingAdmissions : undefined,
    },
    {
      slug: 'th-academic-desk',
      label: 'Academic Desk',
      icon: GraduationCap,
      roleAudience: 'Academic Manager',
      badgeCount: pendingPlacements > 0 ? pendingPlacements : undefined,
    },
    {
      slug: 'th-finance-desk',
      label: 'Finance Desk',
      icon: CircleDollarSign,
      roleAudience: 'Finance Manager',
      badgeCount: overdueInvoices + unbilledEnrollments > 0 ? overdueInvoices + unbilledEnrollments : undefined,
    },
    {
      slug: 'th-operations-desk',
      label: 'Operations Desk',
      icon: Briefcase,
      roleAudience: 'General Manager',
      badgeCount: pendingCorrections > 0 ? pendingCorrections : undefined,
    },
    {
      slug: 'th-owner-cockpit',
      label: 'Owner Cockpit',
      icon: Compass,
      roleAudience: 'Course Owner',
    },
    {
      slug: 'th-teacher-desk',
      label: 'Teacher Desk',
      icon: BookOpen,
      roleAudience: 'Instructor',
    },
    {
      slug: 'th-academic-setup',
      label: 'Academic Setup',
      icon: SlidersHorizontal,
      roleAudience: 'Course Owner',
    },
    {
      slug: 'th-configuration',
      label: 'Configuration Plane',
      icon: FileSpreadsheet,
      roleAudience: 'Course Owner',
    },
    {
      slug: 'th-command-centre',
      label: 'Command Centre',
      icon: Terminal,
      roleAudience: 'All Roles',
    },
  ];

  return (
    <aside className="w-64 bg-white border-r border-[#e3e8ef] flex flex-col shrink-0 min-h-[calc(100vh-53px)] select-none">
      <div className="p-3 border-b border-[#f1f4f8]">
        <span className="text-[10px] font-bold uppercase tracking-wider text-[#8792a3] px-3">
          Daily Work Surfaces
        </span>
      </div>

      <nav className="p-2 space-y-1 flex-1">
        {navItems.map((item) => {
          const isActive = activeDesk === item.slug;
          const isPrimaryForRole = item.roleAudience === activeRole;
          const Icon = item.icon;

          return (
            <button
              key={item.slug}
              type="button"
              onClick={() => setActiveDesk(item.slug)}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-md text-xs font-semibold transition-all text-left ${
                isActive
                  ? 'bg-[#1f5fa8] text-white shadow-xs'
                  : isPrimaryForRole
                  ? 'text-[#1f5fa8] bg-[#eaf1fa] hover:bg-[#dbe7f6]'
                  : 'text-[#5b6779] hover:bg-[#f6f8fa] hover:text-[#1b2430]'
              }`}
            >
              <div className="flex items-center gap-2.5 truncate">
                <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-white' : isPrimaryForRole ? 'text-[#1f5fa8]' : 'text-[#8792a3]'}`} />
                <span className="truncate">{item.label}</span>
              </div>

              {item.badgeCount !== undefined && (
                <span
                  className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                    isActive
                      ? 'bg-white text-[#1f5fa8]'
                      : 'bg-[#fdf3dc] text-[#9a6700] border border-[#f5d98a]'
                  }`}
                >
                  {item.badgeCount}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Footer Info */}
      <div className="p-3 bg-[#f8fafc] border-t border-[#e3e8ef] text-[11px] text-[#5b6779]">
        <div className="flex items-center gap-1.5 text-[#1a7f4b] font-semibold mb-1">
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>Guarded Commands</span>
        </div>
        <p className="text-[10px] text-[#8792a3] leading-tight">
          Role-scoped execution with SHA-256 hash receipts. No raw CRUD bypass.
        </p>
      </div>
    </aside>
  );
};
