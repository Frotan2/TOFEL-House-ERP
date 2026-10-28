export type InstituteRole =
  | 'Course Owner'
  | 'General Manager'
  | 'Academic Manager'
  | 'Finance Manager'
  | 'Reception'
  | 'Instructor';

export type DutyRole =
  | 'Placement Author'
  | 'Placement Publisher'
  | 'Placement Invigilator'
  | 'Placement Assessor'
  | 'Placement Reviewer'
  | 'Placement Releaser'
  | 'Admission Officer'
  | 'Admission Reviewer'
  | 'Admission Approver'
  | 'Enrollment Officer'
  | 'Teaching Scheduler'
  | 'Attendance Recorder'
  | 'Finance Officer';

export type AppRole = InstituteRole | DutyRole;

export type Branch = 'Kabul Central' | 'West Campus' | 'Online';

export type DeskSlug =
  | 'th-reception-desk'
  | 'th-academic-desk'
  | 'th-finance-desk'
  | 'th-operations-desk'
  | 'th-owner-cockpit'
  | 'th-academic-setup'
  | 'th-teacher-desk'
  | 'th-configuration'
  | 'th-command-centre';

export type StatusTone = 'ok' | 'info' | 'warn' | 'danger' | 'neutral';

export interface AcademicProgram {
  code: string;
  name: string;
  family: string;
  description: string;
  targetExam?: string;
  status: 'Active' | 'Draft' | 'Retired';
}

export interface ProgramLevel {
  id: string;
  programCode: string;
  levelOrder: number;
  levelName: string;
  cefrEquivalent: string;
  standardDurationWeeks: number;
  totalHours: number;
  status: 'Active' | 'Draft';
}

export interface LevelDurationPolicy {
  id: string;
  code: string;
  title: string;
  model: 'Standard' | 'Intensive' | 'Weekend';
  weeks: number;
  sessionsPerWeek: number;
  hoursPerSession: number;
  totalHours: number;
  effectiveFrom: string;
  actor: string;
  status: 'Active' | 'Archived';
}

export interface StudentApplicant {
  id: string;
  name: string;
  email: string;
  phone: string;
  branch: Branch;
  programCode: string;
  academicYear: string;
  academicTerm: string;
  creationDate: string;
  placementDecisionId?: string;
  applicationStatus: 'Registered' | 'Placement Scheduled' | 'Tested' | 'Admitted' | 'Enrolled' | 'Rejected' | 'Withdrawn';
}

export interface PlacementItem {
  id: string;
  family: string;
  revision: number;
  skill: 'Reading' | 'Listening' | 'Grammar' | 'Vocabulary' | 'Speaking' | 'Writing';
  difficulty: 'A2' | 'B1' | 'B2' | 'C1';
  questionType: 'single_choice' | 'multi_choice' | 'cloze' | 'short_response';
  prompt: string;
  options?: string[];
  correctAnswer?: string | string[];
  status: 'Draft' | 'Published' | 'Retired';
}

export interface PlacementAttempt {
  id: string;
  caseId: string;
  candidateName: string;
  candidateEmail: string;
  branch: Branch;
  blueprint: string;
  blueprintVersion: number;
  status: 'Registered' | 'Allocated' | 'Verified' | 'In Progress' | 'Sealed' | 'Marking' | 'Review' | 'Finalized' | 'Released';
  score?: number;
  maxScore: number;
  breakdown?: Record<string, number>;
  recommendedProgram: string;
  recommendedLevel: string;
  scheduledTime: string;
  sealedTime?: string;
  releasedTime?: string;
  invigilator?: string;
  assessor?: string;
  reviewer?: string;
  releaser?: string;
}

export interface PlacementDecision {
  id: string;
  attemptId: string;
  candidateName: string;
  candidateEmail: string;
  score: number;
  recommendedProgram: string;
  recommendedLevel: string;
  status: 'Draft' | 'Reviewed' | 'Approved' | 'Released' | 'Superseded';
  releaseDate?: string;
  rationale: string;
}

export interface AdmissionDecision {
  id: string;
  applicantId: string;
  applicantName: string;
  applicantEmail: string;
  branch: Branch;
  placementDecisionId: string;
  programCode: string;
  academicYear: string;
  academicTerm: string;
  status: 'Draft' | 'Review' | 'Approved' | 'Conditional' | 'Deferred' | 'Rejected' | 'Converted';
  conditions?: string;
  conditionsSatisfied?: boolean;
  offerAccepted: boolean;
  offerAcceptedDate?: string;
  nativeStudentId?: string;
  reason?: string;
  version: number;
  lastUpdated: string;
}

export interface Student {
  id: string; // STU-2026-001
  name: string;
  email: string;
  phone: string;
  branch: Branch;
  currentProgram: string;
  currentLevel: string;
  enrollmentDate: string;
  status: 'Active' | 'On Leave' | 'Suspended' | 'Withdrawn' | 'Graduated';
  guardianName?: string;
  guardianPhone?: string;
}

