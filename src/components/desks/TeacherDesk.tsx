import React, { useState } from 'react';
import {
  BookOpen,
  Calendar,
  CheckCircle,
  Users,
  Clock,
  ClipboardList,
  FileText,
  UserCheck,
} from 'lucide-react';
import { useERP } from '../../context/ERPContext';
import { StatusBadge } from '../common/StatusBadge';
import { MetricCard } from '../common/MetricCard';

export const TeacherDesk: React.FC = () => {
  const {
    instructors,
    activeInstructorId,
    setActiveInstructorId,
    studentGroups,
    schedules,
    students,
    attendanceRecords,
    recordAttendance,
  } = useERP();

  const currentInstructor = instructors.find((i) => i.id === activeInstructorId) || instructors[0];

  // Assigned classes
  const myClasses = studentGroups.filter((g) => g.instructorId === currentInstructor.id);

  // Today's sessions
  const todayStr = '2026-10-28';
  const todaySessions = schedules.filter(
    (s) => s.instructorId === currentInstructor.id && s.scheduleDate === todayStr
  );

  // Active session for attendance recording
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const activeSession = schedules.find((s) => s.id === activeSessionId);
  const activeClassGroup = activeSession
    ? studentGroups.find((g) => g.id === activeSession.studentGroupId)
    : null;

  // Roster students for active attendance session
  const rosterStudents = activeClassGroup
    ? students.filter((s) => activeClassGroup.studentIds.includes(s.id))
    : [];

  const [studentMarks, setStudentMarks] = useState<Record<string, 'Present' | 'Absent' | 'Leave'>>({});
  const [attendanceFeedback, setAttendanceFeedback] = useState<string | null>(null);

  const handleOpenAttendance = (session: typeof schedules[0]) => {
    setActiveSessionId(session.id);
    const grp = studentGroups.find((g) => g.id === session.studentGroupId);
    const initialMarks: Record<string, 'Present' | 'Absent' | 'Leave'> = {};
    if (grp) {
      grp.studentIds.forEach((sid) => {
        initialMarks[sid] = 'Present'; // default to Present for convenience
      });
    }
    setStudentMarks(initialMarks);
    setAttendanceFeedback(null);
  };

  const handleSaveAttendance = () => {
    if (!activeSession) return;
    const records = Object.entries(studentMarks).map(([studentId, status]) => {
      const stu = students.find((s) => s.id === studentId);
      return {
        studentId,
        studentName: stu?.name || studentId,
        status,
      };
    });

    recordAttendance(activeSession.id, records);
    setAttendanceFeedback('Submitted native Student Attendance facts successfully.');
    setTimeout(() => {
      setActiveSessionId(null);
      setAttendanceFeedback(null);
    }, 1500);
  };

  return (
    <div className="space-y-6">
      {/* Header & Instructor Switcher */}
      <div className="bg-white p-6 rounded-lg border border-[#e3e8ef] shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#1f5fa8] bg-[#eaf1fa] px-2 py-0.5 rounded border border-[#c5d9f0]">
              Audience: Instructor / Faculty
            </span>
            <span className="text-[11px] text-[#5b6779] font-mono">
              toefl_house.desk.teacher.work
            </span>
          </div>
          <h1 className="text-xl font-bold text-[#1b2430]">TOEFL House Teacher Desk</h1>
          <p className="text-xs text-[#5b6779] mt-0.5 max-w-2xl">
            My classes, today's sessions, attendance recording, students and compensation facts — assigned classes only.
          </p>
        </div>

        {/* Switch Active Instructor */}
        <div className="flex items-center gap-2 bg-[#f8fafc] border border-[#cdd5e0] px-3 py-1.5 rounded-md self-start md:self-auto">
          <UserCheck className="w-4 h-4 text-[#1f5fa8]" />
          <div className="text-xs">
            <span className="text-[#8792a3] text-[10px] block font-mono">Active Instructor</span>
            <select
              value={activeInstructorId}
              onChange={(e) => setActiveInstructorId(e.target.value)}
              className="font-bold text-[#1b2430] bg-transparent focus:outline-none text-xs"
            >
              {instructors.map((ins) => (
                <option key={ins.id} value={ins.id}>
                  {ins.name} ({ins.branch})
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Teaching Overview Tiles */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard
          label="My Assigned Classes"
          value={myClasses.length}
          definition="Cohorts currently allocated to your instructor profile."
          source="TH Teaching Assignment"
          badge={{ text: 'Assigned', tone: 'info' }}
        />
        <MetricCard
          label="Today's Sessions"
          value={todaySessions.length}
          definition="Course schedule timetable slots assigned to you for today."
          source="Course Schedule"
          badge={{ text: 'Today', tone: 'ok' }}
        />
        <MetricCard
          label="Contract Model"
          value={currentInstructor.contractType}
          definition="Contract framework (Hourly, Fixed-Term, or Per-Student)."
          source="TH Instructor Contract"
          badge={{ text: currentInstructor.status, tone: 'ok' }}
        />
        <MetricCard
          label="Payroll Status"
          value={currentInstructor.payrollStatus}
          definition="Monthly compensation readiness for native HRMS payroll entry."
          source="HRMS Payroll"
          badge={{ text: 'Verified', tone: 'ok' }}
        />
      </section>

      {/* Today's Teaching Sessions */}
      <section className="bg-white rounded-lg border border-[#e3e8ef] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#f1f4f8] flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-[#1b2430]">
              Today's Teaching Schedule ({todayStr})
            </h2>
            <p className="text-xs text-[#5b6779] mt-0.5">
              Sessions requiring your attendance and classroom instruction.
            </p>
          </div>
          <span className="text-xs font-mono text-[#5b6779]">
            {todaySessions.length} session(s)
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#f8fafc] text-[#5b6779] uppercase font-semibold text-[10px] tracking-wider border-b border-[#e3e8ef]">
              <tr>
                <th className="px-4 py-3">Class Group</th>
                <th className="px-4 py-3">Time & Room</th>
                <th className="px-4 py-3">Module Skill Focus</th>
                <th className="px-4 py-3">Roster Size</th>
                <th className="px-4 py-3">Attendance State</th>
                <th className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f1f4f8]">
              {todaySessions.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-[#8792a3]">
                    No sessions scheduled for {currentInstructor.name} today.
                  </td>
                </tr>
              ) : (
                todaySessions.map((session) => (
                  <tr key={session.id} className="hover:bg-[#f8fafc] transition-colors">
                    <td className="px-4 py-3 font-semibold text-[#1b2430]">
                      {session.studentGroupName}
                    </td>
                    <td className="px-4 py-3 font-mono">
                      <div>{session.fromTime} – {session.toTime}</div>
                      <div className="text-[10px] text-[#8792a3]">{session.room}</div>
                    </td>
                    <td className="px-4 py-3 text-[#5b6779]">
                      {session.courseSkill}
                    </td>
                    <td className="px-4 py-3 font-mono text-[#0f2a44] font-bold">
                      {session.attendanceTotalCount || 14} students
                    </td>
                    <td className="px-4 py-3">
                      {session.attendanceRecorded ? (
                        <div className="flex items-center gap-1.5 text-[#1a7f4b] font-semibold">
                          <CheckCircle className="w-4 h-4" />
                          <span>Submitted ({session.attendancePresentCount}/{session.attendanceTotalCount})</span>
                        </div>
                      ) : (
                        <span className="text-[#9a6700] bg-[#fdf3dc] px-2 py-0.5 rounded border border-[#f5d98a] text-[10px] font-bold uppercase">
                          Unrecorded
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => handleOpenAttendance(session)}
                        className={`px-3 py-1 rounded text-[11px] font-semibold ${
                          session.attendanceRecorded
                            ? 'bg-[#f1f4f8] text-[#5b6779] hover:bg-[#e3e8ef]'
                            : 'bg-[#1f5fa8] hover:bg-[#164a85] text-white shadow-xs'
                        }`}
                      >
                        {session.attendanceRecorded ? 'Review Attendance' : 'Record Attendance'}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Attendance Recording Sheet Modal */}
      {activeSession && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-lg shadow-xl border border-[#cdd5e0] w-full max-w-xl overflow-hidden flex flex-col max-h-[85vh]">
            <div className="bg-[#0f2a44] text-white px-6 py-4 flex items-center justify-between">
              <div>
                <span className="text-[10px] font-mono text-white/70 uppercase">
                  Class Attendance Roster · {activeSession.scheduleDate}
                </span>
                <h3 className="text-base font-bold">{activeSession.studentGroupName}</h3>
                <p className="text-xs text-white/80 mt-0.5">
                  {activeSession.fromTime} – {activeSession.toTime} ({activeSession.room})
                </p>
              </div>
              <button
                onClick={() => setActiveSessionId(null)}
                className="text-white/60 hover:text-white"
              >
                ✕
              </button>
            </div>

            <div className="p-6 overflow-y-auto flex-1 space-y-4">
              {attendanceFeedback && (
                <div className="p-3 bg-[#e7f4ec] text-[#1a7f4b] border border-[#a8d5ba] rounded font-semibold text-xs flex items-center gap-2">
                  <CheckCircle className="w-4 h-4" />
                  <span>{attendanceFeedback}</span>
                </div>
              )}

              <div className="flex items-center justify-between text-xs">
                <span className="text-[#5b6779]">
                  Mark present, absent or authorized leave per institute policy:
                </span>
                <button
                  type="button"
                  onClick={() => {
                    const allPresent: Record<string, 'Present' | 'Absent' | 'Leave'> = {};
                    rosterStudents.forEach((s) => (allPresent[s.id] = 'Present'));
                    setStudentMarks(allPresent);
                  }}
                  className="text-[#1f5fa8] hover:underline font-semibold"
                >
                  Mark All Present
                </button>
              </div>

              <div className="border border-[#e3e8ef] rounded-md overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[#f8fafc] text-[#5b6779] border-b border-[#e3e8ef] text-[10px] uppercase font-semibold">
                    <tr>
                      <th className="px-4 py-2.5">Student ID & Name</th>
                      <th className="px-4 py-2.5 text-right">Attendance Mark</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#f1f4f8]">
                    {rosterStudents.map((s) => {
                      const currentMark = studentMarks[s.id] || 'Present';
                      return (
                        <tr key={s.id} className="hover:bg-[#f8fafc]">
                          <td className="px-4 py-2.5">
                            <div className="font-bold text-[#1b2430]">{s.name}</div>
                            <div className="text-[10px] text-[#8792a3] font-mono">{s.id}</div>
                          </td>
                          <td className="px-4 py-2.5 text-right">
                            <div className="inline-flex rounded-md shadow-2xs">
                              {(['Present', 'Absent', 'Leave'] as const).map((opt) => (
                                <button
                                  key={opt}
                                  type="button"
                                  onClick={() =>
                                    setStudentMarks((prev) => ({ ...prev, [s.id]: opt }))
                                  }
                                  className={`px-2.5 py-1 text-[11px] font-semibold border ${
                                    currentMark === opt
                                      ? opt === 'Present'
                                        ? 'bg-[#1a7f4b] text-white border-[#1a7f4b]'
                                        : opt === 'Absent'
                                        ? 'bg-[#b42318] text-white border-[#b42318]'
                                        : 'bg-[#9a6700] text-white border-[#9a6700]'
                                      : 'bg-white text-[#5b6779] border-[#cdd5e0] hover:bg-[#f1f4f8]'
                                  } first:rounded-l last:rounded-r`}
                                >
                                  {opt}
                                </button>
                              ))}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="bg-[#f8fafc] border-t border-[#e3e8ef] px-6 py-3 flex justify-between items-center text-xs">
              <span className="text-[#8792a3] text-[11px]">
                Submits native Student Attendance records
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setActiveSessionId(null)}
                  className="px-3 py-1.5 border border-[#cdd5e0] rounded text-[#5b6779] font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSaveAttendance}
                  className="px-4 py-1.5 bg-[#1f5fa8] hover:bg-[#164a85] text-white rounded font-semibold shadow-xs"
                >
                  Save Attendance
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* My Assigned Class Cohorts */}
      <section className="bg-white rounded-lg border border-[#e3e8ef] shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-[#f1f4f8] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-[#1f5fa8]" />
            <h2 className="text-sm font-bold text-[#1b2430]">
              My Active Class Cohorts
            </h2>
          </div>
          <span className="text-xs font-mono text-[#5b6779]">
            {myClasses.length} assigned class(es)
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#f8fafc] text-[#5b6779] uppercase font-semibold text-[10px] tracking-wider border-b border-[#e3e8ef]">
              <tr>
                <th className="px-4 py-3">Group Name</th>
                <th className="px-4 py-3">Program & Level</th>
                <th className="px-4 py-3">Delivery Mode</th>
                <th className="px-4 py-3">Roster Size</th>
                <th className="px-4 py-3">Dates</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#f1f4f8]">
              {myClasses.map((cls) => (
                <tr key={cls.id} className="hover:bg-[#f8fafc] transition-colors">
                  <td className="px-4 py-3 font-semibold text-[#1b2430]">
                    {cls.groupName}
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-bold text-[#1b2430]">{cls.programCode}</div>
                    <div className="text-[11px] text-[#5b6779]">{cls.levelName}</div>
                  </td>
                  <td className="px-4 py-3">
                    <span className="bg-[#f1f4f8] text-[#5b6779] px-2 py-0.5 rounded text-[10px] font-semibold">
                      {cls.deliveryMode}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono">
                    <span className="font-bold text-[#0f2a44]">
                      {cls.currentStrength} / {cls.maxStrength}
                    </span>{' '}
                    students
                  </td>
                  <td className="px-4 py-3 text-[11px] text-[#5b6779] font-mono">
                    {cls.classStartDate} → {cls.classEndDate}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={cls.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};
