// Small Windows GUI self-extractor. Payload is appended by the provider builder.
// It never overwrites a previous installation, changes Docker data or downloads.
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
        Application.EnableVisualStyles();
        string staging = null;
        Form progress = null;
        try {
            if (verifyOnly) { VerifyExecutablePayload(); return; }
            string exe = Application.ExecutablePath;
            string parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TOEFL House ERP");
            string target = Path.Combine(parent, "Customer");
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
                if (Directory.Exists(target)) {
                    string receipt = Path.Combine(target, ".payload-sha256");
                    if (!File.Exists(receipt) || File.ReadAllText(receipt).Trim() != digest)
                        throw new Exception("An existing installation was preserved. Use its TOEFL House ERP shortcut or the verified update workflow. This installer will not replace your records.");
                    // Opening the same verified installer again is a launch,
                    // never a second attempt to initialize the database.
                    Launch(target, false);
                    return;
                }
                Directory.CreateDirectory(parent);
                staging = Path.Combine(parent, ".setup-" + Guid.NewGuid().ToString("N"));
                Directory.CreateDirectory(staging);
                string payload = Path.Combine(staging, "payload.zip");
                progress = new Form();
                progress.Text = "TOEFL House ERP setup";
                progress.Width = 470; progress.Height = 125;
                progress.StartPosition = FormStartPosition.CenterScreen;
                progress.ControlBox = false;
                Label label = new Label();
                label.Text = "Preparing your installation. Please wait...";
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
                string extracted = Path.Combine(staging, "files"); Directory.CreateDirectory(extracted);
                ExtractPayload(payload, extracted);
                if (!File.Exists(Path.Combine(extracted, "product", "windows", "TOEFL House ERP.ps1")))
                    throw new Exception("Installer application is missing.");
                File.WriteAllText(Path.Combine(extracted, ".payload-sha256"), digest);
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
                string path = Path.GetFullPath(Path.Combine(extracted, name));
                if (Path.IsPathRooted(name) || name.Contains(":") || !path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase) ||
                    !names.Add(path) || ((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000)
                    throw new Exception("Unsafe installer archive.");
            }
            foreach (ZipArchiveEntry entry in archive.Entries) {
                string path = Path.GetFullPath(Path.Combine(extracted, entry.FullName.Replace('/', Path.DirectorySeparatorChar)));
                if (entry.Name.Length == 0) Directory.CreateDirectory(path);
                else { Directory.CreateDirectory(Path.GetDirectoryName(path)); entry.ExtractToFile(path); }
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
    static void Launch(string target, bool install) {
        string script = Path.Combine(target, "product", "windows", "TOEFL House ERP.ps1");
        ProcessStartInfo start = new ProcessStartInfo();
        start.FileName = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe");
        start.Arguments = "-NoLogo -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + script + "\"" + (install ? " -AutoInstall" : "");
        start.WorkingDirectory = target; start.UseShellExecute = false; start.CreateNoWindow = true;
        Process.Start(start);
    }
}
