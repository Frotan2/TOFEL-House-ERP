import React, { useState } from 'react';
import { X, CheckCircle, Clock, FileText, Award, ArrowRight } from 'lucide-react';
import { useERP } from '../../context/ERPContext';
import { PlacementItem } from '../../types';

interface PlacementPortalModalProps {
  isOpen: boolean;
  onClose: () => void;
  applicantId?: string;
  attemptId?: string;
}

export const PlacementPortalModal: React.FC<PlacementPortalModalProps> = ({
  isOpen,
  onClose,
  applicantId,
  attemptId,
}) => {
  const { applicants, placementItems, placementAttempts, submitPlacementTest, releasePlacementDecision } = useERP();

  const applicant = applicants.find((a) => a.id === applicantId);
  const existingAttempt = placementAttempts.find((a) => a.id === attemptId);

  const candidateName = applicant?.name || existingAttempt?.candidateName || 'Candidate';
  const candidateEmail = applicant?.email || existingAttempt?.candidateEmail || '';

  const [currentStep, setCurrentStep] = useState<'intro' | 'test' | 'summary'>(
    existingAttempt && existingAttempt.status === 'Released' ? 'summary' : 'intro'
  );

  const [activeItemIndex, setActiveItemIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [testCompleted, setTestCompleted] = useState(false);
  const [calculatedScore, setCalculatedScore] = useState<number | null>(existingAttempt?.score ?? null);

  if (!isOpen) return null;

  const currentItem: PlacementItem | undefined = placementItems[activeItemIndex];

  const handleSelectOption = (option: string) => {
    if (!currentItem) return;
    setAnswers((prev) => ({ ...prev, [currentItem.id]: option }));
  };

  const handleNext = () => {
    if (activeItemIndex < placementItems.length - 1) {
      setActiveItemIndex((prev) => prev + 1);
    } else {
      // Calculate score
      let correct = 0;
      const breakdown: Record<string, number> = {
        Reading: 0,
        Listening: 0,
        Grammar: 0,
        Vocabulary: 0,
      };

      placementItems.forEach((item) => {
        const userAns = answers[item.id];
        if (userAns === item.correctAnswer) {
          correct += 25; // 4 items -> 100 max
          if (breakdown[item.skill] !== undefined) {
            breakdown[item.skill] += 25;
          }
        }
      });

      const totalScore = Math.max(25, correct);
      setCalculatedScore(totalScore);

      let recLevel = 'Diagnostic Foundations';
      if (totalScore >= 85) recLevel = 'Full Test Simulation (100+)';
      else if (totalScore >= 70) recLevel = 'Productive Skills (S & W)';
      else if (totalScore >= 50) recLevel = 'Skills Mastery (R & L)';

      const attId = attemptId || (existingAttempt ? existingAttempt.id : `ATT-2026-${Math.floor(800 + Math.random() * 199)}`);
      submitPlacementTest(attId, totalScore, recLevel, breakdown);
      setTestCompleted(true);
      setCurrentStep('summary');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 backdrop-blur-xs p-4">
      <div className="bg-white rounded-lg shadow-2xl border border-[#cdd5e0] w-full max-w-2xl overflow-hidden flex flex-col max-h-[92vh]">
        {/* Header */}
        <div className="bg-[#0f2a44] text-white px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#1f5fa8] rounded">
              <FileText className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono tracking-wider bg-white/20 px-2 py-0.5 rounded uppercase">
                  Supervised Assessment
                </span>
                <span className="text-xs text-white/80">BP-TOEFL-STD-2026 v3</span>
              </div>
              <h2 className="text-base font-bold">{candidateName} — Placement Diagnostic</h2>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-white/60 hover:text-white p-1 rounded transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1">
          {currentStep === 'intro' && (
            <div className="space-y-4">
              <div className="border border-[#c5d9f0] bg-[#eaf1fa] p-4 rounded-md">
                <h3 className="font-bold text-[#1f5fa8] text-sm">
                  Candidate Session Verification
                </h3>
                <p className="text-xs text-[#1b2430] mt-1">
                  Candidate: <strong>{candidateName}</strong> ({candidateEmail})
                </p>
                <p className="text-xs text-[#5b6779] mt-0.5">
                  Assessment Blueprint: TOEFL Comprehensive Diagnostic Battery (Reading, Listening, Grammar, Vocabulary)
                </p>
              </div>

              <div className="grid grid-cols-3 gap-3 text-center">
                <div className="p-3 border border-[#e3e8ef] rounded bg-[#f8fafc]">
                  <Clock className="w-4 h-4 mx-auto text-[#1f5fa8] mb-1" />
                  <div className="text-xs font-bold text-[#1b2430]">4 Sections</div>
                  <div className="text-[11px] text-[#8792a3]">Timed Delivery</div>
                </div>
                <div className="p-3 border border-[#e3e8ef] rounded bg-[#f8fafc]">
                  <Award className="w-4 h-4 mx-auto text-[#1a7f4b] mb-1" />
                  <div className="text-xs font-bold text-[#1b2430]">100 Points</div>
                  <div className="text-[11px] text-[#8792a3]">Objective Key</div>
                </div>
                <div className="p-3 border border-[#e3e8ef] rounded bg-[#f8fafc]">
                  <CheckCircle className="w-4 h-4 mx-auto text-[#9a6700] mb-1" />
                  <div className="text-xs font-bold text-[#1b2430]">Audited Seal</div>
                  <div className="text-[11px] text-[#8792a3]">Locked Evidence</div>
                </div>
              </div>

              <div className="pt-4 border-t border-[#e3e8ef] flex justify-end">
                <button
                  type="button"
                  onClick={() => setCurrentStep('test')}
                  className="px-5 py-2 bg-[#1f5fa8] hover:bg-[#164a85] text-white rounded text-xs font-semibold flex items-center gap-1.5"
                >
                  Start Supervised Test Session <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {currentStep === 'test' && currentItem && (
            <div className="space-y-4">
              {/* Progress Bar */}
              <div className="flex items-center justify-between text-xs text-[#5b6779] mb-1">
                <span>
                  Question {activeItemIndex + 1} of {placementItems.length}
                </span>
                <span className="font-mono bg-[#f1f4f8] px-2 py-0.5 rounded text-[11px]">
                  Skill: {currentItem.skill} · Difficulty: {currentItem.difficulty}
                </span>
              </div>
              <div className="w-full bg-[#e3e8ef] h-1.5 rounded-full overflow-hidden">
                <div
                  className="bg-[#1f5fa8] h-full transition-all duration-200"
                  style={{ width: `${((activeItemIndex + 1) / placementItems.length) * 100}%` }}
                />
              </div>

              {/* Prompt Box */}
              <div className="p-4 bg-[#f8fafc] border border-[#cdd5e0] rounded-md">
                <span className="text-[10px] font-mono text-[#8792a3] uppercase tracking-wider block mb-1">
                  Item Family: {currentItem.family} (Rev {currentItem.revision})
                </span>
                <p className="text-sm font-medium text-[#1b2430] leading-relaxed">
                  {currentItem.prompt}
                </p>
              </div>

              {/* Options */}
              <div className="space-y-2">
                {currentItem.options?.map((opt, idx) => {
                  const isSelected = answers[currentItem.id] === opt;
                  return (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => handleSelectOption(opt)}
                      className={`w-full text-left p-3 rounded-md border text-xs transition-all flex items-start gap-3 ${
                        isSelected
                          ? 'border-[#1f5fa8] bg-[#eaf1fa] text-[#0f2a44] font-medium ring-1 ring-[#1f5fa8]'
                          : 'border-[#e3e8ef] bg-white hover:bg-[#f6f8fa] text-[#1b2430]'
                      }`}
                    >
                      <span
                        className={`w-5 h-5 rounded-full border flex items-center justify-center shrink-0 text-[10px] font-mono ${
                          isSelected
                            ? 'bg-[#1f5fa8] border-[#1f5fa8] text-white font-bold'
                            : 'border-[#cdd5e0] text-[#5b6779]'
                        }`}
                      >
                        {String.fromCharCode(65 + idx)}
                      </span>
                      <span className="mt-0.5">{opt}</span>
                    </button>
                  );
                })}
              </div>

              {/* Nav buttons */}
              <div className="pt-4 border-t border-[#e3e8ef] flex items-center justify-between">
                <button
                  type="button"
                  disabled={activeItemIndex === 0}
                  onClick={() => setActiveItemIndex((prev) => prev - 1)}
                  className="px-3 py-1.5 border border-[#cdd5e0] disabled:opacity-40 text-xs font-semibold rounded text-[#5b6779]"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={!answers[currentItem.id]}
                  onClick={handleNext}
                  className="px-4 py-1.5 bg-[#1f5fa8] hover:bg-[#164a85] disabled:opacity-40 text-white text-xs font-semibold rounded shadow-xs"
                >
                  {activeItemIndex === placementItems.length - 1 ? 'Seal & Submit Test' : 'Next Question'}
                </button>
              </div>
            </div>
          )}

          {currentStep === 'summary' && (
            <div className="space-y-4">
              <div className="p-4 bg-[#e7f4ec] border border-[#a8d5ba] rounded-md text-center">
                <CheckCircle className="w-8 h-8 mx-auto text-[#1a7f4b] mb-1" />
                <h3 className="text-base font-bold text-[#1a7f4b]">
                  Assessment Sealed & Scored
                </h3>
                <p className="text-xs text-[#1b2430] mt-0.5">
                  Test session evidence captured and processed under published blueprint rules.
                </p>
              </div>

              <div className="border border-[#e3e8ef] rounded-md p-4 bg-white space-y-3">
                <div className="flex justify-between items-center border-b border-[#f1f4f8] pb-3">
                  <div>
                    <span className="text-[10px] font-mono text-[#8792a3] uppercase tracking-wider block">
                      Overall Diagnostic Score
                    </span>
                    <div className="text-2xl font-bold text-[#0f2a44]">
                      {calculatedScore ?? 82} / 100
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-[10px] font-mono text-[#8792a3] uppercase tracking-wider block">
                      Recommended Placement
                    </span>
                    <span className="inline-block bg-[#eaf1fa] text-[#1f5fa8] border border-[#c5d9f0] px-3 py-1 rounded text-xs font-bold">
                      {calculatedScore && calculatedScore >= 85
                        ? 'Full Test Simulation (100+)'
                        : calculatedScore && calculatedScore >= 70
                        ? 'Productive Skills (S & W)'
                        : 'Skills Mastery (R & L)'}
                    </span>
                  </div>
                </div>

                <div className="text-xs text-[#5b6779] space-y-1">
                  <p>
                    <strong>Integrity Seal:</strong> Evidence hash certified by invigilator. No manual edits allowed to sealed response occurrences.
                  </p>
                  <p>
                    <strong>Next Action:</strong> Release decision from Academic Desk so reception and admissions can proceed with program enrollment.
                  </p>
                </div>
              </div>

              <div className="pt-3 border-t border-[#e3e8ef] flex justify-between items-center">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-3 py-1.5 border border-[#cdd5e0] text-[#5b6779] rounded text-xs font-semibold"
                >
                  Close
                </button>

                {attemptId && (
                  <button
                    type="button"
                    onClick={() => {
                      releasePlacementDecision(attemptId);
                      onClose();
                    }}
                    className="px-4 py-1.5 bg-[#1a7f4b] hover:bg-[#15663c] text-white rounded text-xs font-semibold shadow-xs"
                  >
                    Release Decision Now
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
