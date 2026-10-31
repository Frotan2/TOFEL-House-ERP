// Small signed Windows download launcher. The embedded plan is immutable after
// Authenticode signing. It only retrieves an exact SHA-256-pinned signed offline
// Setup EXE; that existing Setup owns all prerequisite and installation work.
// Never accept a dynamic URL, update channel, credential, or executable argument.
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Net;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Windows.Forms;

internal sealed class OnlinePlan {
    internal readonly Uri Url;
    internal readonly string Digest;
    internal readonly long Bytes;
    internal readonly string Signer;

    private OnlinePlan(Uri url, string digest, long bytes, string signer) {
        Url = url; Digest = digest; Bytes = bytes; Signer = signer;
    }
    internal static OnlinePlan Read() {
        using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("TOEFLHouse.OnlinePlan")) {
            if (resource == null) throw new InvalidDataException("The signed download plan is missing.");
            using (StreamReader reader = new StreamReader(resource, new UTF8Encoding(false, true))) {
                string[] rows = reader.ReadToEnd().TrimEnd('\r', '\n').Split('\n');
                if (rows.Length != 5 || rows[0].TrimEnd('\r') != "TH_ONLINE_PLAN_V1")
                    throw new InvalidDataException("The download plan format is invalid.");
                for (int i = 1; i < rows.Length; i++) {
                    rows[i] = rows[i].TrimEnd('\r');
                    if (rows[i] != rows[i].Trim() || rows[i].Length > 600)
                        throw new InvalidDataException("The download plan has invalid fields.");
                }
                Uri url;
                if (!Uri.TryCreate(rows[1], UriKind.Absolute, out url) ||
                    url.UserInfo.Length != 0 || url.Query.Length != 0 || url.Fragment.Length != 0)
                    throw new InvalidDataException("Invalid published installer address.");
                bool approved = url.Scheme == Uri.UriSchemeHttps &&
                    url.Host.Equals("github.com", StringComparison.OrdinalIgnoreCase) &&
                    System.Text.RegularExpressions.Regex.IsMatch(url.AbsolutePath,
                        @"^/Frotan2/TOFEL-House-ERP/releases/download/[A-Za-z0-9][A-Za-z0-9._-]{0,95}/TOEFL-House-ERP-Setup\.exe$",
                        System.Text.RegularExpressions.RegexOptions.IgnoreCase);
#if TEST_BUILD
                approved |= url.Scheme == Uri.UriSchemeHttp &&
                    (url.Host == "127.0.0.1" || url.Host == "localhost");
#endif
                if (!approved || !IsHex(rows[2], 64) || !IsHex(rows[4], 40))
                    throw new InvalidDataException("The signed installer identity is invalid.");
                long bytes;
                if (!long.TryParse(rows[3], NumberStyles.None, CultureInfo.InvariantCulture, out bytes) ||
                    bytes < 1 || bytes >= 2147483648L)
                    throw new InvalidDataException("The installer length is invalid.");
                return new OnlinePlan(url, rows[2].ToLowerInvariant(), bytes, rows[4].ToUpperInvariant());
            }
        }
    }
    static bool IsHex(string text, int n) {
        if (text.Length != n) return false;
        foreach (char c in text)
            if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') ||
                  (c >= 'A' && c <= 'F'))) return false;
        return true;
    }
}

