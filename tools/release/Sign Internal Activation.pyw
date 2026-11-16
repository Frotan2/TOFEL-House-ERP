"""Offline GUI for one detached internal activation approval."""

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SIGNER = Path(__file__).resolve().with_name("create_update_bundle.py")
DOCUMENT_TYPE = "toefl-house-erp-internal-activation"
MAX_REQUEST_BYTES = 256 * 1024
ROLES = {
    "Course Owner": ("course-owner", "internal-activation.owner.sig.json"),
    "General Manager": ("general-manager", "internal-activation.reviewer.sig.json"),
}
REQUIRED_DIGESTS = {
    "source_revision": r"[a-f0-9]{40}",
    "image_id": r"sha256:[a-f0-9]{64}",
    "internal_setup_sha256": r"[a-f0-9]{64}",
    "internal_installation_id": r"[a-f0-9]{32}",
}


def _regular_file(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError("Select a regular file from the approved offline location.")


def export_public_record(role_name, identity, key_id, private_key, openssl, output_dir, passphrase):
    if role_name not in ROLES or not identity.strip() or len(identity) > 140:
        raise ValueError("Enter your approved name and role.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", key_id):
        raise ValueError("Use 3–64 lowercase letters, numbers, dots, underscores or hyphens; begin with a letter or number.")
    _regular_file(private_key)
    _regular_file(openssl)
    if not output_dir.is_dir() or output_dir.is_symlink():
        raise ValueError("Choose the public record output folder.")
    if len(passphrase) > 4096 or any(char in passphrase for char in (b"\r", b"\n", b"\0")):
        raise ValueError("The passphrase contains an unsupported character or is too long.")
    role, _ = ROLES[role_name]
    output = output_dir / f"internal-activation.{role}.public.json"
    if output.exists():
        raise ValueError("That public record already exists. Choose a different output folder.")
    with tempfile.TemporaryDirectory(prefix="toefl-public-key-") as temporary:
        record = Path(temporary) / "key.json"
        completed = subprocess.run(
            [sys.executable, "-I", str(SIGNER), "trust-store", "--key-id", key_id,
             "--internal-approver-role", role, "--internal-approver-identity", identity,
             "--private-key", str(private_key), "--openssl", str(openssl),
             "--out", str(record), "--passphrase-stdin"],
            input=passphrase, capture_output=True, check=False, timeout=45,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode:
            raise ValueError("Public record export failed. Check your approved RSA key, passphrase, and OpenSSL.")
        data = record.read_bytes()
        with output.open("xb") as file:
            file.write(data)
    return output, hashlib.sha256(data).hexdigest()


def load_request(path):
    _regular_file(path)
    with path.open("rb") as file:
        raw = file.read(MAX_REQUEST_BYTES + 1)
    if not raw or len(raw) > MAX_REQUEST_BYTES:
        raise ValueError("Select a valid activation request from the institute.")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise ValueError("The activation request is unreadable.") from None
    if (not isinstance(document, dict)
            or document.get("document_type") != DOCUMENT_TYPE
            or document.get("schema_version") != 2
            or document.get("scope") != "internal-activation"
            or document.get("operation") != "internal-activation"):
        raise ValueError("Select the two-approver internal activation request.")
    installation = document.get("installation")
    if not isinstance(installation, dict) or any(
        not isinstance(installation.get(field), str) or not re.fullmatch(pattern, installation[field])
        for field, pattern in REQUIRED_DIGESTS.items()
    ):
        raise ValueError("The request is missing its exact installation identity.")
    if (not re.fullmatch(r"[a-f0-9]{64}", str(document.get("backup_receipt_sha256", "")))
            or not re.fullmatch(r"[a-f0-9]{32}", str(document.get("request_id", "")))
            or not re.fullmatch(r"[a-zA-Z0-9.-]{1,253}", str(document.get("site", "")))):
        raise ValueError("The request is missing its site, backup or one-time request identity.")
    if any(document.get(field) is not True for field in
           ("windows_host_acceptance_verified", "owner_key_custody_verified", "rehearsal_restore_verified")):
        raise ValueError("The request is missing required Windows and recovery acceptance.")
    try:
        issued, expires = (
            datetime.strptime(document[field], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            for field in ("issued_utc", "expires_utc")
        )
    except (ValueError, TypeError, KeyError):
        raise ValueError("The request has an invalid UTC validity window.") from None
    if not issued <= datetime.now(timezone.utc) < expires:
        raise ValueError("The request is outside its approved validity window. Ask for a new request.")
    approvals = document.get("approvals")
    if not isinstance(approvals, list) or len(approvals) != 2 or any(
        not isinstance(entry, dict) for entry in approvals
    ):
        raise ValueError("The request must name exactly two approvers.")
    by_role = {entry.get("approver_role"): entry for entry in approvals
               if isinstance(entry.get("approver_role"), str)}
    if by_role.keys() != {role for role, _ in ROLES.values()}:
        raise ValueError("The request must name the Course Owner and General Manager.")
    for approver in approvals:
        identity = approver.get("approver_identity")
        key_id = approver.get("key_id")
        if (not isinstance(identity, str) or not 1 <= len(identity) <= 140
                or identity != identity.strip() or not identity.isprintable()
                or not isinstance(key_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", key_id)):
            raise ValueError("The request has an invalid approver identity or key ID.")
    if (len({item["approver_identity"].casefold() for item in approvals}) != 2
            or len({item["key_id"] for item in approvals}) != 2):
        raise ValueError("The request requires two people and two different registered keys.")
    return raw, document, by_role


def sign_request(path, expected_digest, role_name, private_key, openssl, output_dir, passphrase):
    raw, _document, approvers = load_request(path)
    digest = hashlib.sha256(raw).hexdigest()
    if not re.fullmatch(r"[a-f0-9]{64}", expected_digest) or digest != expected_digest:
        raise ValueError("The selected request does not match the independently confirmed SHA-256.")
    role, filename = ROLES[role_name]
    key_id = approvers[role]["key_id"]
    _regular_file(private_key)
    _regular_file(openssl)
    if not output_dir.is_dir() or output_dir.is_symlink():
        raise ValueError("Choose your offline signature output folder.")
    output = output_dir / filename
    if output.exists():
        raise ValueError("That signature already exists. Choose a different output folder.")
    if len(passphrase) > 4096 or any(char in passphrase for char in (b"\r", b"\n", b"\0")):
        raise ValueError("The passphrase contains an unsupported character or is too long.")
    with tempfile.TemporaryDirectory(prefix="toefl-approval-") as temporary:
        snapshot = Path(temporary) / "internal-activation.json"
        detached = Path(temporary) / filename
        snapshot.write_bytes(raw)
        completed = subprocess.run(
            [sys.executable, "-I", str(SIGNER), "sign", "--document", str(snapshot),
             "--document-type", "internal-activation", "--key-id", key_id,
             "--private-key", str(private_key), "--openssl", str(openssl),
             "--out", str(detached), "--passphrase-stdin"],
            input=passphrase, capture_output=True, check=False, timeout=45,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode:
            raise ValueError("Signing failed. Check that you selected your registered RSA key, its "
                             "correct passphrase and the approved OpenSSL executable.")
        approval = detached.read_bytes()
        # Publish only the outcome which the existing signing tool verified.
        with output.open("xb") as file:
            file.write(approval)
    return output


class SigningWindow:
    def __init__(self, root):
        self.root = root
        self.request = None
        self.private_key = None
        self.openssl = None
        self.output_dir = None
        self.details = tk.StringVar(value="Choose the institute's activation request.")
        self.role = tk.StringVar()
        self.approver = tk.StringVar(value="Choose the role you hold in this request.")
        self.expected_digest = tk.StringVar()
        self.passphrase = tk.StringVar()

        root.title("TOEFL House ERP — sign one activation approval")
        root.minsize(710, 440)
        layout = ttk.Frame(root, padding=18)
        layout.pack(fill="both", expand=True)
        layout.columnconfigure(1, weight=1)
        ttk.Label(layout, text=("Use your own offline signing computer and registered key. "
                                "Confirm the request SHA-256 with the institute before signing."),
                          wraplength=650).grid(row=0, column=0, columnspan=2,
                                                                                     sticky="w", pady=(0, 10))
        ttk.Button(layout, text="Choose activation request", command=self.choose_request).grid(
            row=1, column=0, sticky="w")
        ttk.Label(layout, textvariable=self.details, wraplength=615, justify="left").grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(6, 10))
        ttk.Label(layout, text="Independently confirmed request SHA-256").grid(row=3, column=0, sticky="w", padx=(0, 10))
        ttk.Entry(layout, textvariable=self.expected_digest, width=67).grid(row=3, column=1, sticky="ew")
        ttk.Label(layout, text="Your role").grid(row=4, column=0, sticky="w")
        roles = ttk.Combobox(layout, textvariable=self.role, values=tuple(ROLES), state="readonly")
        roles.grid(row=4, column=1, sticky="w", pady=6)
        roles.bind("<<ComboboxSelected>>", lambda _event: self.show_approver())
        ttk.Label(layout, textvariable=self.approver, wraplength=450).grid(row=5, column=1, sticky="w")

        choices = (
            ("private_key", "Choose your private RSA key", "Private key selected",
             [("RSA key", "*.pem *.key")]),
            ("openssl", "Choose approved OpenSSL", "OpenSSL selected", [("Windows executable", "*.exe")]),
            ("output_dir", "Choose output folder", "Output folder selected", None),
        )
        for row, (attribute, label, selected, types) in enumerate(choices, start=6):
            state = tk.StringVar(value="Awaiting selection")
            ttk.Button(layout, text=label,
                       command=lambda a=attribute, s=state, t=types, m=selected: self.choose(a, s, t, m)).grid(
                row=row, column=0, sticky="w", pady=4)
            ttk.Label(layout, textvariable=state).grid(row=row, column=1, sticky="w")
        ttk.Label(layout, text="Key passphrase (if used)").grid(row=9, column=0, sticky="w", pady=7)
        ttk.Entry(layout, textvariable=self.passphrase, show="*").grid(row=9, column=1, sticky="ew")
        self.sign_button = ttk.Button(layout, text="Sign my approval", command=self.sign)
        self.sign_button.grid(row=10, column=1, sticky="e", pady=(8, 0))
        self.export_button = ttk.Button(layout, text="Export my public key", command=self.export)
        self.export_button.grid(row=10, column=0, sticky="w", pady=(8, 0))

    def choose_request(self):
        chosen = filedialog.askopenfilename(parent=self.root, filetypes=[("Activation request", "*.json")])
        if not chosen:
            return
        self.request = None
        self.expected_digest.set("")
        try:
            path = Path(chosen)
            raw, document, self.approvers = load_request(path)
        except (ValueError, OSError) as error:
            self.details.set("Choose a valid activation request.")
            self.approver.set("Choose a valid request to see its named approvers.")
            self.report_error(error)
            return
        self.request = path
        self.reviewed_digest = hashlib.sha256(raw).hexdigest()
        self.details.set(
            f"Site: {document['site']}    Expires (UTC): {document['expires_utc']}\n"
            f"Request SHA-256: {self.reviewed_digest}\n"
            f"Installer SHA-256: {document['installation']['internal_setup_sha256']}\n"
            f"Verified backup receipt SHA-256: {document['backup_receipt_sha256']}"
        )
        self.show_approver()

    def show_approver(self):
        if self.request and self.role.get() in ROLES:
            entry = self.approvers[ROLES[self.role.get()][0]]
            self.approver.set(f"{entry['approver_identity']} ({entry['key_id']})")

    def choose(self, attribute, state, filetypes, message):
        if filetypes is None:
            selected = filedialog.askdirectory(parent=self.root, mustexist=True)
        else:
            selected = filedialog.askopenfilename(parent=self.root, filetypes=filetypes + [("All files", "*")])
        if selected:
            setattr(self, attribute, Path(selected))
            state.set(message)

    def report_error(self, error):
        message = str(error) if isinstance(error, ValueError) else "The selected file or tool could not be used."
        messagebox.showerror("Approval was not signed", message, parent=self.root)

    def export(self):
        if not all((self.private_key, self.openssl, self.output_dir, self.role.get() in ROLES)):
            messagebox.showerror("Public record not exported",
                                 "Choose your role, private key, approved OpenSSL, and output folder.", parent=self.root)
            return
        identity = simpledialog.askstring("Approved identity", "Enter your approved full name:", parent=self.root)
        if identity is None:
            return
        key_id = simpledialog.askstring("Key ID", "Enter a unique key ID agreed with the institute:", parent=self.root)
        if key_id is None:
            return
        passphrase = self.passphrase.get().encode("utf-8")
        self.passphrase.set("")
        self.export_button.state(["disabled"])
        self.root.update_idletasks()
        try:
            output, digest = export_public_record(self.role.get(), identity.strip(), key_id.strip(),
                                                  self.private_key, self.openssl, self.output_dir, passphrase)
        except (ValueError, OSError, subprocess.TimeoutExpired) as error:
            messagebox.showerror("Public record not exported",
                                 str(error) if isinstance(error, ValueError) else "The selected file or tool could not be used.",
                                 parent=self.root)
        else:
            self.root.clipboard_clear()
            self.root.clipboard_append(digest)
            messagebox.showinfo("Public record saved",
                                f"Send only {output.name}. Confirm this SHA-256 separately with the institute "
                                f"administrator. It has been copied to the clipboard.\n\n{digest}",
                                parent=self.root)
        finally:
            self.export_button.state(["!disabled"])

    def sign(self):
        if not all((self.request, self.private_key, self.openssl, self.output_dir, self.role.get() in ROLES)):
            self.report_error(ValueError("Choose the request, your role and key, OpenSSL, and the output folder."))
            return
        digest = self.expected_digest.get().strip().lower()
        if digest != self.reviewed_digest:
            self.report_error(ValueError("Enter the independently confirmed SHA-256 of this exact request."))
            return
        if not messagebox.askyesno(
            "Confirm your approval", f"Sign the displayed request as {self.role.get()} with your own registered key?",
            parent=self.root,
        ):
            return
        passphrase = self.passphrase.get().encode("utf-8")
        self.passphrase.set("")
        self.sign_button.state(["disabled"])
        self.root.update_idletasks()
        try:
            output = sign_request(self.request, digest, self.role.get(), self.private_key,
                                  self.openssl, self.output_dir, passphrase)
        except (ValueError, OSError, subprocess.TimeoutExpired) as error:
            self.report_error(error)
        else:
            messagebox.showinfo("Approval signature saved",
                                f"Return only {output.name} with the unchanged request. "
                                "The other approver must sign independently.", parent=self.root)
        finally:
            self.sign_button.state(["!disabled"])


if __name__ == "__main__":
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk

    window = tk.Tk()
    SigningWindow(window)
    window.mainloop()
