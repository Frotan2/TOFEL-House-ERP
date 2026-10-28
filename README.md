# TOEFL House ERP (React Edition)

Course Management ERP for the **TOEFL House** language institute, rewritten as a modern, high-performance **React + TypeScript + Tailwind CSS** web application.

## Overview

TOEFL House ERP provides an integrated operating system for the institute's daily management across all eight core administrative roles, multi-branch operations, diagnostic placement testing, admission workflows, class rosters, session attendance, tuition billing, native book store, and policy configuration.

## Key Features & Role Desks

### 1. Reception Desk (`th-reception-desk`)
- **Front-Desk Person Lookup:** Instant search matching applicant/student name, email, or phone.
- **Applicant Intake Funnel:** Real-time metrics across Registered, Placement Queued, Tested & Scored, Admitted, and Enrolled stages.
- **People in the Funnel:** Stage tracking, status badges, and guided next actions (Record Applicant, Schedule Placement, Deliver Test, Convert to Student).
- **New Applicant Intake:** Guarded modal to register candidate contact info and target program.

### 2. Academic Manager Desk (`th-academic-desk`)
- **Diagnostic Placement Queue:** Supervised testing attempts, objective scores, and recommended course placements.
- **Admission Approvals Queue:** Review and decide admission outcomes (Approved, Conditional, Deferred, Rejected) with condition tracking.
- **Classes & Sessions Today:** Live Course Schedule and Student Group capacity monitoring (enrolled vs max strength).
- **Session Scheduling:** Timetable session creation and conflict checking.

### 3. Finance Manager Desk (`th-finance-desk`)
- **Daily Collections & Billings:** Collections received today, invoices issued, and net outstanding receivables.
- **Outstanding Receivables Queue:** Grouped charged, paid, and outstanding amounts with direct "Record Payment" guided action.
- **Enrollments Awaiting Billing:** Active student enrollments with zero fees issued, with one-click "Issue Tuition Fee".
- **Cash Register Drawer & Float:** Daily opening float, collected cash, expected balance, and reconciliation with variance logging.
- **Native Book Shop Inventory:** Stock-enabled inventory (Official TOEFL Guide, Cambridge IELTS, etc.), stock alerts, and point-of-sale invoicing.
- **Fee Correction Queue:** Guarded review and approval of fee adjustment requests.

### 4. General Manager / Operations Desk (`th-operations-desk`)
- **Cross-Role Funnel & Bottlenecks:** Identification of admissions in review > 48h, overdue tuition, unbilled enrollments, and pending attendance corrections.
- **Staffing Distribution:** Live count of assigned users across shipped operational roles.
- **Cryptographic Audit Log:** Immutable ledger showing actor, command, target record, and SHA-256 digest receipts.
- **System Health:** Monitored runtime health, loopback network security, and zero unhandled errors.

### 5. Course Owner Cockpit (`th-owner-cockpit`)
- **Executive Analytics:** Active course enrollments, total tuition realized, overdue balances, and verified attendance rates.
- **Governance Attention:** Enforced Owner Decisions D1–D18 (D1 deferred grading/progression, D5 transfer hard-refused, D13/D15 private deployment, D18 backup hold).
- **Hash-Chained Audit Chain:** Cryptographic receipt verification across all mutations.

### 6. Teacher Desk (`th-teacher-desk`)
- **Instructor Switcher:** Easily switch between faculty members (Sarah Jenkins, Ahmad Wardak, Fatima Noori).
- **Today's Teaching Sessions:** Scheduled class sessions with room, times, and module focus.
- **Interactive Attendance Sheet:** Roster table with one-click "Mark All Present" or individual Present/Absent/Leave toggles.
- **Assigned Class Cohorts:** Roster sizes, delivery modes, and session dates.

### 7. Academic Setup (`th-academic-setup`)
- **Program Curricula:** TOEFL iBT Prep, General Academic English, IELTS Academic, and Executive Business English.
- **Ordered Program Levels:** CEFR-benchmarked tiers (Diagnostic Foundations, Skills Mastery, Productive Skills, Full Test Simulation) with contact hour requirements.
- **Effective-Dated Duration Policies:** Standard 8-week, Intensive 4-week, and Weekend 10-week models.

### 8. Configuration Plane (`th-configuration`)
- **Policy Domains:** Catalog linkage, guardian lifecycle, class operations, billing & discounts, and backup policies.
- **Readiness Badges:** Computed readiness indicators for institutional consumers.
- **Append Policy Version:** Guarded mutation command to append new effective-dated business terms.

### 9. Command Centre (`th-command-centre`)
- Role-gated command pages for Placement Authoring, Publication, Invigilation, Admissions, Scheduling, and Attendance.

## Development & Build

```bash
# Install dependencies
npm install

# Start development server on port 3000
npm run dev

# Compile TypeScript and build for production
npm run build
```

## Tech Stack
- **Framework:** React 18 with TypeScript
- **Bundler:** Vite 6
- **Styling:** Tailwind CSS v4 + TOEFL House Design System tokens
- **Icons:** Lucide React
- **Storage:** Reactive state synchronized with LocalStorage for offline persistence and reset capability
