"""Request-local membership validation without patching Education globals."""
import frappe
from education.education.doctype.student_attendance.student_attendance import StudentAttendance

from toefl_house.security import require_operational, teaching_command_active


class THStudentAttendance(StudentAttendance):
    def validate_student(self):
        require_operational()
        if not teaching_command_active("Student Attendance"):
            # Keep native roster-read permissions for callers outside an
            # authorized command; ignore_permissions never grants this seam.
            return super().validate_student()
        group = (frappe.db.get_value("Course Schedule", self.course_schedule, "student_group")
                 if self.course_schedule else self.student_group)
        if not group or not self.student:
            raise frappe.ValidationError("A scheduled group and student are required for attendance")
        member = frappe.db.sql(
            "select name from `tabStudent Group Student` "
            "where parent=%s and student=%s and active=1 limit 1",
            (group, self.student),
        )
        if not member:
            raise frappe.ValidationError("Student is not an active member of the scheduled group")