internal static class InstallerTrust {
    private static readonly Guid Action = new Guid("00AAC56B-CD44-11D0-8CC2-00C04FC295EE");
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct FileInfo {
        public uint Size;
        [MarshalAs(UnmanagedType.LPWStr)] public string FilePath;
        public IntPtr FileHandle;
        public IntPtr KnownSubject;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct TrustData {
        public uint Size;
        public IntPtr PolicyCallback;
        public IntPtr SIPClient;
        public uint UIChoice;
        public uint RevocationChecks;
        public uint UnionChoice;
        public IntPtr FileInfo;
        public uint StateAction;
        public IntPtr StateData;
        public IntPtr UrlReference;
        public uint ProviderFlags;
        public uint UIContext;
    }
    [DllImport("wintrust.dll", ExactSpelling = true, PreserveSig = true)]
    private static extern uint WinVerifyTrust(IntPtr window, ref Guid action, IntPtr data);
    internal static void VerifySignedInstaller(string path, string expectedThumbprint) {
        FileInfo file = new FileInfo {
            Size = (uint)Marshal.SizeOf(typeof(FileInfo)), FilePath = path,
            FileHandle = IntPtr.Zero, KnownSubject = IntPtr.Zero
        };
        IntPtr filePtr = IntPtr.Zero, dataPtr = IntPtr.Zero;
        try {
            filePtr = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(FileInfo)));
            Marshal.StructureToPtr(file, filePtr, false);
            TrustData trust = new TrustData {
                Size = (uint)Marshal.SizeOf(typeof(TrustData)),
                UIChoice = 2, // WTD_UI_NONE
                RevocationChecks = 1, // WTD_REVOKE_WHOLECHAIN
                UnionChoice = 1, // WTD_CHOICE_FILE
                FileInfo = filePtr,
                ProviderFlags = 0x40 // WTD_REVOCATION_CHECK_CHAIN
            };
            dataPtr = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(TrustData)));
            Marshal.StructureToPtr(trust, dataPtr, false);
            Guid action = Action;
            uint status = WinVerifyTrust(IntPtr.Zero, ref action, dataPtr);
            if (status != 0) throw new InvalidDataException("The installer publisher signature could not be verified.");
            using (X509Certificate2 certificate = new X509Certificate2(X509Certificate.CreateFromSignedFile(path))) {
                if (!string.Equals(certificate.Thumbprint, expectedThumbprint,
                    StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("The signed installer was issued by a different publisher.");
            }
        } finally {
            if (dataPtr != IntPtr.Zero) Marshal.FreeHGlobal(dataPtr);
            if (filePtr != IntPtr.Zero) Marshal.FreeHGlobal(filePtr);
        }
    }
}

