// Small Windows GUI self-extractor. Payload is appended by the provider builder.
// An existing installation is serviced only by its separately authenticated
// updater. Factory extraction never replaces an existing site's data.
// The online-assisted internal kit compiles with /define:INTERNAL_UNSIGNED_SETUP.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Windows.Forms;

public class CustomerSetup {
    const int FooterSize = 48;
    const int MaxPayloadEntries = 4096;
    const long MaxUnpackedBytes = 48L * 1024 * 1024 * 1024;
    [STAThread]
    static void Main(string[] args) {
        bool verifyOnly = args.Length == 1 && args[0] == "--verify-payload";
        bool serviceRequested = args.Length == 1 && args[0] == "--service-existing";
        Application.EnableVisualStyles();
        string staging = null;
        Form progress = null;
        try {
            if (args.Length != 0 && !verifyOnly && !serviceRequested)
                throw new Exception("Unknown installer action.");
            if (verifyOnly) { VerifyExecutablePayload(); return; }
            string exe = Application.ExecutablePath;
            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string parent = Path.Combine(localAppData, "TOEFL House ERP");
            string target = Path.Combine(parent, "Customer");
            bool existing = Directory.Exists(target);
            if (serviceRequested && !existing)
                throw new Exception("No existing ERP installation was found. No site was created.");
            byte[] expected = new byte[32];
            long length;
            using (FileStream input = File.OpenRead(exe)) {
                long footer = FindFooter(input);
                input.Position = footer;
                using (BinaryReader reader = new BinaryReader(input, Encoding.UTF8, true)) {
                    if (Encoding.ASCII.GetString(reader.ReadBytes(8)) != "THSETUP1") throw new Exception("Invalid installer.");
                    length = reader.ReadInt64();
                    expected = reader.ReadBytes(32);
                }
                if (length <= 0 || length > footer) throw new Exception("Invalid installer payload.");
                string digest = BitConverter.ToString(expected).Replace("-", "").ToLowerInvariant();
                if (existing) {
                    string receipt = Path.Combine(target, ".payload-sha256");
                    string serviced = Path.Combine(target, ".servicing-setup-sha256");
                    if ((File.Exists(receipt) && File.ReadAllText(receipt).Trim() == digest) ||
                        (!serviceRequested && File.Exists(serviced) &&
                         File.ReadAllText(serviced).Trim() == FileDigest(exe))) {
                        // Reopening an already applied package is a launch,
                        // never another database initialization or update.
                        Launch(target, false);
                        return;
                    }
                    if ((new DirectoryInfo(target).Attributes & FileAttributes.ReparsePoint) != 0)
                        throw new Exception("The existing installation path is redirected. It was preserved.");
                    if (!serviceRequested && MessageBox.Show(
                        "Update the existing TOEFL House ERP on this PC? The protected updater requires the authorized Owner, a verified encrypted backup and rollback protection. Application services may briefly close; your database is not reinstalled.",
                        "TOEFL House ERP update", MessageBoxButtons.YesNo,
                        MessageBoxIcon.Question, MessageBoxDefaultButton.Button2) != DialogResult.Yes)
                        return;
                }
                Directory.CreateDirectory(parent);
                staging = CreateStagingDirectory(localAppData);
                string payload = Path.Combine(staging, "payload.zip");
                progress = new Form();
                progress.Text = "TOEFL House ERP setup";
                progress.Width = 470; progress.Height = 125;
                progress.StartPosition = FormStartPosition.CenterScreen;
                progress.ControlBox = false;
                Label label = new Label();
                label.Text = existing ? "Preparing the protected update. Please wait..." : "Preparing your installation. Please wait...";
                label.Dock = DockStyle.Fill; label.TextAlign = System.Drawing.ContentAlignment.MiddleCenter;
                progress.Controls.Add(label); progress.Show(); Application.DoEvents();
                input.Position = footer - length;
                using (SHA256 hash = SHA256.Create())
                using (FileStream output = File.Create(payload)) {
                    byte[] buffer = new byte[1024 * 1024]; long remaining = length;
                    while (remaining > 0) {
                        int count = input.Read(buffer, 0, (int)Math.Min(buffer.Length, remaining));
                        if (count == 0) throw new Exception("Truncated installer.");
                        output.Write(buffer, 0, count); hash.TransformBlock(buffer, 0, count, buffer, 0);
                        remaining -= count; Application.DoEvents();
                    }
                    hash.TransformFinalBlock(new byte[0], 0, 0);
                    if (BitConverter.ToString(hash.Hash) != BitConverter.ToString(expected)) throw new Exception("Installer integrity check failed.");
                }
                string extracted = Path.Combine(staging, "p"); Directory.CreateDirectory(extracted);
                ExtractPayload(payload, extracted);
                // The Windows prerequisite check needs the post-extraction disk
                // budget. Release the duplicate ZIP before the launcher starts.
                File.Delete(payload);
#if INTERNAL_UNSIGNED_SETUP
                PreserveDownloadMarker(exe, extracted);
#endif
                if (!File.Exists(Path.Combine(extracted, "product", "windows", "TOEFL House ERP.ps1")))
                    throw new Exception("Installer application is missing.");
                if (existing) {
                    if (!HasServicingPayload(extracted))
                        throw new Exception("An existing installation was preserved. This package has no authenticated existing-site servicing bundle. Use the existing ERP shortcut.");
                    label.Text = "Applying the protected update. Keep this PC and the backup drive connected.";
                    Application.DoEvents();
                    ServiceExisting(target, extracted, exe);
                    // A convenience receipt only: the authenticated updater's
                    // completed journal remains the authority for image identity.
                    File.WriteAllText(Path.Combine(target, ".servicing-setup-sha256"), FileDigest(exe));
                    Launch(target, false);
                    return;
                }
                File.WriteAllText(Path.Combine(extracted, ".payload-sha256"), digest);
                input.Position = 0;
                using (SHA256 hash = SHA256.Create()) {
                    string setupDigest = BitConverter.ToString(hash.ComputeHash(input)).Replace("-", "").ToLowerInvariant();
                    File.WriteAllText(Path.Combine(extracted, ".setup-sha256"), setupDigest);
                }
                // Atomic publish: interrupted extraction cannot look installed.
                Directory.Move(extracted, target);
                Launch(target, true);
            }
        } catch (Exception error) {
            Environment.ExitCode = 1;
            if (verifyOnly) Console.Error.WriteLine(error.Message);
            else MessageBox.Show(error.Message, "TOEFL House ERP setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
        } finally {
            if (progress != null) progress.Dispose();
            try { if (staging != null && Directory.Exists(staging)) Directory.Delete(staging, true); } catch { /* An interrupted staging directory is never published. */ }
        }
    }
    public static bool HasServicingPayload(string extracted) {
        string bootstrap = Path.Combine(extracted, "product", "updates", "bootstrap");
        string release = Path.Combine(extracted, "product", "release");
        foreach (string name in new string[] {
            "Service Existing TOEFL House ERP.ps1", "Update TOEFL House ERP.ps1",
            "Owner Host Servicing.ps1", "bootstrap.json", "bootstrap.sig.json",
            "enrollment.json", "enrollment.sig.json" })
            if (!File.Exists(Path.Combine(bootstrap, name))) return false;
        foreach (string name in new string[] { "index.json", "update.json", "update.json.sig", "toefl-house-erp-app.tar" })
            if (!File.Exists(Path.Combine(release, name))) return false;
        return true;
    }
    static string FileDigest(string path) {
        using (FileStream input = File.OpenRead(path))
        using (SHA256 hash = SHA256.Create())
            return BitConverter.ToString(hash.ComputeHash(input)).Replace("-", "").ToLowerInvariant();
    }
    static string PowerShellLiteral(string value) { return "'" + value.Replace("'", "''") + "'"; }
    public static ProcessStartInfo CreateServicingStartInfo(string target, string extracted, string installer) {
        string product = Path.Combine(target, "product");
        string bootstrap = Path.Combine(extracted, "product", "updates", "bootstrap");
        string script = Path.Combine(bootstrap, "Service Existing TOEFL House ERP.ps1");
        string oldLauncher = Path.Combine(product, "windows", "TOEFL House ERP.ps1");
        // Verify before executing the new script. All three signatures must be
        // valid and belong to the already trusted installed publisher.
        string command = "$ErrorActionPreference='Stop';" +
            "$old=Get-AuthenticodeSignature -LiteralPath " + PowerShellLiteral(oldLauncher) + ";" +
            "$exe=Get-AuthenticodeSignature -LiteralPath " + PowerShellLiteral(installer) + ";" +
            "$bridge=Get-AuthenticodeSignature -LiteralPath " + PowerShellLiteral(script) + ";" +
            "if($old.Status -ne 'Valid' -or $exe.Status -ne 'Valid' -or $bridge.Status -ne 'Valid'){throw 'A required publisher signature is invalid.'};" +
            "$pin=$old.SignerCertificate.Thumbprint;" +
            "if($exe.SignerCertificate.Thumbprint -ne $pin -or $bridge.SignerCertificate.Thumbprint -ne $pin){throw 'The updater publisher does not match this installation.'};" +
            "& " + PowerShellLiteral(script) +
            " -TargetProductRoot " + PowerShellLiteral(product) +
            " -OfflineBundleRoot " + PowerShellLiteral(Path.Combine(extracted, "product", "release")) +
            " -BootstrapRoot " + PowerShellLiteral(bootstrap) + " -OwnerApprovalAccepted;" +
            "if($LASTEXITCODE){exit $LASTEXITCODE}";
        ProcessStartInfo start = new ProcessStartInfo();
        start.FileName = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe");
        start.Arguments = "-NoLogo -NoProfile -NonInteractive -STA -WindowStyle Hidden -Command \"" + command + "\"";
        start.WorkingDirectory = target; start.UseShellExecute = false; start.CreateNoWindow = true;
        start.EnvironmentVariables.Remove("PSModulePath");
        start.EnvironmentVariables.Remove("PSExecutionPolicyPreference");
        start.RedirectStandardOutput = true; start.RedirectStandardError = true;
        return start;
    }
    static void ServiceExisting(string target, string extracted, string installer) {
        using (Process updater = new Process()) {
            updater.StartInfo = CreateServicingStartInfo(target, extracted, installer);
            // The updater stores its durable result in product/data/updates.
            // Drain both streams so a hidden child cannot block on a full pipe.
            updater.OutputDataReceived += delegate(object sender, DataReceivedEventArgs data) { };
            updater.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs data) { };
            if (!updater.Start()) throw new Exception("Windows could not start the protected updater.");
            updater.BeginOutputReadLine(); updater.BeginErrorReadLine();
            while (!updater.WaitForExit(100)) Application.DoEvents();
            updater.WaitForExit();
            if (updater.ExitCode != 0)
                throw new Exception("The protected update stopped. Open the existing ERP launcher and copy its safe support status. No database was replaced.");
        }
    }
    public static string CreateStagingDirectory(string localAppData) {
        // Keep staging on the installation volume without repeating the product
        // directory or using a 32-character hex name in every extraction path.
        string id = Convert.ToBase64String(Guid.NewGuid().ToByteArray())
            .TrimEnd('=').Replace('+', '-').Replace('/', '_');
        string path = Path.Combine(localAppData, ".th-" + id);
        if (File.Exists(path) || Directory.Exists(path))
            throw new IOException("Setup could not reserve its staging folder.");
        DirectoryInfo directory = Directory.CreateDirectory(path);
        if ((directory.Attributes & FileAttributes.ReparsePoint) != 0)
            throw new IOException("Setup refused a redirected staging folder.");
        return directory.FullName;
    }
    // Provider validation of the actual assembled EXE: no GUI, extraction,
    // service changes, prerequisite installers or customer profile writes.
    static void VerifyExecutablePayload() {
        using (FileStream input = File.OpenRead(Application.ExecutablePath)) {
            long footer = FindFooter(input);
            input.Position = footer + 8;
            long length; byte[] expected;
            using (BinaryReader reader = new BinaryReader(input, Encoding.UTF8, true)) {
                length = reader.ReadInt64(); expected = reader.ReadBytes(32);
            }
            if (length <= 0 || length > footer) throw new Exception("Invalid installer payload.");
            input.Position = footer - length;
            using (SHA256 hash = SHA256.Create()) {
                byte[] buffer = new byte[1024 * 1024]; long remaining = length;
                while (remaining > 0) {
                    int count = input.Read(buffer, 0, (int)Math.Min(buffer.Length, remaining));
                    if (count == 0) throw new Exception("Truncated installer.");
                    hash.TransformBlock(buffer, 0, count, buffer, 0); remaining -= count;
                }
                hash.TransformFinalBlock(new byte[0], 0, 0);
                if (BitConverter.ToString(hash.Hash) != BitConverter.ToString(expected)) throw new Exception("Installer integrity check failed.");
            }
        }
    }
    public static long FindFooter(FileStream input) {
        using (BinaryReader reader = new BinaryReader(input, Encoding.UTF8, true)) {
            if (input.Length < FooterSize) throw new Exception("Incomplete installer.");
            long last = input.Length - FooterSize;
            input.Position = last;
            if (Encoding.ASCII.GetString(reader.ReadBytes(8)) == "THSETUP1") return last;
            // Authenticode appends a certificate table after the payload. Locate
            // the unsigned end via the PE security directory, allowing alignment.
            if (input.Length < 64) throw new Exception("Invalid installer.");
            input.Position = 60; int pe = reader.ReadInt32();
            if (pe < 64 || pe > input.Length - 256) throw new Exception("Invalid installer.");
            input.Position = pe;
            if (reader.ReadUInt32() != 0x00004550) throw new Exception("Invalid installer.");
            long optional = pe + 24; input.Position = optional;
            ushort magic = reader.ReadUInt16();
            if (magic != 0x20b && magic != 0x10b) throw new Exception("Invalid installer.");
            input.Position = optional + (magic == 0x20b ? 112 : 96) + 32;
            long certificate = reader.ReadUInt32(); long size = reader.ReadUInt32();
            if (certificate < FooterSize || size < 8 || certificate + size > input.Length) throw new Exception("Invalid signature table.");
            for (int padding = 0; padding < 8; padding++) {
                long position = certificate - FooterSize - padding;
                if (position < 0) continue;
                input.Position = position;
                if (Encoding.ASCII.GetString(reader.ReadBytes(8)) == "THSETUP1") return position;
            }
            throw new Exception("Installer payload is missing.");
        }
    }
    public static void ExtractPayload(string payload, string extracted) {
        string prefix = Path.GetFullPath(extracted) + Path.DirectorySeparatorChar;
        HashSet<string> names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        using (ZipArchive archive = ZipFile.OpenRead(payload)) {
            if (archive.Entries.Count > MaxPayloadEntries)
                throw new Exception("Installer archive contains too many files.");
            // Validate the entire index before writing the first file.
            // Reject Windows aliases such as "name.", "name " and device paths,
            // as well as archive expansion beyond a bounded customer disk budget.
            long expanded = 0;
            foreach (ZipArchiveEntry entry in archive.Entries) {
                string raw = entry.FullName;
                if (string.IsNullOrEmpty(raw) || raw.Contains("\\") ||
                    entry.Length < 0 || entry.Length > MaxUnpackedBytes - expanded)
                    throw new Exception("Unsafe installer archive.");
                expanded += entry.Length;
                foreach (string segment in raw.TrimEnd('/').Split('/')) {
                    if (string.IsNullOrEmpty(segment) || segment == "." || segment == ".." ||
                        segment.TrimEnd(' ', '.') != segment || IsDeviceName(segment))
                        throw new Exception("Unsafe installer archive path.");
                }
                string name = raw.Replace('/', Path.DirectorySeparatorChar);
                string path;
                try { path = Path.GetFullPath(Path.Combine(extracted, name)); }
                catch (PathTooLongException error) {
                    throw new PathTooLongException("Setup cannot stage this Windows path: " + prefix + name, error);
                }
                if (Path.IsPathRooted(name) || name.Contains(":") || !path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase) ||
                    !names.Add(path) || ((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000)
                    throw new Exception("Unsafe installer archive.");
            }
            foreach (ZipArchiveEntry entry in archive.Entries) {
                string path = Path.GetFullPath(Path.Combine(extracted, entry.FullName.Replace('/', Path.DirectorySeparatorChar)));
                try {
                    if (entry.Name.Length == 0) Directory.CreateDirectory(path);
                    else { Directory.CreateDirectory(Path.GetDirectoryName(path)); entry.ExtractToFile(path); }
                } catch (PathTooLongException error) {
                    throw new PathTooLongException("Setup cannot stage this Windows path: " + path, error);
                }
                Application.DoEvents();
            }
        }
    }
    static bool IsDeviceName(string segment) {
        string stem = segment.Split('.')[0].ToUpperInvariant();
        if (stem == "CON" || stem == "PRN" || stem == "AUX" || stem == "NUL")
            return true;
        if (stem.Length == 4 && (stem.StartsWith("COM") || stem.StartsWith("LPT")) &&
            stem[3] >= '1' && stem[3] <= '9')
            return true;
        return false;
    }
    public static void PreserveDownloadMarker(string installer, string extracted) {
        byte[] marker = ReadDownloadMarker(installer);
        if (marker == null) return;
        foreach (string file in Directory.EnumerateFiles(extracted, "*", SearchOption.AllDirectories)) {
            string extension = Path.GetExtension(file).ToLowerInvariant();
            if (extension == ".ps1" || extension == ".cmd" || extension == ".vbs")
                WriteDownloadMarker(file, marker);
        }
    }

    // .NET Framework rejects ADS paths before reaching the filesystem API.
    [System.Runtime.InteropServices.DllImport("kernel32.dll", EntryPoint = "CreateFileW",
        CharSet = System.Runtime.InteropServices.CharSet.Unicode, SetLastError = true)]
    private static extern Microsoft.Win32.SafeHandles.SafeFileHandle OpenStream(
        string name, uint access, uint share, IntPtr security, uint creation,
        uint flags, IntPtr template);

    public static byte[] ReadDownloadMarker(string path) {
        var handle = OpenStream(path + ":Zone.Identifier", 0x80000000u, 7,
            IntPtr.Zero, 3, 0, IntPtr.Zero);
        if (handle.IsInvalid) {
            int error = System.Runtime.InteropServices.Marshal.GetLastWin32Error();
            handle.Dispose();
            if (error == 2) return null;
            if (error == 50 || error == 123) {
                string format = new DriveInfo(Path.GetPathRoot(path)).DriveFormat;
                if (format == "FAT" || format == "FAT32" || format == "exFAT") return null;
            }
            throw new System.ComponentModel.Win32Exception(error, "Could not read the Windows download marker.");
        }
        using (handle)
        using (var stream = new FileStream(handle, FileAccess.Read)) {
            if (stream.Length > 65536) throw new IOException("The Windows download marker is too large.");
            using (var data = new MemoryStream()) {
                stream.CopyTo(data);
                return data.ToArray();
            }
        }
    }

    public static void WriteDownloadMarker(string path, byte[] marker) {
        var handle = OpenStream(path + ":Zone.Identifier", 0x40000000u, 0,
            IntPtr.Zero, 2, 0, IntPtr.Zero);
        if (handle.IsInvalid) {
            int error = System.Runtime.InteropServices.Marshal.GetLastWin32Error();
            handle.Dispose();
            throw new System.ComponentModel.Win32Exception(error, "Could not preserve the Windows download marker.");
        }
        using (handle)
        using (var stream = new FileStream(handle, FileAccess.Write)) {
            stream.Write(marker, 0, marker.Length);
        }
    }

    public static ProcessStartInfo CreateLauncherStartInfo(string target, bool install) {
        string script = Path.Combine(target, "product", "windows", "TOEFL House ERP.ps1");
        ProcessStartInfo start = new ProcessStartInfo();
        start.FileName = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe");
#if INTERNAL_UNSIGNED_SETUP
        start.Arguments = "-NoLogo -NoProfile -STA -WindowStyle Hidden -File \"" + script + "\"" + (install ? " -AutoInstall" : "");
#else
        start.Arguments = "-NoLogo -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + script + "\"" + (install ? " -AutoInstall" : "");
#endif
        start.WorkingDirectory = target; start.UseShellExecute = false; start.CreateNoWindow = true;
        // Let Windows PowerShell build its own module search path. A caller
        // running PowerShell 7 can otherwise supply incompatible modules.
        start.EnvironmentVariables.Remove("PSModulePath");
#if INTERNAL_UNSIGNED_SETUP
        // Honor the installed Windows policy, even when a developer shell
        // launches Setup with a transient process policy.
        start.EnvironmentVariables.Remove("PSExecutionPolicyPreference");
#endif
        return start;
    }

    static void Launch(string target, bool install) {
#if INTERNAL_UNSIGNED_SETUP
        // An early policy refusal from hidden Windows PowerShell would otherwise
        // leave the operator with an extracted package and no visible launcher.
        using (Process launcher = Process.Start(CreateLauncherStartInfo(target, install))) {
            if (launcher == null || (launcher.WaitForExit(3000) && launcher.ExitCode != 0))
                throw new Exception("Windows could not open the ERP launcher. The verified files are in place. Ask the institute administrator to check the approved Windows policy for this internal installer, then reopen Setup.");
        }
#else
        Process.Start(CreateLauncherStartInfo(target, install));
#endif
    }
}
