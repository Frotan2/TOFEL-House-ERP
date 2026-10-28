import React, { useState } from 'react';
import {
  GraduationCap,
  Calendar,
  Users,
  CheckCircle,
  Clock,
  PlusCircle,
  FileText,
  UserCheck,
  Award,
} from 'lucide-react';
import { useERP } from '../../context/ERPContext';
import { StatusBadge } from '../common/StatusBadge';
import { MetricCard } from '../common/MetricCard';
import { CommandModal, CommandField } from '../common/CommandModal';
import { PlacementPortalModal } from './PlacementPortalModal';

export const AcademicDesk: React.FC = () => {
  const {
    placementAttempts,
    admissionDecisions,
    studentGroups,
    schedules,
    instructors,
    activeBranch,
    decideAdmission,
    releasePlacementDecision,
    scheduleSession,
  } = useERP();

  const [selectedAttemptId, setSelectedAttemptId] = useState<string | null>(null);
  const [isDecideModalOpen, setIsDecideModalOpen] = useState(false);
  const [selectedAdmissionId, setSelectedAdmissionId] = useState<string | null>(null);
  const [isScheduleModalOpen, setIsScheduleModalOpen] = useState(false);

  // Filtered lists
  const filteredAttempts = placementAttempts.filter(
    (a) => activeBranch === 'All Branches' || a.branch === activeBranch
  );

  const pendingDecisions = admissionDecisions.filter(
    (d) =>
      (activeBranch === 'All Branches' || d.branch === activeBranch) &&
      (d.status === 'Review' || d.status === 'Draft')
  );

  const filteredGroups = studentGroups.filter(
    (g) => activeBranch === 'All Branches' || g.branch === activeBranch
  );

  const todayStr = '2026-10-28';
  const todaySchedules = schedules.filter(
    (s) =>
      s.scheduleDate === todayStr &&
      (activeBranch === 'All Branches' || s.branch === activeBranch)
  );

  const decideAdmissionFields: CommandField[] = [
    {
      name: 'outcome',
      label: 'Admission Outcome',
      type: 'select',
      required: true,
      options: ['Approved', 'Conditional', 'Deferred', 'Rejected'],
      defaultValue: 'Approved',
    },
    {
      name: 'reason',
      label: 'Academic Rationale / Notes',
      type: 'textarea',
      required: true,
      placeholder: 'State academic criteria satisfied or reason for outcome…',
    },
    {
      name: 'conditions',
      label: 'Conditions (if Conditional)',
      type: 'textarea',
      placeholder: 'e.g. Provide verified passport scan and sign academic honor code',
    },
  ];

  const scheduleFields: CommandField[] = [
    {
      name: 'studentGroupId',
      label: 'Student Group / Class',
      type: 'select',
      required: true,
      options: filteredGroups.map((g) => g.id),
      defaultValue: filteredGroups[0]?.id || '',
    },
    {
      name: 'courseSkill',
      label: 'Module / Skill Focus',
      type: 'text',
      required: true,
      placeholder: 'e.g. Reading Diagnostic & Skimming Techniques',
    },
    {
      name: 'scheduleDate',
      label: 'Schedule Date',
      type: 'date',
      required: true,
      defaultValue: todayStr,
    },
    {
      name: 'fromTime',
      label: 'From Time',
      type: 'text',
      required: true,
      defaultValue: '10:00',
    },
    {
      name: 'toTime',
      label: 'To Time',
      type: 'text',
      required: true,
      defaultValue: '12:00',
    },
    {
      name: 'room',
      label: 'Assigned Room',
      type: 'text',
      required: true,
      defaultValue: 'Room 201',
    },
    {
      name: 'instructorId',
      label: 'Instructor',
      type: 'select',
      required: true,
      options: instructors.map((i) => `${i.id}: ${i.name}`),
      defaultValue: instructors[0] ? `${instructors[0].id}: ${instructors[0].name}` : '',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="bg-white p-6 rounded-lg border border-[#e3e8ef] shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#1f5fa8] bg-[#eaf1fa] px-2 py-0.5 rounded border border-[#c5d9f0]">
              Audience: Academic Manager
            </span>
            <span className="text-[11px] text-[#5b6779] font-mono">
              toefl_house.desk.academic.work
            </span>
          </div>
          <h1 className="text-xl font-bold text-[#1b2430]">TOEFL House Academic Desk</h1>
          <p className="text-xs text-[#5b6779] mt-0.5 max-w-2xl">
            Placement and admission queues, classes, sessions and teaching assignments that need an academic decision.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setIsScheduleModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-[#1f5fa8] hover:bg-[#164a85] text-white rounded text-xs font-semibold shadow-xs self-start md:self-auto shrink-0"
        >
          <PlusCircle className="w-4 h-4" />
          <span>Schedule Class Session</span>
        </button>
      </div>

      {/* Academic Funnel Tiles */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xs font-bold uppercase tracking-wider text-[#5b6779]">
            Academic Work Queues
          </h2>
          <span className="text-[11px] text-[#8792a3]">
            Separation of duties enforced between assessor, reviewer & releaser
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard
            label="Placement Under Marking"
            value={filteredAttempts.filter((a) => a.status === 'Marking').length}
            definition="Sealed candidate tests awaiting objective scoring and rubric marks."
            source="TH Placement Attempt"
            badge={{ text: 'Marking', tone: 'warn' }}
          />
          <MetricCard
            label="Decisions to Release"
            value={filteredAttempts.filter((a) => a.status === 'Finalized').length}
            definition="Assessed attempts awaiting final Academic Releaser approval."
            source="TH Placement Decision"
            badge={{ text: 'Action', tone: 'info' }}
          />
          <MetricCard
            label="Admissions in Review"
            value={pendingDecisions.length}
            definition="Candidates with released placement waiting for official admission decision."
            source="TH Admission Decision"
            badge={{ text: 'Queue', tone: 'warn' }}
          />
          <MetricCard
            label="Active Cohorts Today"
            value={todaySchedules.length}
            definition="Scheduled instructional sessions running today across institute branches."
            source="Course Schedule"
            badge={{ text: 'Live', tone: 'ok' }}
          />
        </div>
      </section>

      {/* Placement Testing Queue */}
      <section className="bg-white rounded-lg border border-[#e3e8ef] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#f1f4f8] flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-[#1b2430]">
              Diagnostic Placement Queue
            </h2>
            <p className="text-xs text-[#5b6779] mt-0.5">
              Supervised candidate sessions, sealed test evidence, and recommended course mappings.
            </p>
          </div>
          <span className="text-xs font-mono text-[#5b6779]">
            {filteredAttempts.length} attempt(s)
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#f8fafc] text-[#5b6779] uppercase font-semibold text-[10px] tracking-wider border-b border-[#e3e8ef]">
              <tr>
                <th className="px-4 py-3">Attempt ID / Case</th>
                <th className="px-4 py-3">Candidate</th>
                <th className="px-4 py-3">Blueprint</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Score & Recommendation</th>
                <th className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f1f4f8]">
              {filteredAttempts.map((attempt) => (
                <tr key={attempt.id} className="hover:bg-[#f8fafc] transition-colors">
                  <td className="px-4 py-3 font-mono">
                    <span className="font-bold text-[#1b2430]">{attempt.id}</span>
                    <div className="text-[10px] text-[#8792a3]">{attempt.caseId}</div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-bold text-[#1b2430]">{attempt.candidateName}</div>
                    <div className="text-[11px] text-[#5b6779]">{attempt.candidateEmail}</div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-semibold text-[#1b2430]">{attempt.blueprint}</div>
                    <div className="text-[10px] text-[#8792a3]">Scheduled: {attempt.scheduledTime}</div>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={attempt.status} />
                  </td>
                  <td className="px-4 py-3">
                    {attempt.score !== undefined ? (
                      <div>
                        <div className="font-bold text-[#0f2a44]">{attempt.score} / {attempt.maxScore}</div>
                        <div className="text-[11px] text-[#1f5fa8] font-semibold">{attempt.recommendedLevel}</div>
                      </div>
                    ) : (
                      <span className="text-[#8792a3] italic">Not scored yet</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {attempt.status === 'Allocated' && (
                      <button
                        type="button"
                        onClick={() => setSelectedAttemptId(attempt.id)}
                        className="px-2.5 py-1 bg-[#1f5fa8] hover:bg-[#164a85] text-white rounded text-[11px] font-semibold"
                      >
                        Deliver / Test
                      </button>
                    )}
                    {attempt.status === 'Marking' && (
                      <button
                        type="button"
                        onClick={() => setSelectedAttemptId(attempt.id)}
                        className="px-2.5 py-1 bg-[#9a6700] hover:bg-[#7a5200] text-white rounded text-[11px] font-semibold"
                      >
                        Score & Seal
                      </button>
                    )}
                    {attempt.status === 'Finalized' && (
                      <button
                        type="button"
                        onClick={() => releasePlacementDecision(attempt.id)}
                        className="px-2.5 py-1 bg-[#1a7f4b] hover:bg-[#15663c] text-white rounded text-[11px] font-semibold"
                      >
                        Release Decision
                      </button>
                    )}
                    {attempt.status === 'Released' && (
                      <span className="text-[#1a7f4b] text-[11px] font-semibold">
                        Released · Valid
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Admission Decision Queue */}
      <section className="bg-white rounded-lg border border-[#e3e8ef] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#f1f4f8] flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-[#1b2430]">
              Admission Review & Approvals Queue
            </h2>
            <p className="text-xs text-[#5b6779] mt-0.5">
              Decide admission outcomes over native Student Applicant authority.
            </p>
          </div>
          <span className="text-xs font-mono text-[#5b6779]">
            {pendingDecisions.length} awaiting action
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#f8fafc] text-[#5b6779] uppercase font-semibold text-[10px] tracking-wider border-b border-[#e3e8ef]">
              <tr>
                <th className="px-4 py-3">Decision ID</th>
                <th className="px-4 py-3">Applicant Name</th>
                <th className="px-4 py-3">Target Program</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Academic Note</th>
                <th className="px-4 py-3 text-right">Academic Decision</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f1f4f8]">
              {pendingDecisions.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-[#8792a3]">
                    No admission decisions awaiting academic review.
                  </td>
                </tr>
              ) : (
                pendingDecisions.map((dec) => (
                  <tr key={dec.id} className="hover:bg-[#f8fafc] transition-colors">
                    <td className="px-4 py-3 font-mono font-semibold text-[#1b2430]">
                      {dec.id}
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-bold text-[#1b2430]">{dec.applicantName}</div>
                      <div className="text-[11px] text-[#5b6779]">{dec.applicantEmail}</div>
                    </td>
                    <td className="px-4 py-3 font-semibold text-[#1b2430]">
                      {dec.programCode} ({dec.branch})
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={dec.status} />
                    </td>
                    <td className="px-4 py-3 text-[11px] text-[#5b6779] max-w-xs">
                      {dec.reason || 'Placement recommendation verified.'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedAdmissionId(dec.id);
                          setIsDecideModalOpen(true);
                        }}
                        className="px-3 py-1 bg-[#1f5fa8] hover:bg-[#164a85] text-white rounded text-[11px] font-semibold"
                      >
                        Decide Outcome
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Classes & Sessions Today */}
      <section className="bg-white rounded-lg border border-[#e3e8ef] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#f1f4f8] flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-[#1b2430]">
              Classes & Sessions Today ({todayStr})
            </h2>
            <p className="text-xs text-[#5b6779] mt-0.5">
              Native Course Schedule and Student Group capacity facts.
            </p>
          </div>
          <span className="text-xs text-[#5b6779]">
            {todaySchedules.length} session(s) scheduled
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#f8fafc] text-[#5b6779] uppercase font-semibold text-[10px] tracking-wider border-b border-[#e3e8ef]">
              <tr>
                <th className="px-4 py-3">Class Cohort</th>
                <th className="px-4 py-3">Time & Room</th>
                <th className="px-4 py-3">Instructor</th>
                <th className="px-4 py-3">Skill / Focus</th>
                <th className="px-4 py-3">Roster Capacity</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f1f4f8]">
              {todaySchedules.map((sch) => {
                const group = studentGroups.find((g) => g.id === sch.studentGroupId);
                return (
                  <tr key={sch.id} className="hover:bg-[#f8fafc] transition-colors">
                    <td className="px-4 py-3 font-semibold text-[#1b2430]">
                      {sch.studentGroupName}
                    </td>
                    <td className="px-4 py-3 font-mono">
                      <div>{sch.fromTime} – {sch.toTime}</div>
                      <div className="text-[10px] text-[#8792a3]">{sch.room}</div>
                    </td>
                    <td className="px-4 py-3 font-medium text-[#1b2430]">
                      {sch.instructorName}
                    </td>
                    <td className="px-4 py-3 text-[#5b6779]">
                      {sch.courseSkill}
                    </td>
                    <td className="px-4 py-3 font-mono">
                      {group ? (
                        <div>
                          <span className="font-bold text-[#0f2a44]">
                            {group.currentStrength} / {group.maxStrength}
                          </span>
                          <span className="text-[10px] text-[#8792a3] ml-1">
                            ({group.maxStrength - group.currentStrength} open seats)
                          </span>
                        </div>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={sch.status} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Decide Admission Modal */}
      {selectedAdmissionId && (
        <CommandModal
          isOpen={isDecideModalOpen}
          onClose={() => {
            setIsDecideModalOpen(false);
            setSelectedAdmissionId(null);
          }}
          title="Decide Admission"
          description="Approves, rejects, or adds conditions to the admission offer."
          actingRole="Admission Approver"
          methodName="toefl_house.admission.decide_admission"
          fields={decideAdmissionFields}
          onSubmit={(values) => {
            decideAdmission(selectedAdmissionId, values.outcome, values.reason, values.conditions);
            return {
              status: 'success',
              message: `Recorded outcome "${values.outcome}" for admission decision`,
              payload: {
                decision_id: selectedAdmissionId,
                outcome: values.outcome,
                reason: values.reason,
                conditions: values.conditions || 'None',
              },
            };
          }}
        />
      )}

      {/* Schedule Session Modal */}
      <CommandModal
        isOpen={isScheduleModalOpen}
        onClose={() => setIsScheduleModalOpen(false)}
        title="Schedule Class Session"
        description="Creates an authoritative native Course Schedule entry."
        actingRole="Teaching Scheduler"
        methodName="toefl_house.teaching.schedule_session"
        fields={scheduleFields}
        onSubmit={(values) => {
          const grp = studentGroups.find((g) => g.id === values.studentGroupId);
          const insSplit = values.instructorId.split(':');
          const insId = insSplit[0].trim();
          const insName = insSplit[1]?.trim() || 'Instructor';

          const newId = scheduleSession({
            studentGroupId: values.studentGroupId,
            studentGroupName: grp?.groupName || values.studentGroupId,
            programCode: grp?.programCode || 'TOEFL-PREP',
            courseSkill: values.courseSkill,
            scheduleDate: values.scheduleDate,
            fromTime: values.fromTime,
            toTime: values.toTime,
            room: values.room,
            instructorId: insId,
            instructorName: insName,
            branch: grp?.branch || 'Kabul Central',
          });

          return {
            status: 'success',
            message: `Scheduled session ${newId} for ${grp?.groupName}`,
            payload: {
              schedule_id: newId,
              class: grp?.groupName,
              date: values.scheduleDate,
              time: `${values.fromTime}-${values.toTime}`,
              instructor: insName,
            },
          };
        }}
      />

      {/* Interactive Placement Test Modal */}
      {selectedAttemptId && (
        <PlacementPortalModal
          isOpen={Boolean(selectedAttemptId)}
          onClose={() => setSelectedAttemptId(null)}
          attemptId={selectedAttemptId}
        />
      )}
    </div>
  );
};
