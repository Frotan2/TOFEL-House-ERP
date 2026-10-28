import React from 'react';
import { HelpCircle } from 'lucide-react';

interface MetricCardProps {
  label: string;
  value: string | number;
  definition: string;
  source?: string;
  scope?: string;
  badge?: {
    text: string;
    tone?: 'ok' | 'info' | 'warn' | 'danger' | 'neutral';
  };
  onClick?: () => void;
  isExecutive?: boolean;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  definition,
  source,
  scope,
  badge,
  onClick,
  isExecutive = false,
}) => {
  return (
    <div
      onClick={onClick}
      className={`p-4 rounded-lg border transition-all ${
        onClick ? 'cursor-pointer hover:border-[#1f5fa8] hover:shadow-sm' : ''
      } ${
        isExecutive
          ? 'bg-gradient-to-br from-[#ffffff] to-[#f4f7fb] border-[#cdd5e0]'
          : 'bg-white border-[#e3e8ef]'
      }`}
    >
      <div className="flex items-start justify-between gap-2 mb-1">
        <span className="text-xs font-semibold text-[#5b6779] uppercase tracking-wider">
          {label}
        </span>
        {badge && (
          <span
            className={`text-[10px] font-bold px-1.5 py-0.5 rounded border uppercase ${
              badge.tone === 'ok'
                ? 'bg-[#e7f4ec] text-[#1a7f4b] border-[#a8d5ba]'
                : badge.tone === 'warn'
                ? 'bg-[#fdf3dc] text-[#9a6700] border-[#f5d98a]'
                : badge.tone === 'danger'
                ? 'bg-[#fdecea] text-[#b42318] border-[#f5b5b0]'
                : 'bg-[#eaf1fa] text-[#1f5fa8] border-[#c5d9f0]'
            }`}
          >
            {badge.text}
          </span>
        )}
      </div>

      <div className="flex items-baseline gap-2 my-1">
        <span
          className={`font-bold tracking-tight ${
            isExecutive ? 'text-2xl text-[#0f2a44]' : 'text-xl text-[#1b2430]'
          }`}
        >
          {value}
        </span>
      </div>

      <div className="mt-2 pt-2 border-t border-[#f1f4f8] text-[11px] text-[#6b778c] flex flex-col gap-1">
        <div className="flex items-start gap-1">
          <HelpCircle className="w-3 h-3 text-[#8792a3] mt-0.5 shrink-0" />
          <span className="leading-snug">{definition}</span>
        </div>
        {(source || scope) && (
          <div className="flex justify-between items-center text-[10px] text-[#8792a3] mt-0.5">
            {source && <span>Source: {source}</span>}
            {scope && <span className="italic">{scope}</span>}
          </div>
        )}
      </div>
    </div>
  );
};