internal static class OnlineDownloader {
    private static void RejectReparse(string path) {
        if (File.Exists(path) || Directory.Exists(path)) {
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("An unsafe linked download directory or file was found. Contact support.");
        }
    }
    internal static string Destination(OnlinePlan plan, string root) {
        string full = Path.GetFullPath(root);
        RejectReparse(full);
        string downloads = Path.Combine(full, "Downloads");
        RejectReparse(downloads);
        Directory.CreateDirectory(downloads);
        return Path.Combine(downloads, "TOEFL-House-ERP-Setup-" + plan.Digest.Substring(0, 16) + ".exe");
    }
    internal static string Download(OnlinePlan plan, string root, BackgroundWorker worker) {
        string destination = Destination(plan, root), part = destination + ".part";
        RejectReparse(destination); RejectReparse(part);
        // A verified cached installer is safe to reuse, without downloading.
        if (File.Exists(destination)) {
            try {
                VerifyDigest(destination, plan);
            } catch (InvalidDataException) {
                // A corrupt digest-named cache would otherwise prevent every retry.
                // Remove ONLY this untrusted download; never an installed site.
                File.Delete(destination);
                throw new InvalidDataException("The cached download was damaged and removed. Click Download & Install to retry.");
            }
#if !TEST_BUILD
            // Trust failures are not treated as ordinary cache corruption.
            // Preserve the file for trusted support; never execute it.
            InstallerTrust.VerifySignedInstaller(destination, plan.Signer);
#endif
            return destination;
        }
        long offset = File.Exists(part) ? new FileInfo(part).Length : 0;
        if (offset > plan.Bytes) {
            // An oversized partial is unrecoverable with HTTP Range.
            File.Delete(part);
            throw new InvalidDataException("The partial download was invalid and removed. Click Download & Install to retry.");
        }
        if (offset != plan.Bytes) {
            // TLS 1.2 required by GitHub. HttpWebRequest handles HTTPS redirects,
            // but the resulting address must remain HTTPS. Never send secrets.
            ServicePointManager.SecurityProtocol |= (SecurityProtocolType)3072;
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(plan.Url);
            request.Method = "GET";
            request.Timeout = 30000;
            request.ReadWriteTimeout = 30000;
            request.AllowAutoRedirect = true;
            request.MaximumAutomaticRedirections = 5;
            request.AutomaticDecompression = DecompressionMethods.None;
            request.UserAgent = "TOEFL-House-ERP-Signed-Online-Setup/1";
            if (offset != 0) request.AddRange(offset);
            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse()) {
                if (response.ResponseUri.Scheme != Uri.UriSchemeHttps) {
#if TEST_BUILD
                    if (response.ResponseUri.Scheme != Uri.UriSchemeHttp ||
                        (response.ResponseUri.Host != "127.0.0.1" &&
                         response.ResponseUri.Host != "localhost"))
#endif
                        throw new InvalidDataException("The download did not use a trusted HTTPS channel.");
                }
                bool resumed = response.StatusCode == HttpStatusCode.PartialContent;
                if (offset != 0 && resumed) {
                    string expectedStart = "bytes " + offset.ToString(CultureInfo.InvariantCulture) + "-";
                    string range = response.Headers[HttpResponseHeader.ContentRange] ?? "";
                    if (!range.StartsWith(expectedStart, StringComparison.Ordinal) ||
                        !range.EndsWith("/" + plan.Bytes.ToString(CultureInfo.InvariantCulture), StringComparison.Ordinal))
                        throw new InvalidDataException("The server returned an invalid resume range.");
                } else if (response.StatusCode != HttpStatusCode.OK) {
                    throw new InvalidDataException("The server returned an invalid installer response.");
                } else {
                    offset = 0; // Server ignored Range: restart, never append its full response.
                }
                FileMode mode = resumed && offset != 0 ? FileMode.Open : FileMode.Create;
                using (FileStream target = new FileStream(part, mode, FileAccess.Write, FileShare.None))
                using (Stream source = response.GetResponseStream()) {
                    if (offset > 0) target.Position = offset;
                    byte[] buffer = new byte[128 * 1024]; long current = offset;
                    int count;
                    while ((count = source.Read(buffer, 0, buffer.Length)) > 0) {
                        if (worker != null && worker.CancellationPending)
                            throw new OperationCanceledException("Download cancelled. The partial download was retained.");
                        current += count;
                        if (current > plan.Bytes) throw new InvalidDataException("The server sent too much data.");
                        target.Write(buffer, 0, count);
                        if (worker != null)
                            worker.ReportProgress((int)(100 * current / plan.Bytes));
                    }
                    target.Flush(true);
                    if (current != plan.Bytes)
                        throw new IOException("Download interrupted. Open Setup again to resume.");
                }
            }
        }
        try {
            VerifyDigest(part, plan);
        } catch (InvalidDataException) {
            // Only this digest-named, untrusted .part is discarded. An invalid
            // complete cache must not trap nontechnical users in a failed retry.
            File.Delete(part);
            throw new InvalidDataException("The download failed verification and was discarded. Open Setup again to retry.");
        }
        if (worker != null && worker.CancellationPending)
            throw new OperationCanceledException("Download cancelled before installation.");
#if !TEST_BUILD
        InstallerTrust.VerifySignedInstaller(part, plan.Signer);
#endif
        if (worker != null && worker.CancellationPending)
            throw new OperationCanceledException("Download cancelled before installation.");
        // Do not replace existing files or any previously installed Customer site.
        File.Move(part, destination);
        return destination;
    }
    private static void VerifyDigest(string file, OnlinePlan plan) {
        RejectReparse(file);
        FileInfo info = new FileInfo(file);
        if (info.Length != plan.Bytes) throw new InvalidDataException("Downloaded installer length does not match the publisher record.");
        using (SHA256 sha = SHA256.Create())
        using (FileStream stream = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.Read)) {
            string actual = BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
            if (actual != plan.Digest)
                throw new InvalidDataException("The downloaded installer failed its SHA-256 integrity check.");
        }
    }
}

public sealed class OnlineSetup : Form {
    readonly OnlinePlan plan;
    readonly string root;
    readonly Label status = new Label();
    readonly ProgressBar progress = new ProgressBar();
    readonly Button start = new Button();
    readonly Button cancel = new Button();
    readonly BackgroundWorker worker = new BackgroundWorker();