export interface ProgramEnrollment {
  id: string;
  studentId: string;
  studentName: string;
  programCode: string;
  levelName: string;
  branch: Branch;
  academicYear: string;
  academicTerm: string;
  enrollmentDate: string;
  status: 'Active' | 'Completed' | 'Withdrawn' | 'Dismissed';
  feeIssued: boolean;
  feesId?: string;
}

export interface StudentGroup {
  id: string; // e.g. TOEFL-2026-AM1
  groupName: string;
  programCode: string;
  levelName: string;
  academicYear: string;
  academicTerm: string;
  branch: Branch;
  instructorId: string;
  instructorName: string;
  room: string;
  maxStrength: number;
  currentStrength: number;
  deliveryMode: 'On-site' | 'Online' | 'Hybrid';
  classStartDate: string;
  classEndDate: string;
  status: 'Active' | 'Planned' | 'Completed' | 'Cancelled';
  studentIds: string[];
}

export interface CourseSchedule {
  id: string;
  studentGroupId: string;
  studentGroupName: string;
  programCode: string;
  courseSkill: string;
  instructorId: string;
  instructorName: string;
  room: string;
  scheduleDate: string;
  fromTime: string;
  toTime: string;
  branch: Branch;
  status: 'Scheduled' | 'Completed' | 'Postponed' | 'Cancelled';
  attendanceRecorded: boolean;
  attendancePresentCount?: number;
  attendanceTotalCount?: number;
}

export interface AttendanceRecord {
  id: string;
  courseScheduleId: string;
  studentId: string;
  studentName: string;
  status: 'Present' | 'Absent' | 'Leave';
  recordedBy: string;
  recordedAt: string;
}

export interface AttendanceCorrectionRequest {
  id: string;
  attendanceId: string;
  courseScheduleId: string;
  studentId: string;
  studentName: string;
  date: string;
  originalStatus: 'Present' | 'Absent' | 'Leave';
  requestedStatus: 'Present' | 'Absent' | 'Leave';
  reason: string;
  requestedBy: string;
  status: 'Pending' | 'Approved' | 'Denied';
  decidedBy?: string;
  decidedAt?: string;
}

export interface SalesInvoice {
  id: string;
  invoiceType: 'Tuition' | 'Placement' | 'Book';
  studentOrApplicantId: string;
  studentOrApplicantName: string;
  programOrItem: string;
  branch: Branch;
  grandTotal: number;
  paidAmount: number;
  outstandingAmount: number;
  dueDate: string;
  issueDate: string;
  status: 'Unpaid' | 'Partial' | 'Paid' | 'Overdue' | 'Credit Note Issued' | 'Cancelled';
}

export interface PaymentEntry {
  id: string;
  invoiceId: string;
  payerName: string;
  amount: number;
  paymentMethod: 'Cash' | 'Bank Transfer' | 'Card';
  paymentDate: string;
  cashierName: string;
  receiptKey: string;
  status: 'Submitted' | 'Reconciled' | 'Voided';
}

export interface CashierDay {
  id: string;
  cashierName: string;
  date: string;
  branch: Branch;
  openingCash: number;
  collectedCash: number;
  expectedBalance: number;
  actualCount?: number;
  difference?: number;
  status: 'Open' | 'Balanced' | 'Discrepancy' | 'Closed';
  notes?: string;
}

export interface BookItem {
  id: string;
  code: string;
  title: string;
  category: 'TOEFL' | 'IELTS' | 'General English' | 'Grammar';
  unitPrice: number;
  currentStock: number;
  warehouse: string;
  reorderLevel: number;
}

export interface CorrectionRequest {
  id: string;
  invoiceId: string;
  clientName: string;
  currentAmount: number;
  requestedAmount: number;
  reason: string;
  status: 'Pending' | 'Approved' | 'Denied';
  requestedBy: string;
  requestedAt: string;
  decidedBy?: string;
}

export interface Instructor {
  id: string;
  name: string;
  email: string;
  phone: string;
  branch: Branch;
  skills: string[];
  contractType: 'Hourly' | 'Fixed-Term' | 'Per-Student';
  status: 'Active' | 'On Leave' | 'Inactive';
  assignedClassCount: number;
  sessionsThisMonth: number;
  payrollStatus: 'Ready' | 'Processed' | 'Action Needed';
}

export interface ConfigurationAuditEvent {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  target: string;
  requestKey: string;
  hash: string;
  previousHash: string;
  status: 'Complete' | 'Failed';
  details: string;
}

export interface PolicyDomain {
  domain: string;
  name: string;
  governingVersion: string;
  effectiveFrom: string;
  status: 'Configured & Active' | 'Draft Version' | 'Deferred (D1/D5)' | 'Unconfigured';
  summary: string;
  ownerDecision?: string;
}
