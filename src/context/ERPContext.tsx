import React, { createContext, useContext, useState, useEffect } from 'react';
import {
  InstituteRole,
  Branch,
  DeskSlug,
  AcademicProgram,
  ProgramLevel,
  LevelDurationPolicy,
  StudentApplicant,
  PlacementItem,
  PlacementAttempt,
  PlacementDecision,
  AdmissionDecision,
  Student,
  ProgramEnrollment,
  StudentGroup,
  CourseSchedule,
  AttendanceRecord,
  AttendanceCorrectionRequest,
  SalesInvoice,
  PaymentEntry,
  CashierDay,
  BookItem,
  CorrectionRequest,
  Instructor,
  ConfigurationAuditEvent,
  PolicyDomain,
} from '../types';
import {
  initialPrograms,
  initialLevels,
  initialDurationPolicies,
  initialApplicants,
  initialPlacementItems,
  initialPlacementAttempts,
  initialPlacementDecisions,
  initialAdmissionDecisions,
  initialStudents,
  initialEnrollments,
  initialStudentGroups,
  initialSchedules,
  initialAttendanceRecords,
  initialAttendanceCorrections,
  initialInvoices,
  initialPayments,
  initialCashierDay,
  initialBooks,
  initialCorrectionRequests,
  initialInstructors,
  initialAuditEvents,
  initialPolicyDomains,
} from '../data/initialData';

interface ERPContextType {
  activeRole: InstituteRole;
  setActiveRole: (role: InstituteRole) => void;
  activeBranch: Branch | 'All Branches';
  setActiveBranch: (branch: Branch | 'All Branches') => void;
  activeDesk: DeskSlug;
  setActiveDesk: (desk: DeskSlug) => void;
  activeInstructorId: string;
  setActiveInstructorId: (id: string) => void;

  // Data Collections
  programs: AcademicProgram[];
  levels: ProgramLevel[];
  durationPolicies: LevelDurationPolicy[];
  applicants: StudentApplicant[];
  placementItems: PlacementItem[];
  placementAttempts: PlacementAttempt[];
  placementDecisions: PlacementDecision[];
  admissionDecisions: AdmissionDecision[];
  students: Student[];
  enrollments: ProgramEnrollment[];
  studentGroups: StudentGroup[];
  schedules: CourseSchedule[];
  attendanceRecords: AttendanceRecord[];
  attendanceCorrections: AttendanceCorrectionRequest[];
  invoices: SalesInvoice[];
  payments: PaymentEntry[];
  cashierDay: CashierDay;
  books: BookItem[];
  correctionRequests: CorrectionRequest[];
  instructors: Instructor[];
  auditEvents: ConfigurationAuditEvent[];
  policyDomains: PolicyDomain[];

  // Actions
  recordApplicant: (data: { name: string; email: string; phone: string; programCode: string; branch: Branch }) => string;
  createPlacementCase: (applicantId: string, blueprint?: string) => string;
  submitPlacementTest: (attemptId: string, score: number, recommendedLevel: string, breakdown: Record<string, number>) => void;
  releasePlacementDecision: (attemptId: string) => void;
  createAdmissionDecision: (applicantId: string, placementDecisionId: string, programCode: string) => string;
  reviewAdmission: (decisionId: string) => void;
  decideAdmission: (decisionId: string, outcome: 'Approved' | 'Conditional' | 'Deferred' | 'Rejected', reason: string, conditions?: string) => void;
  acceptOffer: (decisionId: string) => void;
  convertApplicantToStudent: (decisionId: string) => string;
  enrollInProgram: (studentId: string, programCode: string, levelName: string, branch: Branch) => void;
  addGroupMember: (groupId: string, studentId: string) => { success: boolean; message: string };
  removeGroupMember: (groupId: string, studentId: string, reason: string) => void;
  createStudentGroup: (data: Partial<StudentGroup>) => string;
  scheduleSession: (data: Partial<CourseSchedule>) => string;
  postponeSession: (scheduleId: string, newDate: string, reason: string) => void;
  cancelSession: (scheduleId: string, reason: string) => void;
  recordAttendance: (scheduleId: string, records: { studentId: string; studentName: string; status: 'Present' | 'Absent' | 'Leave' }[]) => void;
  requestAttendanceCorrection: (courseScheduleId: string, studentId: string, studentName: string, originalStatus: 'Present' | 'Absent' | 'Leave', requestedStatus: 'Present' | 'Absent' | 'Leave', reason: string) => void;
  decideAttendanceCorrection: (requestId: string, decision: 'Approved' | 'Denied') => void;
  issueTuitionFee: (studentId: string, programCode: string, levelName: string, amount: number) => string;
  issuePlacementFee: (applicantId: string, amount: number) => string;
  recordPayment: (invoiceId: string, amount: number, method: 'Cash' | 'Bank Transfer' | 'Card', cashierName: string) => string;
  reconcileCashierDay: (actualCount: number, notes?: string) => void;
  sellBook: (bookId: string, customerName: string, quantity: number, paymentMethod: 'Cash' | 'Card') => { success: boolean; invoiceId?: string; message: string };
  requestFeeCorrection: (invoiceId: string, requestedAmount: number, reason: string) => void;
  decideFeeCorrection: (requestId: string, decision: 'Approved' | 'Denied') => void;
  appendPolicyVersion: (domainName: string, versionTitle: string, effectiveFrom: string, summary: string) => void;
  resetToDemoData: () => void;
}

