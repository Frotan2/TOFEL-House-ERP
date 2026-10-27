"""Attendance drill-down must use the existing scoped projection, not native CRUD."""
import unittest
from unittest.mock import patch

from tests.desk.test_desk_contract import _import_desk


class AttendanceSourceTests(unittest.TestCase):
    def test_audience_denied_before_read(self):
        module = _import_desk("academic", roles={"Reception"})
        with patch.object(module, "project_rows") as read:
            with self.assertRaises(module.frappe.PermissionError):
                module.attendance_records("CLASS-A")
            read.assert_not_called()

    def test_scoped_projection_bound_and_group_filter(self):
        module = _import_desk("academic", roles={"Academic Manager"})
        rows = [{"name": str(i)} for i in range(module.LIMIT_QUEUES + 1)]
        with patch.object(module, "project_rows", return_value=rows) as read:
            result = module.attendance_records("CLASS-A")
        self.assertEqual(len(result["rows"]), module.LIMIT_QUEUES)
        self.assertTrue(result["truncated"])
        args, kwargs = read.call_args
        self.assertEqual(args[:2], ("academic", "Student Attendance"))
        self.assertEqual(kwargs["filters"], {"docstatus": 1, "student_group": "CLASS-A"})
        self.assertEqual(kwargs["limit"], module.LIMIT_QUEUES + 1)
        self.assertNotIn("scope", kwargs, "Native Branch scope must remain enabled")
        self.assertEqual(set(args[2]), {"name", "student", "student_group", "course_schedule", "date", "status"})

    def test_invalid_class_refused_without_read(self):
        module = _import_desk("academic", roles={"Academic Manager"})
        with patch.object(module, "project_rows") as read:
            for value in ({"x": 1}, "", "x" * 141):
                with self.assertRaises(module.frappe.ValidationError):
                    module.attendance_records(value)
            read.assert_not_called()

    def test_enrollment_audience_and_complete_waiting_scope(self):
        denied = _import_desk("academic", roles={"Reception"})
        with patch.object(denied, "project_rows") as read:
            with self.assertRaises(denied.frappe.PermissionError):
                denied.enrollment_records()
            read.assert_not_called()
        module = _import_desk("academic", roles={"Academic Manager"})
        enrollment = {"name": "ENR-A", "student": "STU-A", "program": "P", "academic_year": "Y"}
        group = {"name": "CLASS-A", "program": "P", "academic_year": "Y", "th_class_status": "Active"}
        with patch.object(module, "project_rows", side_effect=[
                [enrollment], [group], [{"parent": "CLASS-A", "student": "STU-A", "active": 1}]]) as read:
            self.assertEqual(module.enrollment_records(1)["rows"], [])
            self.assertTrue(all("scope" not in call.kwargs for call in read.call_args_list))
        with patch.object(module, "project_rows", side_effect=[[enrollment], [group], []]):
            self.assertEqual(module.enrollment_records("1")["rows"], [enrollment])
        with patch.object(module, "project_rows", side_effect=[[enrollment] * module.BOUNCE_WINDOW, [], []]):
            with self.assertRaises(module.frappe.ValidationError):
                module.enrollment_records(1)
