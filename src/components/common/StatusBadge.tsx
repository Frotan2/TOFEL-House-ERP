import React from 'react';
import { StatusTone } from '../../types';

interface StatusBadgeProps {
  status: string;
  tone?: StatusTone;
  className?: string;
}

const STATUS_MAP: Record<string, StatusTone> = {
  // ok (green)
  active: 'ok',
  approved: 'ok',
  completed: 'ok',
  submitted: 'ok',
  paid: 'ok',
  settled: 'ok',
  received: 'ok',
  released: 'ok',
  finalized: 'ok',
  posted: 'ok',
  'credit note issued': 'ok',
  effective: 'ok',
  validated: 'ok',
  configured: 'ok',
  present: 'ok',
  reconciled: 'ok',
  balanced: 'ok',
  'configured & active': 'ok',
  tested: 'ok',
  enrolled: 'ok',

  // info (blue)
  draft: 'info',
  review: 'info',
  open: 'info',
  applied: 'info',
  allocated: 'info',
  verified: 'info',
  'in progress': 'info',
  'in review': 'info',
  sealed: 'info',
  marking: 'info',
  outstanding: 'info',
  unpaid: 'info',
  unbilled: 'info',
  student: 'info',
  scheduled: 'info',
  planned: 'info',
  defined: 'info',
  registered: 'info',
  'placement scheduled': 'info',
  'draft version': 'info',

  // warn (amber/yellow)
  requested: 'warn',
  conditional: 'warn',
  deferred: 'warn',
  overdue: 'warn',
  unstaffed: 'warn',
  expired: 'warn',
  pending: 'warn',
  awaiting: 'warn',
  attention: 'warn',
  partial: 'warn',
  leave: 'warn',
  discrepancy: 'warn',
  'action needed': 'warn',
  'deferred (d1/d5)': 'warn',

  // danger (red)
  rejected: 'danger',
  cancelled: 'danger',
  canceled: 'danger',
  revoked: 'danger',
  withdrawn: 'danger',
  return: 'danger',
  failed: 'danger',
  blocked: 'danger',
  error: 'danger',
  absent: 'danger',
  voided: 'danger',
  dismissed: 'danger',
  reject: 'danger',
  unconfigured: 'danger',

  // neutral (gray)
  archived: 'neutral',
  retired: 'neutral',
  empty: 'neutral',
  unknown: 'neutral',
  closed: 'neutral',
  inactive: 'neutral',
  'on leave': 'neutral',
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, tone, className = '' }) => {
  const normalizedKey = status.trim().toLowerCase();
  const resolvedTone: StatusTone = tone || STATUS_MAP[normalizedKey] || 'neutral';

  const toneStyles: Record<StatusTone, string> = {
    ok: 'bg-[#e7f4ec] text-[#1a7f4b] border-[#a8d5ba]',
    info: 'bg-[#eaf1fa] text-[#1f5fa8] border-[#c5d9f0]',
    warn: 'bg-[#fdf3dc] text-[#9a6700] border-[#f5d98a]',
    danger: 'bg-[#fdecea] text-[#b42318] border-[#f5b5b0]',
    neutral: 'bg-[#f1f4f8] text-[#5b6779] border-[#d0d8e2]',
  };

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border uppercase tracking-wider ${toneStyles[resolvedTone]} ${className}`}
    >
      {status}
    </span>
  );
};
