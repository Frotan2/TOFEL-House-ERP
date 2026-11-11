frappe.pages["th-course-assessment"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({parent: wrapper, title: __("Course assessment"), single_column: true});
    const root = $("<div class='p-4'></div>").appendTo(page.body);
    const roles = new Set(frappe.user_roles || []);
    const academic = roles.has("Academic Manager");
    const instructor = roles.has("Instructor");
    const endpoint = "toefl_house.academic.assessment.";
    let state = null, pending = false, uncertain = false;
    $("<p class='text-muted'></p>").text(__("Load the class book to enter marks or review its pinned policy and published results.")).appendTo(root);
    const toolbar = $("<div class='d-flex flex-wrap align-items-end' style='gap:12px'></div>").appendTo(root);
    const reference = frappe.ui.form.make_control({
        parent: $("<div style='min-width:260px'></div>").appendTo(toolbar),
        df: {fieldname: "book", label: __("Assessment book"), fieldtype: "Data"}, render_input: true,
    });
    const notice = $("<p role='status' class='mt-3'></p>").appendTo(root);
    const content = $("<div></div>").appendTo(root);
    let controls = [];
    function button(parent, label, action) {
        const control = $("<button type='button' class='btn btn-default'></button>").text(__(label)).appendTo(parent).on("click", action);
        controls.push(control);
        return control;
    }
    function busy() {
        controls.forEach(control => control.prop("disabled", pending || uncertain));
        loadButton.prop("disabled", pending);
    }
    async function post(method, args) {
        if (pending || uncertain) return null;
        pending = true;
        busy();
        notice.text(__("Saving. Wait for server confirmation."));
        try {
            const response = await fetch("/api/method/" + method, {
                method: "POST", credentials: "same-origin",
                headers: {"Content-Type": "application/json", "X-Frappe-CSRF-Token": frappe.csrf_token},
                body: JSON.stringify({request_key: crypto.randomUUID(), ...args}),
            });
            const body = await response.json();
            if (response.status >= 400 && response.status < 500) {
                notice.text(String(body.exception || __("The server refused this action.")).slice(0, 600));
                return null;
            }
            if (!response.ok || body.exc || !body.message) throw new Error(__("Outcome unknown."));
            notice.text(__("Saved and confirmed by the server."));
            return body.message;
        } catch (error) {
            uncertain = true;
            notice.text(String(error.message || __("Outcome unknown.")) + " " + __("Load the book to check its current state before continuing."));
            return null;
        } finally {
            pending = false;
            busy();
        }
    }
    async function load() {
        if (pending) return;
        const book = reference.get_value();
        if (!book) { notice.text(__("Enter an assessment book reference.")); return; }
        pending = true;
        busy();
        try {
            const response = await frappe.call({method: endpoint + "assessment_state", type: "GET", args: {book}});
            state = response.message;
            uncertain = false;
            render();
            notice.text(__("Current book loaded."));
        } catch (_error) {
            uncertain = true;
            content.empty();
            notice.text(__("The book could not be loaded. Check the reference and your access."));
        } finally {
            pending = false;
            busy();
        }
    }
    const loadButton = button(toolbar, "Load book", load);
    if (academic) button(toolbar, "Open class book", () => {
        const dialog = new frappe.ui.Dialog({
            title: __("Open class assessment book"),
            fields: [
                {fieldname: "student_group", label: __("Class"), fieldtype: "Data", reqd: 1},
                {fieldname: "policy", label: __("Approved assessment policy code"), fieldtype: "Data", reqd: 1},
                {fieldname: "assessment_plan", label: __("Native Assessment Plan (optional)"), fieldtype: "Data"},
            ],
            primary_action_label: __("Open book"),
            async primary_action(values) {
                $(dialog.body).find(".th-assessment-refusal").remove();
                dialog.get_primary_btn().prop("disabled", true);
                const result = await post(endpoint + "open_assessment_book", values);
                if (result) { await reference.set_value(result.name); dialog.hide(); await load(); }
                else if (uncertain) dialog.hide();
                else {
                    $("<p class='alert alert-danger th-assessment-refusal' role='alert'></p>")
                        .text(notice.text()).prependTo(dialog.body);
                    dialog.get_primary_btn().prop("disabled", false);
                }
            },
        });
        dialog.show();
    });
    async function transition(method, args = {}) {
        const result = await post(endpoint + method, {book: state.name, ...args});
        if (result) await load();
    }
    function render() {
        content.empty();
        controls = controls.filter(control => root[0].contains(control[0]));
        $("<h3></h3>").text(state.student_group).appendTo(content);
        $("<p></p>").text([state.name, state.status, state.policy, state.policy_effective_from].join(" · ")).appendTo(content);
        const table = $("<table class='table table-bordered'></table>").appendTo(content);
        const header = $("<tr></tr>").appendTo($("<thead></thead>").appendTo(table));
        ["Student", "Component", "Maximum", "Mark", "Missing reason"].forEach(label => $("<th scope='col'></th>").text(__(label)).appendTo(header));
        const body = $("<tbody></tbody>").appendTo(table), entries = [];
        const editable = instructor && ["Open", "Returned"].includes(state.status);
        for (const student of state.students || []) for (const component of state.components || []) {
            const saved = (state.marks || []).find(row => row.student === student && row.component === component.code);
            const row = $("<tr></tr>").appendTo(body);
            [student, component.code, component.maximum_score].forEach(value => $("<td></td>").text(String(value)).appendTo(row));
            const locked = !editable || Boolean(saved && state.status === "Open");
            const mark = $("<input type='number' class='form-control' min='0' step='any'>")
                .attr("max", component.maximum_score).attr("aria-label", student + " " + component.code + " mark")
                .val(saved && saved.mark != null ? saved.mark : "").prop("disabled", locked).appendTo($("<td></td>").appendTo(row));
            const missing = $("<input type='text' class='form-control' maxlength='300'>")
                .attr("aria-label", student + " " + component.code + " missing reason")
                .val(saved ? saved.missing_reason : "").prop("disabled", locked).appendTo($("<td></td>").appendTo(row));
            entries.push({student, component: component.code, maximum: component.maximum_score, saved, mark, missing});
        }
        const actions = $("<div class='d-flex flex-wrap mb-4' style='gap:8px'></div>").appendTo(content);
        if (editable) {
            button(actions, "Save marks", async () => {
                const marks = [];
                for (const entry of entries) {
                    if (entry.saved && state.status === "Open") continue;
                    const raw = String(entry.mark.val()).trim(), reason = String(entry.missing.val()).trim();
                    if ((!raw && !reason) || (raw && reason)) { notice.text(__("Each row needs either a mark or a missing reason.")); return; }
                    const value = raw ? Number(raw) : null;
                    if (value != null && (!Number.isFinite(value) || value < 0 || value > entry.maximum)) { notice.text(__("Marks must be within the displayed maximum.")); return; }
                    marks.push({student: entry.student, component: entry.component, mark: value, missing_reason: reason});
                }
                if (!marks.length) { notice.text(__("All marks are already saved.")); return; }
                const result = await post(endpoint + "record_assessment_marks", {book: state.name, marks});
                if (result) await load();
            });
            button(actions, "Submit for review", () => transition("submit_assessment_book"));
        }
        if (academic && state.status === "Submitted") {
            button(actions, "Review book", () => transition("review_assessment_book", {action: "Review"}));
            button(actions, "Return for correction", () => frappe.prompt(
                {fieldname: "note", label: __("Correction required"), fieldtype: "Small Text", reqd: 1},
                values => transition("review_assessment_book", {action: "Return", note: values.note}), __("Return book"), __("Return")));
        }
        if (academic && state.status === "Reviewed") button(actions, "Approve book", () => transition("approve_assessment_book"));
        if (academic && state.status === "Approved") button(actions, "Publish results", () => frappe.confirm(
            __("Publish these approved results? Later changes require the academic correction process."), () => transition("publish_assessment_results")));
        if ((state.results || []).length) {
            $("<h3></h3>").text(__("Published results")).appendTo(content);
            for (const result of state.results) {
                const block = $("<div class='border rounded p-3 mb-2'></div>").appendTo(content);
                $("<p></p>").text([result.student, result.name, result.outcome, result.overall_percent + "%", result.grade_code || ""].join(" · ")).appendTo(block);
                if (academic) button(block, "Decide progression", () => frappe.prompt([
                    {fieldname: "decision", label: __("Decision"), fieldtype: "Select", options: "Promote\nRepeat\nRetake\nComplete", reqd: 1},
                    {fieldname: "reason", label: __("Decision evidence"), fieldtype: "Small Text", reqd: 1},
                ], async values => {
                    const outcome = await post("toefl_house.academic.progression.decide_progression", {academic_result: result.name, ...values});
                    if (outcome) $("<p></p>").text(__("Progression decision recorded") + " " + outcome.name).appendTo(block);
                }, __("Progression decision"), __("Save decision")));
            }
        }
    }
};
