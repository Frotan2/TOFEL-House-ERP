import React, { useState } from 'react';
import {
  ShieldAlert,
  Building2,
  UserCheck,
  Search,
  RotateCcw,
  Sparkles,
} from 'lucide-react';
import { useERP } from '../../context/ERPContext';
import { InstituteRole, Branch } from '../../types';

export const Header: React.FC = () => {
  const {
    activeRole,
    setActiveRole,
    activeBranch,
    setActiveBranch,
    resetToDemoData,
  } = useERP();

  const [searchQuery, setSearchQuery] = useState('');
  const [showSearchModal, setShowSearchModal] = useState(false);

  const roles: InstituteRole[] = [
    'Course Owner',
    'General Manager',
    'Reception',
    'Academic Manager',
    'Finance Manager',
    'Instructor',
  ];

  const branches: (Branch | 'All Branches')[] = [
    'All Branches',
    'Kabul Central',
    'West Campus',
    'Online',
  ];

  return (
    <header className="bg-white border-b border-[#e3e8ef] sticky top-0 z-40 px-6 py-2.5 flex items-center justify-between shadow-2xs">
      {/* Brand & Eyebrow */}
      <div className="flex items-center gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#1f5fa8] bg-[#eaf1fa] px-1.5 py-0.5 rounded border border-[#c5d9f0]">
              TOEFL House
            </span>
            <span className="text-[11px] text-[#5b6779] font-medium hidden sm:inline">
              Course Management ERP
            </span>
          </div>
          <h1 className="text-base font-bold text-[#1b2430] tracking-tight">
            Academic & Operations System
          </h1>
        </div>

        {/* System Release Hold Banner */}
        <div className="hidden lg:flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#fdf3dc] border border-[#f5d98a] text-[11px] text-[#9a6700]">
          <ShieldAlert className="w-3.5 h-3.5 shrink-0" />
          <span>Release Hold Active · Synthetic Site Mode</span>
        </div>
      </div>

      {/* Role & Branch Selectors */}
      <div className="flex items-center gap-3">
        {/* Branch Selector */}
        <div className="flex items-center gap-1.5 text-xs">
          <Building2 className="w-3.5 h-3.5 text-[#5b6779] hidden md:inline" />
          <select
            value={activeBranch}
            onChange={(e) => setActiveBranch(e.target.value as Branch | 'All Branches')}
            className="border border-[#cdd5e0] bg-[#f8fafc] text-[#1b2430] rounded px-2.5 py-1 text-xs font-semibold focus:outline-none focus:border-[#1f5fa8]"
          >
            {branches.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </div>

        {/* Role Switcher */}
        <div className="flex items-center gap-1.5 text-xs">
          <UserCheck className="w-3.5 h-3.5 text-[#1f5fa8]" />
          <span className="text-xs text-[#5b6779] hidden md:inline font-medium">Viewing as:</span>
          <select
            value={activeRole}
            onChange={(e) => setActiveRole(e.target.value as InstituteRole)}
            className="border border-[#1f5fa8] bg-[#eaf1fa] text-[#1f5fa8] rounded px-3 py-1 text-xs font-bold focus:outline-none"
          >
            {roles.map((r) => (
              <option key={r} value={r}>
                {r} Desk
              </option>
            ))}
          </select>
        </div>

        {/* Demo Data Reset */}
        <button
          type="button"
          onClick={() => {
            if (confirm('Reset all demo state to fresh TOEFL House seed records?')) {
              resetToDemoData();
            }
          }}
          title="Reset Demo Data"
          className="flex items-center gap-1 text-[11px] text-[#5b6779] hover:text-[#b42318] border border-[#cdd5e0] hover:border-[#f5b5b0] hover:bg-[#fdecea] px-2 py-1 rounded transition-all"
        >
          <RotateCcw className="w-3 h-3" />
          <span className="hidden sm:inline">Reset Demo</span>
        </button>
      </div>
    </header>
  );
};