    internal OnlineSetup(OnlinePlan plan, string root) {
        this.plan = plan; this.root = root;
        Text = "The TOEFL House | Online Setup";
        Width = 500; Height = 230;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        status.SetBounds(20, 15, 440, 66);
        status.Text = "Download and install the verified TOEFL House ERP package.\r\nInternet is required for the first download. Existing ERP data is preserved.";
        progress.SetBounds(20, 88, 440, 22);
        progress.Minimum = 0; progress.Maximum = 100;
        start.Text = "Download & Install"; start.SetBounds(20, 125, 230, 35);
        cancel.Text = "Close"; cancel.SetBounds(265, 125, 195, 35);
        Controls.Add(status); Controls.Add(progress); Controls.Add(start); Controls.Add(cancel);
        worker.WorkerReportsProgress = true; worker.WorkerSupportsCancellation = true;
        worker.DoWork += (sender, args) => {
            try { args.Result = OnlineDownloader.Download(plan, root, worker); }
            catch (OperationCanceledException) { args.Cancel = true; }
        };
        worker.ProgressChanged += (sender, args) => {
            progress.Value = Math.Max(0, Math.Min(100, args.ProgressPercentage));
            status.Text = "Downloading verified offline installation package: " + progress.Value + "%\r\nDo not turn off this computer.";
        };
        worker.RunWorkerCompleted += (sender, args) => {
            start.Enabled = true; cancel.Enabled = true; cancel.Text = "Close";
            if (args.Error != null) {
                status.Text = "Download failed. No ERP database was changed.";
                MessageBox.Show(args.Error.Message, "TOEFL House Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
            } else if (args.Cancelled) {
                status.Text = "Download cancelled. Reopen Setup to resume.";
            } else {
                try {
                    status.Text = "Verified package. Opening the offline installer...";
                    string file = (string)args.Result;
                    Process.Start(new ProcessStartInfo(file) { UseShellExecute = true });
                    Close();
                } catch (Exception error) {
                    MessageBox.Show(error.Message, "Unable to start verified installer", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
            }
        };
        start.Click += (sender, args) => {
            start.Enabled = false; cancel.Text = "Cancel download";
            status.Text = "Connecting to verified release...";
            worker.RunWorkerAsync();
        };
        cancel.Click += (sender, args) => {
            if (worker.IsBusy) { worker.CancelAsync(); cancel.Enabled = false; }
            else Close();
        };
        FormClosing += (sender, args) => {
            if (worker.IsBusy) { worker.CancelAsync(); args.Cancel = true; }
        };
    }
    private static void RefuseExistingInstallation(string root) {
        // The signed offline setup installs to Customer under the same root.
        if (Directory.Exists(Path.Combine(root, "Customer")))
            throw new InvalidDataException("Existing TOEFL House installation detected. Use the existing launcher. No download or reinstall was attempted.");
        // Older portable/customer-kit installations may reside on the Desktop.
        // Detect only actual ERP data, not a source checkout with the same name.
        string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        foreach (string name in new string[] { "TOEFL-House-ERP", "TOFEL-House-ERP", "TOEFL House ERP" }) {
            string data = Path.Combine(desktop, name, "product", "data");
            if (File.Exists(Path.Combine(data, "secrets", "db.env")) ||
                Directory.Exists(Path.Combine(data, "sites")) ||
                Directory.Exists(Path.Combine(data, ".installation-claim")))
                throw new InvalidDataException("Existing portable ERP data was detected on the Desktop. Use the installed launcher or contact support.");
        }
    }
    [STAThread]
    public static int Main(string[] args) {
        try {
            OnlinePlan plan = OnlinePlan.Read();
#if TEST_BUILD
            // Disposable CI only. Production builds never compile this entry.
            // Neither Authenticode policy nor launch is bypassable in production.
            if (args.Length == 2 && args[0] == "--probe-download") {
                OnlineDownloader.Download(plan, args[1], null);
                Console.WriteLine("TEST_ONLY_NO_LAUNCH: download integrity verified");
                return 0;
            }
#endif
            if (args.Length != 0) throw new InvalidDataException("Unsupported setup arguments.");
            string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TOEFL House ERP");
            RefuseExistingInstallation(root);
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new OnlineSetup(plan, root));
            return 0;
        } catch (Exception error) {
#if TEST_BUILD
            if (args.Length == 2 && args[0] == "--probe-download") {
                Console.Error.WriteLine("Synthetic download refused: " + error.Message);
                return 1;
            }
#endif
            MessageBox.Show(error.Message, "TOEFL House Online Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
