import React, { useState } from 'react';
import {
  Terminal,
  FileCode,
  Send,
  UserCheck,
  CheckCircle,
  PlayCircle,
  BookOpen,
  Calendar,
  CreditCard,
  FileText,
} from 'lucide-react';
import { useERP } from '../../context/ERPContext';
import { CommandModal, CommandField } from '../common/CommandModal';

interface CommandCategory {
  id: string;
  title: string;
  role: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
  commands: {
    label: string;
    method: string;
    fields: CommandField[];
    handler: (values: Record<string, any>) => { status: 'success' | 'warning' | 'error'; message: string; payload?: Record<string, any> };
  }[];
}

export const CommandCenter: React.FC = () => {
  const {
    applicants,
    placementAttempts,
    admissionDecisions,
    studentGroups,
    schedules,
    recordApplicant,
    createPlacementCase,
    createAdmissionDecision,
    decideAdmission,
    convertApplicantToStudent,
    createStudentGroup,
    scheduleSession,
    postponeSession,
    cancelSession,
    addGroupMember,
  } = useERP();

  const [activeModalCommand, setActiveModalCommand] = useState<{
    title: string;
    description: string;
    role: string;
    method: string;
    fields: CommandField[];
    handler: (values: Record<string, any>) => any;
  } | null>(null);

  const commandCategories: CommandCategory[] = [
    {
      id: 'placement-author',
      title: 'Placement Authoring & Blueprints',
      role: 'Placement Author',
      icon: FileCode,
      description: 'Create and revise synthetic item definitions and testing blueprints.',
      commands: [
        {
          label: 'Create Placement Item Draft',
          method: 'toefl_house.api.create_draft',
          fields: [
            { name: 'family', label: 'Item Family Code', type: 'text', required: true, defaultValue: 'FAM-TOEFL-R05' },
            { name: 'skill', label: 'Language Skill', type: 'select', required: true, options: ['Reading', 'Listening', 'Grammar', 'Vocabulary', 'Speaking', 'Writing'], defaultValue: 'Reading' },
            { name: 'difficulty', label: 'Difficulty Tier', type: 'select', required: true, options: ['A2', 'B1', 'B2', 'C1'], defaultValue: 'B2' },
            { name: 'prompt', label: 'Question Prompt', type: 'textarea', required: true, placeholder: 'Enter prompt text…' },
          ],
          handler: (values) => ({
            status: 'success',
            message: `Created draft item ${values.family} with skill ${values.skill}`,
            payload: { family: values.family, skill: values.skill, difficulty: values.difficulty, status: 'Draft' },
          }),
        },
      ],
    },
    {
      id: 'placement-delivery',
      title: 'Placement Allocation & Case Management',
      role: 'Placement Publisher',
      icon: PlayCircle,
      description: 'Allocate test blueprints and register candidate placement attempts.',
      commands: [
        {
          label: 'Allocate Placement Attempt',
          method: 'toefl_house.api.allocate_attempt',
          fields: [
            { name: 'applicantId', label: 'Applicant', type: 'select', required: true, options: applicants.map((a) => a.id), defaultValue: applicants[0]?.id || '' },
            { name: 'blueprint', label: 'Testing Blueprint', type: 'select', required: true, options: ['BP-TOEFL-STD-2026', 'BP-GENENG-2026', 'BP-IELTS-ACAD-2026'], defaultValue: 'BP-TOEFL-STD-2026' },
          ],
          handler: (values) => {
            const attId = createPlacementCase(values.applicantId, values.blueprint);
            return {
              status: 'success',
              message: `Allocated attempt ${attId} for applicant ${values.applicantId}`,
              payload: { attempt_id: attId, blueprint: values.blueprint, status: 'Allocated' },
            };
          },
        },
      ],
    },
    {
      id: 'admission-actions',
      title: 'Admission Intake & Conversions',
      role: 'Admission Officer & Approver',
      icon: UserCheck,
      description: 'Process admission reviews, approve offers, and convert candidates to native Students.',
      commands: [
        {
          label: 'Record New Applicant',
          method: 'toefl_house.admission.record_applicant',
          fields: [
            { name: 'name', label: 'Full Name', type: 'text', required: true },
            { name: 'email', label: 'Email', type: 'text', required: true },
            { name: 'phone', label: 'Phone', type: 'text', required: true },
            { name: 'programCode', label: 'Program', type: 'select', required: true, options: ['TOEFL-PREP', 'GEN-ENG', 'IELTS-ACAD', 'BUS-ENG'], defaultValue: 'TOEFL-PREP' },
            { name: 'branch', label: 'Branch', type: 'select', required: true, options: ['Kabul Central', 'West Campus', 'Online'], defaultValue: 'Kabul Central' },
          ],
          handler: (values) => {
            const id = recordApplicant(values as any);
            return {
              status: 'success',
              message: `Applicant registered with ID ${id}`,
              payload: { applicant_id: id, name: values.name, program: values.programCode },
            };
          },
        },
        {
          label: 'Create Admission Decision',
          method: 'toefl_house.admission.create_admission',
          fields: [
            { name: 'applicantId', label: 'Applicant ID', type: 'select', required: true, options: applicants.map((a) => a.id), defaultValue: applicants[0]?.id || '' },
            { name: 'programCode', label: 'Target Program', type: 'select', required: true, options: ['TOEFL-PREP', 'GEN-ENG', 'IELTS-ACAD', 'BUS-ENG'], defaultValue: 'TOEFL-PREP' },
          ],
          handler: (values) => {
            const decId = createAdmissionDecision(values.applicantId, 'PLC-DEC-091', values.programCode);
            return {
              status: 'success',
              message: `Created admission decision ${decId} in Review stage`,
              payload: { decision_id: decId, status: 'Review' },
            };
          },
        },
      ],
    },
    {
      id: 'teaching-scheduling',
      title: 'Teaching Scheduling & Rosters',
      role: 'Teaching Scheduler',
      icon: Calendar,
      description: 'Create cohorts, manage student rosters, and schedule timetable sessions.',
      commands: [
        {
          label: 'Create Student Group (Class Cohort)',
          method: 'toefl_house.teaching.create_student_group',
          fields: [
            { name: 'groupName', label: 'Class Group Name', type: 'text', required: true, defaultValue: 'TOEFL Morning Cohort B' },
            { name: 'programCode', label: 'Program', type: 'select', required: true, options: ['TOEFL-PREP', 'GEN-ENG', 'IELTS-ACAD', 'BUS-ENG'], defaultValue: 'TOEFL-PREP' },
            { name: 'maxStrength', label: 'Maximum Capacity (Seats)', type: 'number', required: true, defaultValue: 16 },
            { name: 'deliveryMode', label: 'Delivery Mode', type: 'select', required: true, options: ['On-site', 'Online', 'Hybrid'], defaultValue: 'On-site' },
            { name: 'branch', label: 'Branch', type: 'select', required: true, options: ['Kabul Central', 'West Campus', 'Online'], defaultValue: 'Kabul Central' },
          ],
          handler: (values) => {
            const id = createStudentGroup(values);
            return {
              status: 'success',
              message: `Created Student Group ${id} (${values.groupName})`,
              payload: { group_id: id, max_strength: values.maxStrength, delivery_mode: values.deliveryMode },
            };
          },
        },
        {
          label: 'Add Member to Class Roster',
          method: 'toefl_house.teaching.add_class_member',
          fields: [
            { name: 'groupId', label: 'Class Group', type: 'select', required: true, options: studentGroups.map((g) => g.id), defaultValue: studentGroups[0]?.id || '' },
            { name: 'studentId', label: 'Student ID', type: 'text', required: true, defaultValue: 'STU-2026-004' },
          ],
          handler: (values) => {
            const res = addGroupMember(values.groupId, values.studentId);
            return {
              status: res.success ? 'success' : 'warning',
              message: res.message,
              payload: { group: values.groupId, student: values.studentId },
            };
          },
        },
        {
          label: 'Postpone Session',
          method: 'toefl_house.teaching.scheduling.postpone_session',
          fields: [
            { name: 'scheduleId', label: 'Course Schedule', type: 'select', required: true, options: schedules.map((s) => s.id), defaultValue: schedules[0]?.id || '' },
            { name: 'newDate', label: 'Rescheduled Date', type: 'date', required: true, defaultValue: '2026-10-30' },
            { name: 'reason', label: 'Postponement Reason', type: 'textarea', required: true, defaultValue: 'Instructor attendance at academic conference.' },
          ],
          handler: (values) => {
            postponeSession(values.scheduleId, values.newDate, values.reason);
            return {
              status: 'success',
              message: `Session ${values.scheduleId} rescheduled to ${values.newDate}`,
              payload: { schedule: values.scheduleId, new_date: values.newDate, reason: values.reason },
            };
          },
        },
      ],
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white p-6 rounded-lg border border-[#e3e8ef] shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#1f5fa8] bg-[#eaf1fa] px-2 py-0.5 rounded border border-[#c5d9f0]">
              Cross-Role Execution Surface
            </span>
            <span className="text-[11px] text-[#5b6779] font-mono">
              toefl_house.command_pages
            </span>
          </div>
          <h1 className="text-xl font-bold text-[#1b2430]">TOEFL House Command Centre</h1>
          <p className="text-xs text-[#5b6779] mt-0.5 max-w-2xl">
            Choose the role-specific command page for a role assigned to this account. Each command executes through guarded server-side validation with an idempotent request key.
          </p>
        </div>
      </div>

      {/* Command Categories */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {commandCategories.map((cat) => {
          const Icon = cat.icon;
          return (
            <div key={cat.id} className="bg-white p-5 rounded-lg border border-[#e3e8ef] shadow-xs flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="p-1.5 bg-[#eaf1fa] text-[#1f5fa8] rounded">
                      <Icon className="w-4 h-4" />
                    </div>
                    <h2 className="text-sm font-bold text-[#1b2430]">{cat.title}</h2>
                  </div>
                  <span className="text-[10px] font-bold uppercase text-[#5b6779] bg-[#f1f4f8] px-2 py-0.5 rounded">
                    {cat.role}
                  </span>
                </div>
                <p className="text-xs text-[#5b6779] mb-4">{cat.description}</p>
              </div>

              <div className="space-y-2 pt-2 border-t border-[#f1f4f8]">
                {cat.commands.map((cmd) => (
                  <button
                    key={cmd.label}
                    type="button"
                    onClick={() =>
                      setActiveModalCommand({
                        title: cmd.label,
                        description: `Role Authority: ${cat.role}`,
                        role: cat.role,
                        method: cmd.method,
                        fields: cmd.fields,
                        handler: cmd.handler,
                      })
                    }
                    className="w-full flex items-center justify-between p-2.5 rounded border border-[#e3e8ef] hover:border-[#1f5fa8] hover:bg-[#f8fafc] text-xs font-semibold text-[#1b2430] transition-all group"
                  >
                    <span>{cmd.label}</span>
                    <span className="text-[10px] font-mono text-[#8792a3] group-hover:text-[#1f5fa8]">
                      Run →
                    </span>
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Modal Dialog */}
      {activeModalCommand && (
        <CommandModal
          isOpen={Boolean(activeModalCommand)}
          onClose={() => setActiveModalCommand(null)}
          title={activeModalCommand.title}
          description={activeModalCommand.description}
          actingRole={activeModalCommand.role}
          methodName={activeModalCommand.method}
          fields={activeModalCommand.fields}
          onSubmit={activeModalCommand.handler}
        />
      )}
    </div>
  );
};
