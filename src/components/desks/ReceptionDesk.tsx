import React, { useState } from 'react';
import {
  Search,
  UserPlus,
  PlayCircle,
  FileCheck,
  CheckCircle2,
  ArrowRight,
  UserCheck,
} from 'lucide-react';
import { useERP } from '../../context/ERPContext';
import { StatusBadge } from '../common/StatusBadge';
import { MetricCard } from '../common/MetricCard';
import { CommandModal, CommandField } from '../common/CommandModal';
import { PlacementPortalModal } from './PlacementPortalModal';
import { Branch } from '../../types';

export const ReceptionDesk: React.FC = () => {
  const {
    applicants,
    placementAttempts,
    admissionDecisions,
    students,
    activeBranch,
    recordApplicant,
    createPlacementCase,
    createAdmissionDecision,
    acceptOffer,
    convertApplicantToStudent,
  } = useERP();

  const [searchQuery, setSearchQuery] = useState('');
  const [isRecordApplicantOpen, setIsRecordApplicantOpen] = useState(false);
  const [selectedPlacementApplicantId, setSelectedPlacementApplicantId] = useState<string | null>(null);

  // Filter by branch if active
  const filteredApplicants = applicants.filter((a) => {
    if (activeBranch !== 'All Branches' && a.branch !== activeBranch) return false;
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      a.name.toLowerCase().includes(q) ||
      a.email.toLowerCase().includes(q) ||
      a.phone.toLowerCase().includes(q) ||
      a.id.toLowerCase().includes(q)
    );
  });

  // Funnel calculations
  const totalRegistered = applicants.length;
  const totalScheduled = applicants.filter((a) => a.applicationStatus === 'Placement Scheduled').length;
  const totalTested = applicants.filter(
    (a) => a.applicationStatus === 'Tested' || a.applicationStatus === 'Admitted' || a.applicationStatus === 'Enrolled'
  ).length;
  const totalAdmitted = applicants.filter(
    (a) => a.applicationStatus === 'Admitted' || a.applicationStatus === 'Enrolled'
  ).length;
  const totalEnrolled = applicants.filter((a) => a.applicationStatus === 'Enrolled').length;

  const applicantFields: CommandField[] = [
    { name: 'name', label: 'Candidate Full Name', type: 'text', required: true, placeholder: 'e.g. Ahmad Fawad' },
    { name: 'email', label: 'Email Address', type: 'text', required: true, placeholder: 'e.g. ahmad.fawad@example.com' },
    { name: 'phone', label: 'Phone Number', type: 'text', required: true, placeholder: 'e.g. +93 78 123 4567' },
    {
      name: 'programCode',
      label: 'Target Program',
      type: 'select',
      required: true,
      options: ['TOEFL-PREP', 'GEN-ENG', 'IELTS-ACAD', 'BUS-ENG'],
      defaultValue: 'TOEFL-PREP',
    },
    {
      name: 'branch',
      label: 'Intake Branch',
      type: 'select',
      required: true,
      options: ['Kabul Central', 'West Campus', 'Online'],
      defaultValue: activeBranch !== 'All Branches' ? activeBranch : 'Kabul Central',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="bg-white p-6 rounded-lg border border-[#e3e8ef] shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#1f5fa8] bg-[#eaf1fa] px-2 py-0.5 rounded border border-[#c5d9f0]">
              Audience: Reception Staff
            </span>
            <span className="text-[11px] text-[#5b6779] font-mono">
              toefl_house.desk.reception.work
            </span>
          </div>
          <h1 className="text-xl font-bold text-[#1b2430]">TOEFL House Reception Desk</h1>
          <p className="text-xs text-[#5b6779] mt-0.5 max-w-2xl">
            Find any person in the admission funnel and see the stage, what is missing and who acts next.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setIsRecordApplicantOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-[#1f5fa8] hover:bg-[#164a85] text-white rounded text-xs font-semibold shadow-xs transition-colors self-start md:self-auto shrink-0"
        >
          <UserPlus className="w-4 h-4" />
          <span>Record New Applicant</span>
        </button>
      </div>

      {/* Applicant Funnel Tiles */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xs font-bold uppercase tracking-wider text-[#5b6779]">
            Applicant Intake Funnel
          </h2>
          <span className="text-[11px] text-[#8792a3]">
            Definitions anchored to native applicant & decision records
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <MetricCard
            label="1. Registered"
            value={totalRegistered}
            definition="Total candidates entered into intake with contact and target program recorded."
            source="Student Applicant"
          />
          <MetricCard
            label="2. Placement Queued"
            value={totalScheduled}
            definition="Assigned to a synthetic placement assessment blueprint session."
            source="TH Placement Attempt"
          />
          <MetricCard
            label="3. Tested & Scored"
            value={totalTested}
            definition="Sealed responses scored and level recommendation generated."
            source="TH Placement Decision"
          />
          <MetricCard
            label="4. Admitted"
            value={totalAdmitted}
            definition="Official admission offer extended; waiting for offer acceptance."
            source="TH Admission Decision"
          />
          <MetricCard
            label="5. Enrolled"
            value={totalEnrolled}
            definition="Converted to native Student record with active Program Enrollment."
            source="Program Enrollment"
            badge={{ text: 'Target', tone: 'ok' }}
          />
        </div>
      </section>

      {/* Person Search / Finder */}
      <section className="bg-white p-4 rounded-lg border border-[#e3e8ef] shadow-xs space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Search className="w-4 h-4 text-[#1f5fa8]" />
            <h2 className="text-sm font-bold text-[#1b2430]">
              Find a Person (Front-Desk Lookup)
            </h2>
          </div>
          <span className="text-[11px] text-[#8792a3]">
            Bounded query matches name, phone, or email
          </span>
        </div>

        <div className="relative">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Type name, email or phone of the person in front of you…"
            className="w-full pl-9 pr-4 py-2 border border-[#cdd5e0] rounded-md text-xs focus:outline-none focus:border-[#1f5fa8] bg-[#f8fafc]"
          />
          <Search className="w-4 h-4 text-[#8792a3] absolute left-3 top-2.5" />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-3 top-2 text-xs text-[#8792a3] hover:text-[#1b2430]"
            >
              Clear
            </button>
          )}
        </div>
      </section>

      {/* People in the Funnel Table */}
      <section className="bg-white rounded-lg border border-[#e3e8ef] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#f1f4f8] flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-[#1b2430]">People in the Funnel</h2>
            <p className="text-xs text-[#5b6779] mt-0.5">
              Active journey stages, pending actions, and role pre-fills for front desk staff.
            </p>
          </div>
          <span className="text-xs font-mono text-[#5b6779]">
            {filteredApplicants.length} candidate(s)
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#f8fafc] text-[#5b6779] uppercase font-semibold text-[10px] tracking-wider border-b border-[#e3e8ef]">
              <tr>
                <th className="px-4 py-3">Applicant / Contact</th>
                <th className="px-4 py-3">Program & Branch</th>
                <th className="px-4 py-3">Current Status</th>
                <th className="px-4 py-3">Diagnostic Placement</th>
                <th className="px-4 py-3">Next Action & Owner</th>
                <th className="px-4 py-3 text-right">Guided Command</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f1f4f8]">
              {filteredApplicants.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-[#8792a3]">
                    No applicant records found matching search filters.
                  </td>
                </tr>
              ) : (
                filteredApplicants.map((app) => {
                  const admission = admissionDecisions.find((d) => d.applicantId === app.id);
                  const attempt = placementAttempts.find((a) => a.candidateEmail === app.email);

                  return (
                    <tr key={app.id} className="hover:bg-[#f8fafc] transition-colors">
                      <td className="px-4 py-3">
                        <div className="font-bold text-[#1b2430]">{app.name}</div>
                        <div className="text-[11px] text-[#5b6779]">{app.email}</div>
                        <div className="text-[10px] text-[#8792a3]">{app.phone}</div>
                      </td>

                      <td className="px-4 py-3">
                        <div className="font-semibold text-[#1b2430]">{app.programCode}</div>
                        <div className="text-[11px] text-[#5b6779]">{app.branch}</div>
                        <div className="text-[10px] text-[#8792a3]">Registered {app.creationDate}</div>
                      </td>

                      <td className="px-4 py-3">
                        <StatusBadge status={app.applicationStatus} />
                        {admission && (
                          <div className="mt-1">
                            <span className="text-[10px] text-[#5b6779]">
                              Admission: {admission.status}
                            </span>
                          </div>
                        )}
                      </td>

                      <td className="px-4 py-3">
                        {attempt ? (
                          <div>
                            <div className="flex items-center gap-1.5">
                              <span className="font-mono text-xs font-bold text-[#0f2a44]">
                                {attempt.score !== undefined ? `${attempt.score}/100` : 'Pending'}
                              </span>
                              <StatusBadge status={attempt.status} className="scale-85 origin-left" />
                            </div>
                            <div className="text-[10px] text-[#5b6779] mt-0.5 truncate max-w-[150px]">
                              {attempt.recommendedLevel}
                            </div>
                          </div>
                        ) : (
                          <span className="text-[11px] text-[#8792a3]">No attempt scheduled</span>
                        )}
                      </td>

                      <td className="px-4 py-3">
                        {app.applicationStatus === 'Registered' && (
                          <div>
                            <span className="font-semibold text-[#1f5fa8]">Schedule Placement</span>
                            <div className="text-[10px] text-[#8792a3]">Owned by: Reception Staff</div>
                          </div>
                        )}
                        {app.applicationStatus === 'Placement Scheduled' && (
                          <div>
                            <span className="font-semibold text-[#9a6700]">Deliver Assessment</span>
                            <div className="text-[10px] text-[#8792a3]">Owned by: Invigilator</div>
                          </div>
                        )}
                        {app.applicationStatus === 'Tested' && !admission && (
                          <div>
                            <span className="font-semibold text-[#1f5fa8]">Create Admission Decision</span>
                            <div className="text-[10px] text-[#8792a3]">Owned by: Admission Officer</div>
                          </div>
                        )}
                        {admission && admission.status === 'Review' && (
                          <div>
                            <span className="font-semibold text-[#9a6700]">Review & Decide Offer</span>
                            <div className="text-[10px] text-[#8792a3]">Owned by: Academic Approver</div>
                          </div>
                        )}
                        {admission && admission.status === 'Approved' && !admission.offerAccepted && (
                          <div>
                            <span className="font-semibold text-[#1a7f4b]">Accept Offer</span>
                            <div className="text-[10px] text-[#8792a3]">Owned by: Candidate / Reception</div>
                          </div>
                        )}
                        {admission && admission.status === 'Approved' && admission.offerAccepted && (
                          <div>
                            <span className="font-semibold text-[#1a7f4b]">Convert to Student</span>
                            <div className="text-[10px] text-[#8792a3]">Owned by: Admission Approver</div>
                          </div>
                        )}
                        {app.applicationStatus === 'Enrolled' && (
                          <div className="text-[#1a7f4b] flex items-center gap-1 font-semibold">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            <span>Enrolled in Cohort</span>
                          </div>
                        )}
                      </td>

                      <td className="px-4 py-3 text-right">
                        {app.applicationStatus === 'Registered' && (
                          <button
                            type="button"
                            onClick={() => createPlacementCase(app.id)}
                            className="px-2.5 py-1 bg-[#1f5fa8] hover:bg-[#164a85] text-white rounded text-[11px] font-semibold"
                          >
                            Allocate Placement
                          </button>
                        )}

                        {app.applicationStatus === 'Placement Scheduled' && (
                          <button
                            type="button"
                            onClick={() => setSelectedPlacementApplicantId(app.id)}
                            className="px-2.5 py-1 bg-[#0f2a44] hover:bg-[#1f5fa8] text-white rounded text-[11px] font-semibold inline-flex items-center gap-1"
                          >
                            <PlayCircle className="w-3 h-3" />
                            <span>Run Test</span>
                          </button>
                        )}

                        {app.applicationStatus === 'Tested' && !admission && (
                          <button
                            type="button"
                            onClick={() =>
                              createAdmissionDecision(app.id, app.placementDecisionId || '', app.programCode)
                            }
                            className="px-2.5 py-1 bg-[#1f5fa8] hover:bg-[#164a85] text-white rounded text-[11px] font-semibold"
                          >
                            Create Admission
                          </button>
                        )}

                        {admission && admission.status === 'Approved' && !admission.offerAccepted && (
                          <button
                            type="button"
                            onClick={() => acceptOffer(admission.id)}
                            className="px-2.5 py-1 bg-[#1a7f4b] hover:bg-[#15663c] text-white rounded text-[11px] font-semibold"
                          >
                            Accept Offer
                          </button>
                        )}

                        {admission && admission.status === 'Approved' && admission.offerAccepted && (
                          <button
                            type="button"
                            onClick={() => convertApplicantToStudent(admission.id)}
                            className="px-2.5 py-1 bg-[#1f5fa8] hover:bg-[#164a85] text-white rounded text-[11px] font-semibold"
                          >
                            Convert to Student
                          </button>
                        )}

                        {app.applicationStatus === 'Enrolled' && (
                          <span className="text-[11px] font-mono text-[#5b6779]">
                            {students.find((s) => s.email === app.email)?.id || 'Enrolled'}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Record Applicant Command Modal */}
      <CommandModal
        isOpen={isRecordApplicantOpen}
        onClose={() => setIsRecordApplicantOpen(false)}
        title="Record New Applicant"
        description="Records applicant details and target program. Does not create an enrollment or billing row."
        actingRole="Reception Staff"
        methodName="toefl_house.admission.record_applicant"
        fields={applicantFields}
        onSubmit={(values) => {
          const newId = recordApplicant({
            name: values.name,
            email: values.email,
            phone: values.phone,
            programCode: values.programCode,
            branch: values.branch,
          });
          return {
            status: 'success',
            message: `Recorded applicant ${values.name} with ID ${newId}`,
            payload: {
              applicant_id: newId,
              name: values.name,
              program: values.programCode,
              branch: values.branch,
              status: 'Registered',
            },
          };
        }}
      />

      {/* Placement Test Delivery Modal */}
      {selectedPlacementApplicantId && (
        <PlacementPortalModal
          isOpen={Boolean(selectedPlacementApplicantId)}
          onClose={() => setSelectedPlacementApplicantId(null)}
          applicantId={selectedPlacementApplicantId}
        />
      )}
    </div>
  );
};