const STORAGE_KEY = 'toefl_house_erp_store_v1';

const ERPContext = createContext<ERPContextType | undefined>(undefined);

export const ERPProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [activeRole, setActiveRole] = useState<InstituteRole>('Reception');
  const [activeBranch, setActiveBranch] = useState<Branch | 'All Branches'>('All Branches');
  const [activeDesk, setActiveDesk] = useState<DeskSlug>('th-reception-desk');
  const [activeInstructorId, setActiveInstructorId] = useState<string>('INS-01');

  // Load from local storage or fallback to pristine seeds
  const [programs] = useState<AcademicProgram[]>(initialPrograms);
  const [levels] = useState<ProgramLevel[]>(initialLevels);
  const [durationPolicies] = useState<LevelDurationPolicy[]>(initialDurationPolicies);

  const [applicants, setApplicants] = useState<StudentApplicant[]>(() => {
    const saved = localStorage.getItem(`${STORAGE_KEY}_applicants`);
    return saved ? JSON.parse(saved) : initialApplicants;
  });

  const [placementItems] = useState<PlacementItem[]>(initialPlacementItems);

  const [placementAttempts, setPlacementAttempts] = useState<PlacementAttempt[]>(() => {
    const saved = localStorage.getItem(`${STORAGE_KEY}_placementAttempts`);
    return saved ? JSON.parse(saved) : initialPlacementAttempts;
  });

  const [placementDecisions, setPlacementDecisions] = useState<PlacementDecision[]>(() => {
    const saved = localStorage.getItem(`${STORAGE_KEY}_placementDecisions`);
    return saved ? JSON.parse(saved) : initialPlacementDecisions;
  });

  const [admissionDecisions, setAdmissionDecisions] = useState<AdmissionDecision[]>(() => {
    const saved = localStorage.getItem(`${STORAGE_KEY}_admissionDecisions`);
    return saved ? JSON.parse(saved) : initialAdmissionDecisions;
  });

  const [students, setStudents] = useState<Student[]>(() => {
    const saved = localStorage.getItem(`${STORAGE_KEY}_students`);
    return saved ? JSON.parse(saved) : initialStudents;
  });

  const [enrollments, setEnrollments] = useState<ProgramEnrollment[]>(() => {
    const saved = localStorage.getItem(`${STORAGE_KEY}_enrollments`);
    return saved ? JSON.parse(saved) : initialEnrollments;
  });

  const [studentGroups, setStudentGroups] = useState<StudentGroup[]>(() => {
    const saved = localStorage.getItem(`${STORAGE_KEY}_studentGroups`);
    return saved ? JSON.parse(saved) : initialStudentGroups;
  });

  const [schedules, setSchedules] = useState<CourseSchedule[]>(() => {
    const saved = localStorage.getItem(`${STORAGE_KEY}_schedules`);
    return saved ? JSON.parse(saved) : initialSchedules;
  });

  const [attendanceRecords, setAttendanceRecords] = useState<AttendanceRecord[]>(() => {
    const saved = localStorage.getItem(`${STORAGE_KEY}_attendanceRecords`);
    return saved ? JSON.parse(saved) : initialAttendanceRecords;
  });

  const [attendanceCorrections, setAttendanceCorrections] = useState<AttendanceCorrectionRequest[]>(() => {
    const saved = localStorage.getItem(`${STORAGE_KEY}_attendanceCorrections`);
    return saved ? JSON.parse(saved) : initialAttendanceCorrections;
  });

  const [invoices, setInvoices] = useState<SalesInvoice[]>(() => {
    const saved = localStorage.getItem(`${STORAGE_KEY}_invoices`);
    return saved ? JSON.parse(saved) : initialInvoices;
  });

  const [payments, setPayments] = useState<PaymentEntry[]>(() => {
    const saved = localStorage.getItem(`${STORAGE_KEY}_payments`);
    return saved ? JSON.parse(saved) : initialPayments;
  });

  const [cashierDay, setCashierDay] = useState<CashierDay>(() => {
    const saved = localStorage.getItem(`${STORAGE_KEY}_cashierDay`);
    return saved ? JSON.parse(saved) : initialCashierDay;
  });

  const [books, setBooks] = useState<BookItem[]>(() => {
    const saved = localStorage.getItem(`${STORAGE_KEY}_books`);
    return saved ? JSON.parse(saved) : initialBooks;
  });

  const [correctionRequests, setCorrectionRequests] = useState<CorrectionRequest[]>(() => {
    const saved = localStorage.getItem(`${STORAGE_KEY}_correctionRequests`);
    return saved ? JSON.parse(saved) : initialCorrectionRequests;
  });

  const [instructors] = useState<Instructor[]>(initialInstructors);

  const [auditEvents, setAuditEvents] = useState<ConfigurationAuditEvent[]>(() => {
    const saved = localStorage.getItem(`${STORAGE_KEY}_auditEvents`);
    return saved ? JSON.parse(saved) : initialAuditEvents;
  });

  const [policyDomains, setPolicyDomains] = useState<PolicyDomain[]>(() => {
    const saved = localStorage.getItem(`${STORAGE_KEY}_policyDomains`);
    return saved ? JSON.parse(saved) : initialPolicyDomains;
  });

  // Sync to local storage
  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}_applicants`, JSON.stringify(applicants));
  }, [applicants]);

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}_placementAttempts`, JSON.stringify(placementAttempts));
  }, [placementAttempts]);

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}_placementDecisions`, JSON.stringify(placementDecisions));
  }, [placementDecisions]);

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}_admissionDecisions`, JSON.stringify(admissionDecisions));
  }, [admissionDecisions]);

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}_students`, JSON.stringify(students));
  }, [students]);

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}_enrollments`, JSON.stringify(enrollments));
  }, [enrollments]);

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}_studentGroups`, JSON.stringify(studentGroups));
  }, [studentGroups]);

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}_schedules`, JSON.stringify(schedules));
  }, [schedules]);

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}_attendanceRecords`, JSON.stringify(attendanceRecords));
  }, [attendanceRecords]);

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}_attendanceCorrections`, JSON.stringify(attendanceCorrections));
  }, [attendanceCorrections]);

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}_invoices`, JSON.stringify(invoices));
  }, [invoices]);

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}_payments`, JSON.stringify(payments));
  }, [payments]);

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}_cashierDay`, JSON.stringify(cashierDay));
  }, [cashierDay]);

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}_books`, JSON.stringify(books));
  }, [books]);

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}_correctionRequests`, JSON.stringify(correctionRequests));
  }, [correctionRequests]);

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}_auditEvents`, JSON.stringify(auditEvents));
  }, [auditEvents]);

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}_policyDomains`, JSON.stringify(policyDomains));
  }, [policyDomains]);

  // Helper: append audit event
  const appendAuditEvent = (action: string, target: string, details: string) => {
    const prev = auditEvents[0]?.hash || 'genesis-block-000000000000000000000000000000000000';
    const rand = Math.random().toString(36).substring(2, 10);
    const newHash = Array.from(action + target + Date.now().toString() + rand)
      .map((c) => c.charCodeAt(0).toString(16).padStart(2, '0'))
      .join('')
      .padEnd(64, 'a')
      .substring(0, 64);

    const event: ConfigurationAuditEvent = {
      id: `AUD-2026-${Date.now().toString().slice(-4)}`,
      timestamp: new Date().toISOString().replace('T', ' ').substring(0, 16),
      actor: activeRole,
      action,
      target,
      requestKey: `REQ-${Math.random().toString(36).substring(2, 9).toUpperCase()}`,
      hash: newHash,
      previousHash: prev,
      status: 'Complete',
      details,
    };
    setAuditEvents((curr) => [event, ...curr]);
  };

  // Actions
  const recordApplicant = (data: { name: string; email: string; phone: string; programCode: string; branch: Branch }) => {
    const id = `APP-2026-${Math.floor(100 + Math.random() * 900)}`;
    const newApplicant: StudentApplicant = {
      id,
      name: data.name,
      email: data.email,
      phone: data.phone,
      branch: data.branch,
      programCode: data.programCode,
      academicYear: '2026',
      academicTerm: 'Term 4',
      creationDate: new Date().toISOString().split('T')[0],
      applicationStatus: 'Registered',
    };
    setApplicants((prev) => [newApplicant, ...prev]);
    appendAuditEvent('record_applicant', `Student Applicant (${id})`, `Recorded new applicant ${data.name} for ${data.programCode} at ${data.branch}`);
    return id;
  };

  const createPlacementCase = (applicantId: string, blueprint = 'BP-TOEFL-STD-2026') => {
    const applicant = applicants.find((a) => a.id === applicantId);
    if (!applicant) return '';
    const attemptId = `ATT-2026-${Math.floor(800 + Math.random() * 199)}`;
    const caseId = `CASE-${Math.floor(100 + Math.random() * 900)}`;

    const newAttempt: PlacementAttempt = {
      id: attemptId,
      caseId,
      candidateName: applicant.name,
      candidateEmail: applicant.email,
      branch: applicant.branch,
      blueprint,
      blueprintVersion: 3,
      status: 'Allocated',
      maxScore: 100,
      recommendedProgram: applicant.programCode,
      recommendedLevel: 'Skills Mastery (R & L)',
      scheduledTime: new Date(Date.now() + 86400000).toISOString().replace('T', ' ').substring(0, 16),
      invigilator: 'Mariam Safi',
    };

    setPlacementAttempts((prev) => [newAttempt, ...prev]);
    setApplicants((prev) =>
      prev.map((a) => (a.id === applicantId ? { ...a, applicationStatus: 'Placement Scheduled' } : a))
    );

    appendAuditEvent('allocate_attempt', `TH Placement Attempt (${attemptId})`, `Allocated attempt for ${applicant.name} using ${blueprint}`);
    return attemptId;
  };

  const submitPlacementTest = (attemptId: string, score: number, recommendedLevel: string, breakdown: Record<string, number>) => {
    const attempt = placementAttempts.find((a) => a.id === attemptId);
    if (!attempt) return;

    const decisionId = `PLC-DEC-${Math.floor(100 + Math.random() * 900)}`;

    const decision: PlacementDecision = {
      id: decisionId,
      attemptId,
      candidateName: attempt.candidateName,
      candidateEmail: attempt.candidateEmail,
      score,
      recommendedProgram: attempt.recommendedProgram,
      recommendedLevel,
      status: 'Draft',
      rationale: `Objective test score: ${score}/100. Diagnostic profile indicates strong fit for ${recommendedLevel}.`,
    };

    setPlacementDecisions((prev) => [decision, ...prev]);
    setPlacementAttempts((prev) =>
      prev.map((a) =>
        a.id === attemptId
          ? {
              ...a,
              status: 'Finalized',
              score,
              breakdown,
              recommendedLevel,
              sealedTime: new Date().toISOString().replace('T', ' ').substring(0, 16),
              assessor: 'Hamid Azizi',
              reviewer: 'Academic Manager',
            }
          : a
      )
    );

    setApplicants((prev) =>
      prev.map((a) =>
        a.email === attempt.candidateEmail
          ? { ...a, applicationStatus: 'Tested', placementDecisionId: decisionId }
          : a
      )
    );

    appendAuditEvent('finalize_attempt', `TH Placement Attempt (${attemptId})`, `Finalized placement assessment with score ${score}/100`);
  };

  const releasePlacementDecision = (attemptId: string) => {
    const attempt = placementAttempts.find((a) => a.id === attemptId);
    if (!attempt) return;

    setPlacementAttempts((prev) =>
      prev.map((a) =>
        a.id === attemptId
          ? {
              ...a,
              status: 'Released',
              releasedTime: new Date().toISOString().replace('T', ' ').substring(0, 16),
              releaser: 'Academic Manager',
            }
          : a
      )
    );

    setPlacementDecisions((prev) =>
      prev.map((d) =>
        d.attemptId === attemptId
          ? { ...d, status: 'Released', releaseDate: new Date().toISOString().split('T')[0] }
          : d
      )
    );

    appendAuditEvent('release_decision', `TH Placement Decision for ${attempt.candidateName}`, `Released official placement decision recommending ${attempt.recommendedLevel}`);
  };

  const createAdmissionDecision = (applicantId: string, placementDecisionId: string, programCode: string) => {
    const applicant = applicants.find((a) => a.id === applicantId);
    if (!applicant) return '';

    const id = `ADM-DEC-${Math.floor(400 + Math.random() * 599)}`;
    const decision: AdmissionDecision = {
      id,
      applicantId,
      applicantName: applicant.name,
      applicantEmail: applicant.email,
      branch: applicant.branch,
      placementDecisionId,
      programCode,
      academicYear: '2026',
      academicTerm: 'Term 4',
      status: 'Review',
      offerAccepted: false,
      version: 1,
      lastUpdated: new Date().toISOString().replace('T', ' ').substring(0, 16),
      reason: 'Placement verified. Awaiting academic approver decision on offer.',
    };

    setAdmissionDecisions((prev) => [decision, ...prev]);
    appendAuditEvent('create_admission', `TH Admission Decision (${id})`, `Initiated admission review for ${applicant.name}`);
    return id;
  };

  const reviewAdmission = (decisionId: string) => {
    setAdmissionDecisions((prev) =>
      prev.map((d) =>
        d.id === decisionId
          ? { ...d, status: 'Review', lastUpdated: new Date().toISOString().replace('T', ' ').substring(0, 16), version: d.version + 1 }
          : d
      )
    );
    appendAuditEvent('review_admission', `TH Admission Decision (${decisionId})`, `Moved admission decision to Review stage`);
  };

  const decideAdmission = (decisionId: string, outcome: 'Approved' | 'Conditional' | 'Deferred' | 'Rejected', reason: string, conditions?: string) => {
    setAdmissionDecisions((prev) =>
      prev.map((d) =>
        d.id === decisionId
          ? {
              ...d,
              status: outcome,
              reason,
              conditions: outcome === 'Conditional' ? conditions : undefined,
              conditionsSatisfied: outcome === 'Approved' ? true : outcome === 'Conditional' ? false : undefined,
              version: d.version + 1,
              lastUpdated: new Date().toISOString().replace('T', ' ').substring(0, 16),
            }
          : d
      )
    );

    setApplicants((prev) => {
      const dec = admissionDecisions.find((d) => d.id === decisionId);
      if (!dec) return prev;
      return prev.map((a) =>
        a.id === dec.applicantId
          ? { ...a, applicationStatus: outcome === 'Approved' || outcome === 'Conditional' ? 'Admitted' : outcome === 'Rejected' ? 'Rejected' : a.applicationStatus }
          : a
      );
    });

    appendAuditEvent('decide_admission', `TH Admission Decision (${decisionId})`, `Admission decision recorded outcome: ${outcome}`);
  };

  const acceptOffer = (decisionId: string) => {
    setAdmissionDecisions((prev) =>
      prev.map((d) =>
        d.id === decisionId
          ? {
              ...d,
              offerAccepted: true,
              offerAcceptedDate: new Date().toISOString().split('T')[0],
              conditionsSatisfied: true,
              version: d.version + 1,
              lastUpdated: new Date().toISOString().replace('T', ' ').substring(0, 16),
            }
          : d
      )
    );
    appendAuditEvent('accept_offer', `TH Admission Decision (${decisionId})`, `Candidate accepted institutional offer`);
  };

  const convertApplicantToStudent = (decisionId: string) => {
    const decision = admissionDecisions.find((d) => d.id === decisionId);
    if (!decision) return '';

    const applicant = applicants.find((a) => a.id === decision.applicantId);
    const newStudentId = `STU-2026-${String(students.length + 1).padStart(3, '0')}`;

    const newStudent: Student = {
      id: newStudentId,
      name: decision.applicantName,
      email: decision.applicantEmail,
      phone: applicant?.phone || '+93 70 000 0000',
      branch: decision.branch,
      currentProgram: decision.programCode,
      currentLevel: 'Skills Mastery (R & L)',
      enrollmentDate: new Date().toISOString().split('T')[0],
      status: 'Active',
    };

    const newEnrollment: ProgramEnrollment = {
      id: `ENR-2026-${String(enrollments.length + 1).padStart(2, '0')}`,
      studentId: newStudentId,
      studentName: decision.applicantName,
      programCode: decision.programCode,
      levelName: 'Skills Mastery (R & L)',
      branch: decision.branch,
      academicYear: '2026',
      academicTerm: 'Term 4',
      enrollmentDate: new Date().toISOString().split('T')[0],
      status: 'Active',
      feeIssued: false, // will appear in finance desk queue!
    };

    setStudents((prev) => [newStudent, ...prev]);
    setEnrollments((prev) => [newEnrollment, ...prev]);

    setAdmissionDecisions((prev) =>
      prev.map((d) =>
        d.id === decisionId
          ? {
              ...d,
              status: 'Converted',
              nativeStudentId: newStudentId,
              version: d.version + 1,
              lastUpdated: new Date().toISOString().replace('T', ' ').substring(0, 16),
            }
          : d
      )
    );

    setApplicants((prev) =>
      prev.map((a) =>
        a.id === decision.applicantId ? { ...a, applicationStatus: 'Enrolled' } : a
      )
    );

    appendAuditEvent('convert_applicant', `TH Admission Decision (${decisionId})`, `Converted applicant to native Student ${newStudentId}`);
    return newStudentId;
  };

  const enrollInProgram = (studentId: string, programCode: string, levelName: string, branch: Branch) => {
    const student = students.find((s) => s.id === studentId);
    if (!student) return;

    const id = `ENR-2026-${String(enrollments.length + 1).padStart(2, '0')}`;
    const newEnrollment: ProgramEnrollment = {
      id,
      studentId,
      studentName: student.name,
      programCode,
      levelName,
      branch,
      academicYear: '2026',
      academicTerm: 'Term 4',
      enrollmentDate: new Date().toISOString().split('T')[0],
      status: 'Active',
      feeIssued: false,
    };
    setEnrollments((prev) => [newEnrollment, ...prev]);
    appendAuditEvent('enroll_in_program', `Program Enrollment (${id})`, `Enrolled student ${student.name} in ${programCode}`);
  };

  const addGroupMember = (groupId: string, studentId: string) => {
    const group = studentGroups.find((g) => g.id === groupId);
    if (!group) return { success: false, message: 'Class group not found' };

    if (group.currentStrength >= group.maxStrength) {
      return { success: false, message: `Class is at maximum capacity (${group.maxStrength}/${group.maxStrength}). Requires capacity approval override.` };
    }

    if (group.studentIds.includes(studentId)) {
      return { success: false, message: 'Student is already enrolled in this class roster.' };
    }

    setStudentGroups((prev) =>
      prev.map((g) =>
        g.id === groupId
          ? {
              ...g,
              currentStrength: g.currentStrength + 1,
              studentIds: [...g.studentIds, studentId],
            }
          : g
      )
    );

    const student = students.find((s) => s.id === studentId);
    appendAuditEvent('add_class_member', `Student Group (${groupId})`, `Added student ${student?.name || studentId} to roster`);
    return { success: true, message: `Successfully enrolled ${student?.name || studentId} in ${group.groupName}` };
  };

  const removeGroupMember = (groupId: string, studentId: string, reason: string) => {
    const group = studentGroups.find((g) => g.id === groupId);
    if (!group) return;

    setStudentGroups((prev) =>
      prev.map((g) =>
        g.id === groupId
          ? {
              ...g,
              currentStrength: Math.max(0, g.currentStrength - 1),
              studentIds: g.studentIds.filter((id) => id !== studentId),
            }
          : g
      )
    );

    const student = students.find((s) => s.id === studentId);
    appendAuditEvent('remove_class_member', `Student Group (${groupId})`, `Removed student ${student?.name || studentId}: ${reason}`);
  };

  const createStudentGroup = (data: Partial<StudentGroup>) => {
    const id = `GRP-${data.programCode?.split('-')[0] || 'CLS'}-${Math.floor(100 + Math.random() * 900)}`;
    const newGroup: StudentGroup = {
      id,
      groupName: data.groupName || 'New Class Cohort',
      programCode: data.programCode || 'TOEFL-PREP',
      levelName: data.levelName || 'Diagnostic Foundations',
      academicYear: '2026',
      academicTerm: 'Term 4',
      branch: data.branch || 'Kabul Central',
      instructorId: data.instructorId || 'INS-01',
      instructorName: data.instructorName || 'Sarah Jenkins',
      room: data.room || 'Room 101',
      maxStrength: data.maxStrength || 16,
      currentStrength: 0,
      deliveryMode: data.deliveryMode || 'On-site',
      classStartDate: data.classStartDate || new Date().toISOString().split('T')[0],
      classEndDate: data.classEndDate || new Date(Date.now() + 60 * 86400000).toISOString().split('T')[0],
      status: 'Active',
      studentIds: [],
    };

    setStudentGroups((prev) => [newGroup, ...prev]);
    appendAuditEvent('create_student_group', `Student Group (${id})`, `Created new class cohort ${newGroup.groupName}`);
    return id;
  };

  const scheduleSession = (data: Partial<CourseSchedule>) => {
    const id = `SCH-2026-${Math.floor(700 + Math.random() * 299)}`;
    const newSchedule: CourseSchedule = {
      id,
      studentGroupId: data.studentGroupId || 'GRP-TOEFL-AM1',
      studentGroupName: data.studentGroupName || 'TOEFL Morning Masterclass (AM-1)',
      programCode: data.programCode || 'TOEFL-PREP',
      courseSkill: data.courseSkill || 'Integrated Language Skills',
      instructorId: data.instructorId || 'INS-01',
      instructorName: data.instructorName || 'Sarah Jenkins',
      room: data.room || 'Lab 101 - Smart Audio',
      scheduleDate: data.scheduleDate || new Date().toISOString().split('T')[0],
      fromTime: data.fromTime || '09:00',
      toTime: data.toTime || '11:00',
      branch: data.branch || 'Kabul Central',
      status: 'Scheduled',
      attendanceRecorded: false,
    };

    setSchedules((prev) => [newSchedule, ...prev]);
    appendAuditEvent('schedule_session', `Course Schedule (${id})`, `Scheduled session for ${newSchedule.studentGroupName} on ${newSchedule.scheduleDate}`);
    return id;
  };

  const postponeSession = (scheduleId: string, newDate: string, reason: string) => {
    setSchedules((prev) =>
      prev.map((s) => (s.id === scheduleId ? { ...s, scheduleDate: newDate, status: 'Postponed' } : s))
    );
    appendAuditEvent('postpone_session', `Course Schedule (${scheduleId})`, `Postponed session to ${newDate}: ${reason}`);
  };

  const cancelSession = (scheduleId: string, reason: string) => {
    setSchedules((prev) =>
      prev.map((s) => (s.id === scheduleId ? { ...s, status: 'Cancelled' } : s))
    );
    appendAuditEvent('cancel_session', `Course Schedule (${scheduleId})`, `Cancelled session: ${reason}`);
  };

  const recordAttendance = (scheduleId: string, records: { studentId: string; studentName: string; status: 'Present' | 'Absent' | 'Leave' }[]) => {
    const newRecords: AttendanceRecord[] = records.map((r) => ({
      id: `ATT-REC-${Date.now().toString().slice(-4)}-${Math.floor(Math.random() * 90)}`,
      courseScheduleId: scheduleId,
      studentId: r.studentId,
      studentName: r.studentName,
      status: r.status,
      recordedBy: activeRole === 'Instructor' ? 'Sarah Jenkins' : activeRole,
      recordedAt: new Date().toISOString().replace('T', ' ').substring(0, 16),
    }));

    setAttendanceRecords((prev) => [...newRecords, ...prev]);

    const presentCount = records.filter((r) => r.status === 'Present').length;
    setSchedules((prev) =>
      prev.map((s) =>
        s.id === scheduleId
          ? {
              ...s,
              status: 'Completed',
              attendanceRecorded: true,
              attendancePresentCount: presentCount,
              attendanceTotalCount: records.length,
            }
          : s
      )
    );

    appendAuditEvent('record_attendance', `Course Schedule (${scheduleId})`, `Recorded attendance for ${records.length} students (${presentCount} present)`);
  };

  const requestAttendanceCorrection = (
    courseScheduleId: string,
    studentId: string,
    studentName: string,
    originalStatus: 'Present' | 'Absent' | 'Leave',
    requestedStatus: 'Present' | 'Absent' | 'Leave',
    reason: string
  ) => {
    const id = `ATT-CORR-${Math.floor(100 + Math.random() * 899)}`;
    const req: AttendanceCorrectionRequest = {
      id,
      attendanceId: `ATT-${Math.random().toString(36).substring(2, 6)}`,
      courseScheduleId,
      studentId,
      studentName,
      date: new Date().toISOString().split('T')[0],
      originalStatus,
      requestedStatus,
      reason,
      requestedBy: activeRole,
      status: 'Pending',
    };
    setAttendanceCorrections((prev) => [req, ...prev]);
    appendAuditEvent('request_attendance_correction', `Attendance Correction (${id})`, `Requested status correction for ${studentName} to ${requestedStatus}`);
  };

  const decideAttendanceCorrection = (requestId: string, decision: 'Approved' | 'Denied') => {
    setAttendanceCorrections((prev) =>
      prev.map((r) =>
        r.id === requestId
          ? {
              ...r,
              status: decision,
              decidedBy: activeRole,
              decidedAt: new Date().toISOString().replace('T', ' ').substring(0, 16),
            }
          : r
      )
    );
    appendAuditEvent(decision === 'Approved' ? 'approve_attendance_correction' : 'deny_attendance_correction', `Attendance Correction (${requestId})`, `Decision: ${decision}`);
  };

  const issueTuitionFee = (studentId: string, programCode: string, levelName: string, amount: number) => {
    const student = students.find((s) => s.id === studentId);
    if (!student) return '';

    const invoiceId = `INV-2026-${Math.floor(50 + Math.random() * 49)}`;
    const newInvoice: SalesInvoice = {
      id: invoiceId,
      invoiceType: 'Tuition',
      studentOrApplicantId: studentId,
      studentOrApplicantName: student.name,
      programOrItem: `${programCode} - ${levelName}`,
      branch: student.branch,
      grandTotal: amount,
      paidAmount: 0,
      outstandingAmount: amount,
      dueDate: new Date(Date.now() + 14 * 86400000).toISOString().split('T')[0],
      issueDate: new Date().toISOString().split('T')[0],
      status: 'Unpaid',
    };

    setInvoices((prev) => [newInvoice, ...prev]);
    setEnrollments((prev) =>
      prev.map((e) => (e.studentId === studentId ? { ...e, feeIssued: true, feesId: invoiceId } : e))
    );

    appendAuditEvent('issue_tuition_fees', `Sales Invoice (${invoiceId})`, `Issued tuition fees invoice of $${amount} to ${student.name}`);
    return invoiceId;
  };

  const issuePlacementFee = (applicantId: string, amount: number) => {
    const applicant = applicants.find((a) => a.id === applicantId);
    if (!applicant) return '';

    const invoiceId = `INV-2026-${Math.floor(50 + Math.random() * 49)}`;
    const newInvoice: SalesInvoice = {
      id: invoiceId,
      invoiceType: 'Placement',
      studentOrApplicantId: applicantId,
      studentOrApplicantName: applicant.name,
      programOrItem: `Diagnostic Assessment Fee (${applicant.programCode})`,
      branch: applicant.branch,
      grandTotal: amount,
      paidAmount: 0,
      outstandingAmount: amount,
      dueDate: new Date(Date.now() + 7 * 86400000).toISOString().split('T')[0],
      issueDate: new Date().toISOString().split('T')[0],
      status: 'Unpaid',
    };

    setInvoices((prev) => [newInvoice, ...prev]);
    appendAuditEvent('issue_placement_fee', `Sales Invoice (${invoiceId})`, `Issued placement fee of $${amount} to applicant ${applicant.name}`);
    return invoiceId;
  };

  const recordPayment = (invoiceId: string, amount: number, method: 'Cash' | 'Bank Transfer' | 'Card', cashierName: string) => {
    const invoice = invoices.find((i) => i.id === invoiceId);
    if (!invoice) return '';

    const paymentId = `PAY-2026-${Math.floor(300 + Math.random() * 699)}`;
    const receiptKey = `RCPT-${invoice.branch.substring(0, 2).toUpperCase()}-2026-${Math.floor(900 + Math.random() * 99)}`;

    const newPayment: PaymentEntry = {
      id: paymentId,
      invoiceId,
      payerName: invoice.studentOrApplicantName,
      amount,
      paymentMethod: method,
      paymentDate: new Date().toISOString().split('T')[0],
      cashierName,
      receiptKey,
      status: 'Submitted',
    };

    setPayments((prev) => [newPayment, ...prev]);

    setInvoices((prev) =>
      prev.map((inv) => {
        if (inv.id !== invoiceId) return inv;
        const newPaid = inv.paidAmount + amount;
        const newOutstanding = Math.max(0, inv.grandTotal - newPaid);
        return {
          ...inv,
          paidAmount: newPaid,
          outstandingAmount: newOutstanding,
          status: newOutstanding === 0 ? 'Paid' : 'Partial',
        };
      })
    );

    if (method === 'Cash') {
      setCashierDay((prev) => ({
        ...prev,
        collectedCash: prev.collectedCash + amount,
        expectedBalance: prev.expectedBalance + amount,
      }));
    }

    appendAuditEvent('record_payment', `Payment Entry (${paymentId})`, `Received $${amount} (${method}) for ${invoice.id} from ${invoice.studentOrApplicantName}`);
    return paymentId;
  };

  const reconcileCashierDay = (actualCount: number, notes?: string) => {
    setCashierDay((prev) => {
      const diff = actualCount - prev.expectedBalance;
      const status = diff === 0 ? 'Balanced' : 'Discrepancy';
      return {
        ...prev,
        actualCount,
        difference: diff,
        status,
        notes: notes || prev.notes,
      };
    });
    appendAuditEvent('reconcile_cashier_count', `Cashier Day (${cashierDay.id})`, `Reconciled cash drawer with actual count $${actualCount}`);
  };

  const sellBook = (bookId: string, customerName: string, quantity: number, paymentMethod: 'Cash' | 'Card') => {
    const book = books.find((b) => b.id === bookId);
    if (!book) return { success: false, message: 'Book item not found' };
    if (book.currentStock < quantity) {
      return { success: false, message: `Insufficient stock! Only ${book.currentStock} copies available in warehouse.` };
    }

    const total = book.unitPrice * quantity;
    const invoiceId = `INV-2026-${Math.floor(60 + Math.random() * 39)}`;

    const newInvoice: SalesInvoice = {
      id: invoiceId,
      invoiceType: 'Book',
      studentOrApplicantId: 'WALK-IN',
      studentOrApplicantName: customerName,
      programOrItem: `${book.title} (x${quantity})`,
      branch: 'Kabul Central',
      grandTotal: total,
      paidAmount: total,
      outstandingAmount: 0,
      dueDate: new Date().toISOString().split('T')[0],
      issueDate: new Date().toISOString().split('T')[0],
      status: 'Paid',
    };

    const newPayment: PaymentEntry = {
      id: `PAY-2026-${Math.floor(400 + Math.random() * 599)}`,
      invoiceId,
      payerName: customerName,
      amount: total,
      paymentMethod,
      paymentDate: new Date().toISOString().split('T')[0],
      cashierName: activeRole === 'Reception' ? 'Reception Cashier' : 'Finance Officer',
      receiptKey: `RCPT-BK-2026-${Math.floor(100 + Math.random() * 899)}`,
      status: 'Submitted',
    };

    setBooks((prev) =>
      prev.map((b) => (b.id === bookId ? { ...b, currentStock: b.currentStock - quantity } : b))
    );
    setInvoices((prev) => [newInvoice, ...prev]);
    setPayments((prev) => [newPayment, ...prev]);

    if (paymentMethod === 'Cash') {
      setCashierDay((prev) => ({
        ...prev,
        collectedCash: prev.collectedCash + total,
        expectedBalance: prev.expectedBalance + total,
      }));
    }

    appendAuditEvent('stock_book_sale', `Sales Invoice (${invoiceId})`, `Sold ${quantity} copies of "${book.title}" for $${total} (${paymentMethod})`);
    return { success: true, invoiceId, message: `Successfully sold ${quantity} copy/copies to ${customerName}. Receipt issued.` };
  };

  const requestFeeCorrection = (invoiceId: string, requestedAmount: number, reason: string) => {
    const invoice = invoices.find((i) => i.id === invoiceId);
    if (!invoice) return;

    const reqId = `CORR-2026-${String(correctionRequests.length + 1).padStart(2, '0')}`;
    const newReq: CorrectionRequest = {
      id: reqId,
      invoiceId,
      clientName: invoice.studentOrApplicantName,
      currentAmount: invoice.grandTotal,
      requestedAmount,
      reason,
      status: 'Pending',
      requestedBy: activeRole,
      requestedAt: new Date().toISOString().replace('T', ' ').substring(0, 16),
    };

    setCorrectionRequests((prev) => [newReq, ...prev]);
    appendAuditEvent('request_fee_correction', `Correction Request (${reqId})`, `Requested adjustment for invoice ${invoiceId} from $${invoice.grandTotal} to $${requestedAmount}`);
  };

  const decideFeeCorrection = (requestId: string, decision: 'Approved' | 'Denied') => {
    const req = correctionRequests.find((r) => r.id === requestId);
    if (!req) return;

    setCorrectionRequests((prev) =>
      prev.map((r) => (r.id === requestId ? { ...r, status: decision, decidedBy: activeRole } : r))
    );

    if (decision === 'Approved') {
      setInvoices((prev) =>
        prev.map((inv) => {
          if (inv.id !== req.invoiceId) return inv;
          const diff = inv.grandTotal - req.requestedAmount;
          const newTotal = req.requestedAmount;
          const newOutstanding = Math.max(0, inv.outstandingAmount - diff);
          return {
            ...inv,
            grandTotal: newTotal,
            outstandingAmount: newOutstanding,
            status: newOutstanding === 0 ? 'Paid' : 'Partial',
          };
        })
      );
    }

    appendAuditEvent(decision === 'Approved' ? 'approve_fee_correction' : 'deny_fee_correction', `Correction Request (${requestId})`, `Decision: ${decision}`);
  };

  const appendPolicyVersion = (domainName: string, versionTitle: string, effectiveFrom: string, summary: string) => {
    setPolicyDomains((prev) =>
      prev.map((p) =>
        p.domain === domainName
          ? {
              ...p,
              governingVersion: versionTitle,
              effectiveFrom,
              status: 'Configured & Active',
              summary,
            }
          : p
      )
    );
    appendAuditEvent('append_policy_version', `Policy Domain (${domainName})`, `Appended new policy version "${versionTitle}" effective ${effectiveFrom}`);
  };

  const resetToDemoData = () => {
    localStorage.clear();
    setApplicants(initialApplicants);
    setPlacementAttempts(initialPlacementAttempts);
    setPlacementDecisions(initialPlacementDecisions);
    setAdmissionDecisions(initialAdmissionDecisions);
    setStudents(initialStudents);
    setEnrollments(initialEnrollments);
    setStudentGroups(initialStudentGroups);
    setSchedules(initialSchedules);
    setAttendanceRecords(initialAttendanceRecords);
    setAttendanceCorrections(initialAttendanceCorrections);
    setInvoices(initialInvoices);
    setPayments(initialPayments);
    setCashierDay(initialCashierDay);
    setBooks(initialBooks);
    setCorrectionRequests(initialCorrectionRequests);
    setAuditEvents(initialAuditEvents);
    setPolicyDomains(initialPolicyDomains);
  };

  return (
    <ERPContext.Provider
      value={{
        activeRole,
        setActiveRole,
        activeBranch,
        setActiveBranch,
        activeDesk,
        setActiveDesk,
        activeInstructorId,
        setActiveInstructorId,
        programs,
        levels,
        durationPolicies,
        applicants,
        placementItems,
        placementAttempts,
        placementDecisions,
        admissionDecisions,
        students,
        enrollments,
        studentGroups,
        schedules,
        attendanceRecords,
        attendanceCorrections,
        invoices,
        payments,
        cashierDay,
        books,
        correctionRequests,
        instructors,
        auditEvents,
        policyDomains,
        recordApplicant,
        createPlacementCase,
        submitPlacementTest,
        releasePlacementDecision,
        createAdmissionDecision,
        reviewAdmission,
        decideAdmission,
        acceptOffer,
        convertApplicantToStudent,
        enrollInProgram,
        addGroupMember,
        removeGroupMember,
        createStudentGroup,
        scheduleSession,
        postponeSession,
        cancelSession,
        recordAttendance,
        requestAttendanceCorrection,
        decideAttendanceCorrection,
        issueTuitionFee,
        issuePlacementFee,
        recordPayment,
        reconcileCashierDay,
        sellBook,
        requestFeeCorrection,
        decideFeeCorrection,
        appendPolicyVersion,
        resetToDemoData,
      }}
    >
      {children}
    </ERPContext.Provider>
  );
};

export const useERP = () => {
  const context = useContext(ERPContext);
  if (!context) {
    throw new Error('useERP must be used within an ERPProvider');
  }
  return context;
};
