app_name = "toefl_house"
app_title = "TOEFL House Placement (Synthetic Qualification)"
app_publisher = "TOEFL House"
app_description = "Synthetic-only governed placement content; no learner workflow"
app_email = "validation@example.test"
app_license = "MIT"
required_apps = ["erpnext", "education", "foundation_security"]
after_install = "toefl_house.install.after_install"
after_migrate = "toefl_house.install.after_migrate"
fixtures = [{"dt": "Role", "filters": [["name", "in", ["Placement Author", "Placement Publisher", "Placement Auditor", "Placement Invigilator"]]]}]
has_permission = {
    name: "toefl_house.permissions.has_permission"
    for name in ("TH Placement Item Revision", "TH Placement Key Revision", "TH Placement Audit Event",
                 "TH Placement Operation", "TH Placement Blueprint Revision", "TH Placement Policy Revision",
                 "TH Placement Case", "TH Placement Attempt", "TH Placement Form Manifest",
                 "TH Placement Exposure", "TH Placement Allocation Guard",
                 "TH Placement Response")
}
permission_query_conditions = {
    name: "toefl_house.permissions.query_" + suffix
    for name, suffix in (
        ("TH Placement Item Revision", "item"), ("TH Placement Key Revision", "key"),
        ("TH Placement Audit Event", "audit"), ("TH Placement Operation", "operation"),
        ("TH Placement Blueprint Revision", "blueprint"), ("TH Placement Policy Revision", "policy"),
        ("TH Placement Case", "case"), ("TH Placement Attempt", "attempt"),
        ("TH Placement Form Manifest", "manifest"), ("TH Placement Exposure", "exposure"),
        ("TH Placement Allocation Guard", "guard"), ("TH Placement Response", "response"))
}
