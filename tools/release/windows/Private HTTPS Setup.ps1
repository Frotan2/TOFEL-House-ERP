param([switch]$FunctionsOnly, [switch]$SmokeTest)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 3.0

function ConvertTo-IPv4Number([string]$Address) {
    if ($Address -cnotmatch '\A(?:0|[1-9][0-9]{0,2})(?:\.(?:0|[1-9][0-9]{0,2})){3}\z') {
        throw 'Enter IPv4 as four decimal numbers without spaces or leading zeros.'
    }
    $parsed = $null
    if (-not [Net.IPAddress]::TryParse($Address, [ref]$parsed) -or
        $parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
        throw 'The IPv4 address is outside the valid range.'
    }
    $bytes = $parsed.GetAddressBytes()
    return [long]$bytes[0] * 16777216 + [long]$bytes[1] * 65536 +
        [long]$bytes[2] * 256 + $bytes[3]
}

function Get-PrivateIPv4Block([long]$Address) {
    $octet1 = [Math]::Floor($Address / 16777216)
    $octet2 = [Math]::Floor(($Address % 16777216) / 65536)
    if ($octet1 -eq 10) { return '10/8' }
    if ($octet1 -eq 172 -and $octet2 -ge 16 -and $octet2 -le 31) { return '172.16/12' }
    if ($octet1 -eq 192 -and $octet2 -eq 168) { return '192.168/16' }
    return ''
}

function ConvertTo-PrivateHttpsConfiguration(
    [string]$DnsName, [string]$BindAddress, [string]$StaffCidr, [string]$TemplatePath
) {
    $labels = $DnsName.Split('.')
    if ($DnsName.Length -gt 253 -or $labels.Count -lt 2 -or
        $labels[-1] -cnotmatch '[A-Za-z]' -or
        $labels[-1] -in @('localhost', 'invalid', 'example', 'test', 'onion')) {
        throw 'Enter the institute DNS name for the private ERP, such as the name supplied by your network administrator.'
    }
    foreach ($label in $labels) {
        if ($label -cnotmatch '\A[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\z') {
            throw 'Use only standard DNS letters, digits and hyphens, separated by dots.'
        }
    }

    $bindNumber = ConvertTo-IPv4Number $BindAddress
    if (-not (Get-PrivateIPv4Block $bindNumber)) {
        throw 'The ERP host bind address must be a private IPv4 address in 10/8, 172.16/12 or 192.168/16.'
    }

    if ($StaffCidr -cnotmatch '\A([0-9.]+)/(0|[1-9]|[12][0-9]|3[0-2])\z') {
        throw 'Enter one approved IPv4 network with its prefix length.'
    }
    $network = ConvertTo-IPv4Number $Matches[1]
    $prefix = [int]$Matches[2]
    $blockSize = [long][Math]::Pow(2, 32 - $prefix)
    if (($network % $blockSize) -ne 0) {
        throw 'Enter the approved staff network address with host bits set to zero.'
    }
    $networkBlock = Get-PrivateIPv4Block $network
    if (-not $networkBlock -or $networkBlock -ne (Get-PrivateIPv4Block ($network + $blockSize - 1))) {
        throw 'The entire approved staff network must stay inside a single private IPv4 range.'
    }

    # Verify the same normalized text that is used to generate the configuration.
    $utf8 = [Text.UTF8Encoding]::new($false, $true)
    $template = [IO.File]::ReadAllText($TemplatePath, $utf8).Replace([string][char]13 + [char]10, [string][char]10)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $actual = [BitConverter]::ToString($sha.ComputeHash($utf8.GetBytes($template))).Replace('-', '')
    } finally {
        $sha.Dispose()
    }
    if ($actual -ine '56dc3799f24344f75dcaff39b461b012adf3568527469101668bf2a775f376ab') {
        throw 'The Caddy template differs from the verified release. Restore it from the delivery kit.'
    }
    $configuration = $template.Replace('erp-staff.example.invalid', $DnsName.ToLowerInvariant()).
        Replace('192.0.2.250', $BindAddress).Replace('192.0.2.0/24', $StaffCidr)
    return $configuration.Substring($configuration.IndexOf('{'))
}

function Confirm-LocalBindAddress([string]$BindAddress) {
    $matches = 0
    foreach ($adapter in [Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()) {
        if ($adapter.OperationalStatus -ne [Net.NetworkInformation.OperationalStatus]::Up -or
            $adapter.NetworkInterfaceType -in @('Loopback', 'Tunnel')) { continue }
        foreach ($address in $adapter.GetIPProperties().UnicastAddresses) {
            if ($address.Address.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork -and
                $address.Address.ToString() -ceq $BindAddress) { $matches++ }
        }
    }
    if ($matches -ne 1) {
        throw 'The bind address must be assigned to one active network adapter on this Windows PC.'
    }
}

function Assert-PlainLocalDirectory([string]$Path) {
    if ($Path -cnotmatch '\A[A-Za-z]:\\') {
        throw 'Choose an existing folder on a local Windows drive.'
    }
    $folder = [IO.DirectoryInfo]::new([IO.Path]::GetFullPath($Path))
    while ($null -ne $folder) {
        if (-not $folder.Exists -or ($folder.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Choose an existing local folder without redirected folders or symbolic links.'
        }
        $folder = $folder.Parent
    }
}

function Open-PlainLocalFile([string]$Path) {
    Assert-PlainLocalDirectory ([IO.Path]::GetDirectoryName($Path))
    $file = [IO.FileInfo]::new($Path)
    if (!$file.Exists -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'The expected local file is missing or redirected.'
    }
    return [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
}

function Save-NewPrivateHttpsConfiguration([string]$Path, [string]$Configuration) {
    if ($Path -cnotmatch '\A[A-Za-z]:\\') { throw 'Choose a file on a local Windows drive.' }
    $fullPath = [IO.Path]::GetFullPath($Path)
    if ([IO.Path]::GetFileName($fullPath) -ine 'Caddyfile') {
        throw 'Save the new configuration with the file name Caddyfile and no extension.'
    }
    Assert-PlainLocalDirectory ([IO.Path]::GetDirectoryName($fullPath))
    $stream = [IO.File]::Open($fullPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes($Configuration)
        $stream.Write($bytes, 0, $bytes.Length)
    } finally {
        $stream.Dispose()
    }
}

function Set-ProxyDownloadMarker([string]$Executable, [string[]]$Origins) {
    # The executable came from a vendor download, even when the embedded ZIP
    # carries no zone stream. Preserve a restricted-zone mark if present.
    $mark = "[ZoneTransfer]`r`nZoneId=3`r`n"
    foreach ($origin in $Origins) {
        $streams = @(Get-Item -LiteralPath $origin -Stream '*' | Where-Object Stream -CEQ 'Zone.Identifier')
        if (!$streams.Count) { continue }
        if ($streams[0].Length -gt 4096) { throw 'The proxy download marker is invalid.' }
        $inputMark = Get-Content -LiteralPath $origin -Stream Zone.Identifier -Raw
        if ($inputMark -match '(?m)^ZoneId=4\r?$') { $mark = "[ZoneTransfer]`r`nZoneId=4`r`n" }
    }
    Set-Content -LiteralPath $Executable -Stream Zone.Identifier -Value $mark -Encoding Ascii -NoNewline
}

function Save-PrivateProxyFiles([string]$Parent, [string]$Archive, [string]$Configuration) {
    Assert-PlainLocalDirectory $Parent
    $target = Join-Path $Parent 'TOEFL House ERP Private HTTPS'
    if (Get-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue) {
        throw 'A proxy files folder already exists. Choose a new destination folder.'
    }
    Add-Type -AssemblyName System.IO.Compression
    $source = Open-PlainLocalFile $Archive
    $stage = $null
    try {
        if ($source.Length -lt 1 -or $source.Length -gt 64MB) {
            throw 'The bundled proxy archive has an invalid size.'
        }
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $digest = [BitConverter]::ToString($sha.ComputeHash($source)).Replace('-', '') }
        finally { $sha.Dispose() }
        if ($digest -ine 'ad93112d335ee687100c4c9f11bced16ca590377976b7fe7883882b9e797e472') {
            throw 'The bundled proxy archive failed its release checksum.'
        }
        $source.Position = 0
        $zip = [IO.Compression.ZipArchive]::new($source, [IO.Compression.ZipArchiveMode]::Read, $true)
        try {
            $entries = @($zip.Entries | Where-Object FullName -CEQ 'caddy.exe')
            if ($entries.Count -ne 1 -or $entries[0].Length -lt 1 -or $entries[0].Length -gt 160MB) {
                throw 'The verified proxy archive does not contain one Windows executable.'
            }
            $stage = Join-Path $Parent ('.toefl-https-' + [guid]::NewGuid().ToString('N'))
            [void][IO.Directory]::CreateDirectory($stage)
            $entry = $entries[0].Open()
            try {
                $exe = [IO.File]::Open((Join-Path $stage 'caddy.exe'), [IO.FileMode]::CreateNew,
                    [IO.FileAccess]::Write, [IO.FileShare]::None)
                try {
                    $entry.CopyTo($exe)
                    if ($exe.Length -ne $entries[0].Length) { throw 'The proxy executable was not fully extracted.' }
                } finally { $exe.Dispose() }
            } finally { $entry.Dispose() }
            Set-ProxyDownloadMarker (Join-Path $stage 'caddy.exe') @($Archive, $PSCommandPath)
            Save-NewPrivateHttpsConfiguration (Join-Path $stage 'Caddyfile') $Configuration
        } finally { $zip.Dispose() }
        [IO.Directory]::Move($stage, $target)
        $stage = $null
        return $target
    } finally {
        $source.Dispose()
        if ($stage) {
            # Only remove our two named output files inside our newly created staging directory.
            Assert-PlainLocalDirectory $stage
            [IO.File]::Delete((Join-Path $stage 'caddy.exe'))
            [IO.File]::Delete((Join-Path $stage 'Caddyfile'))
            [IO.Directory]::Delete($stage)
        }
    }
}

function Read-PrivateHttpsPublicCertificate([string]$Path) {
    $source = Open-PlainLocalFile $Path
    try {
        if ($source.Length -lt 1 -or $source.Length -gt 16384) {
            throw 'The public certificate file has an invalid size.'
        }
        $reader = [IO.StreamReader]::new($source)
        try { $pem = $reader.ReadToEnd() }
        finally { $reader.Dispose() }
    } finally { $source.Dispose() }
    if ($pem -cnotmatch '\A-----BEGIN CERTIFICATE-----\r?\n([A-Za-z0-9+/=\r\n]+)-----END CERTIFICATE-----\s*\z') {
        throw 'The file must contain exactly one public PEM certificate.'
    }
    $der = [Convert]::FromBase64String($Matches[1])
    if ([Security.Cryptography.X509Certificates.X509Certificate2]::GetCertContentType($der) -ne 'Cert') {
        throw 'The input is not a public X.509 certificate.'
    }
    $certificate = [Security.Cryptography.X509Certificates.X509Certificate2]::new($der)
    try {
        $constraints = @($certificate.Extensions | Where-Object { $_.Oid.Value -ceq '2.5.29.19' })
        if ($certificate.HasPrivateKey -or $certificate.Subject -cne $certificate.Issuer -or
            $constraints.Count -ne 1 -or -not $constraints[0].CertificateAuthority -or
            $certificate.NotBefore -gt (Get-Date) -or $certificate.NotAfter -le (Get-Date)) {
            throw 'The file is not a currently valid public CA certificate.'
        }
        return ,$certificate.Export([Security.Cryptography.X509Certificates.X509ContentType]::Cert)
    } finally { $certificate.Dispose() }
}

if ($FunctionsOnly) { return }

Add-Type -AssemblyName System.Windows.Forms,System.Drawing
[Windows.Forms.Application]::EnableVisualStyles()

$form = New-Object Windows.Forms.Form
$form.Text = 'TOEFL House ERP - Private HTTPS'
$form.ClientSize = New-Object Drawing.Size(640, 450)
$form.FormBorderStyle = [Windows.Forms.FormBorderStyle]::FixedDialog
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.StartPosition = [Windows.Forms.FormStartPosition]::CenterScreen
$form.Font = New-Object Drawing.Font('Segoe UI', 10)

function Add-FormLabel([string]$Text, [int]$Top, [int]$Height) {
    $label = New-Object Windows.Forms.Label
    $label.Text = $Text
    $label.SetBounds(22, $Top, 596, $Height)
    $form.Controls.Add($label)
}
function Add-FormField([string]$Label, [int]$Top, [int]$MaxLength) {
    Add-FormLabel $Label $Top 23
    $field = New-Object Windows.Forms.TextBox
    $field.MaxLength = $MaxLength
    $field.SetBounds(22, ($Top + 25), 596, 25)
    $form.Controls.Add($field)
    return $field
}

Add-FormLabel 'Use the values approved by your institute network administrator. Prepare the proxy files here. Follow the guide to set up the Windows task, firewall and device trust.' 19 60
$dns = Add-FormField 'Private ERP DNS name' 86 253
$bind = Add-FormField 'Reserved private IPv4 address on this PC' 146 15
$cidr = Add-FormField 'Approved staff IPv4 network and prefix' 206 18
$confirm = New-Object Windows.Forms.CheckBox
$confirm.Text = 'I have the approved private DNS name and staff-only network.'
$confirm.SetBounds(20, 272, 598, 34)
$form.Controls.Add($confirm)

$save = New-Object Windows.Forms.Button
$save.Text = 'Save new Caddyfile'
$save.SetBounds(320, 345, 170, 37)
$save.Enabled = $false
$form.Controls.Add($save)
$prepare = New-Object Windows.Forms.Button
$prepare.Text = 'Prepare proxy files'
$prepare.SetBounds(22, 345, 176, 37)
$prepare.Enabled = $false
$form.Controls.Add($prepare)
$export = New-Object Windows.Forms.Button
$export.Text = 'Export public CA certificate'
$export.SetBounds(22, 395, 286, 36)
$form.Controls.Add($export)
$close = New-Object Windows.Forms.Button
$close.Text = 'Close'
$close.SetBounds(505, 345, 113, 37)
$close.DialogResult = [Windows.Forms.DialogResult]::Cancel
$form.Controls.Add($close)
$form.AcceptButton = $prepare
$form.CancelButton = $close
$confirm.Add_CheckedChanged({
    $save.Enabled = $confirm.Checked
    $prepare.Enabled = $confirm.Checked
})
$prepare.Add_Click({
    try {
        $configuration = ConvertTo-PrivateHttpsConfiguration $dns.Text.Trim() $bind.Text.Trim() $cidr.Text.Trim() (Join-Path $PSScriptRoot 'Caddyfile.template')
        Confirm-LocalBindAddress $bind.Text.Trim()
        $picker = New-Object Windows.Forms.FolderBrowserDialog
        try {
            $picker.Description = 'Choose a local folder for the verified proxy files.'
            if ($picker.ShowDialog($form) -ne [Windows.Forms.DialogResult]::OK) { return }
            $output = Save-PrivateProxyFiles $picker.SelectedPath (Join-Path $PSScriptRoot 'caddy-windows-amd64.zip') $configuration
        } finally { $picker.Dispose() }
        [void][Windows.Forms.MessageBox]::Show($form,
            "Verified proxy files saved in $output. Apply the file permissions, task and firewall steps in the guide.",
            'Proxy files ready', 'OK', 'Information')
    } catch {
        [void][Windows.Forms.MessageBox]::Show($form, $_.Exception.Message, 'Private HTTPS setup', 'OK', 'Warning')
    }
})
$export.Add_Click({
    try {
        $root = 'C:\ProgramData\TOEFL House ERP\Private HTTPS\certificates\pki\authorities\local\root.crt'
        [byte[]]$public = Read-PrivateHttpsPublicCertificate $root
        $picker = New-Object Windows.Forms.SaveFileDialog
        try {
            $picker.Title = 'Save the public CA certificate'
            $picker.FileName = 'TOEFL House ERP Staff CA.cer'
            $picker.Filter = 'Public Windows certificate (*.cer)|*.cer'
            $picker.DefaultExt = 'cer'
            if ($picker.ShowDialog($form) -ne [Windows.Forms.DialogResult]::OK) { return }
            if ([IO.Path]::GetExtension($picker.FileName) -ine '.cer') { throw 'Choose an unused .cer file.' }
            Assert-PlainLocalDirectory ([IO.Path]::GetDirectoryName($picker.FileName))
            $file = [IO.File]::Open($picker.FileName, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            try { $file.Write($public, 0, $public.Length) }
            finally { $file.Dispose() }
        } finally { $picker.Dispose() }
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $hash = [BitConverter]::ToString($sha.ComputeHash($public)).Replace('-', '') }
        finally { $sha.Dispose() }
        [void][Windows.Forms.MessageBox]::Show($form,
            "Public certificate saved. SHA-256: $hash`r`nConfirm it to staff through a separate trusted channel.",
            'Public certificate exported', 'OK', 'Information')
    } catch {
        [void][Windows.Forms.MessageBox]::Show($form, $_.Exception.Message, 'Public certificate export', 'OK', 'Warning')
    }
})
$save.Add_Click({
    try {
        $name = $dns.Text.Trim()
        $address = $bind.Text.Trim()
        $network = $cidr.Text.Trim()
        $configuration = ConvertTo-PrivateHttpsConfiguration $name $address $network (Join-Path $PSScriptRoot 'Caddyfile.template')
        Confirm-LocalBindAddress $address
        $picker = New-Object Windows.Forms.SaveFileDialog
        try {
            $picker.Title = 'Save a new private Caddy configuration'
            $picker.FileName = 'Caddyfile'
            $picker.AddExtension = $false
            $picker.OverwritePrompt = $false
            $picker.CheckPathExists = $true
            if ($picker.ShowDialog($form) -ne [Windows.Forms.DialogResult]::OK) { return }
            Save-NewPrivateHttpsConfiguration $picker.FileName $configuration
        } finally {
            $picker.Dispose()
        }
        [void][Windows.Forms.MessageBox]::Show($form,
            "Saved a new Caddyfile for https://$($name.ToLowerInvariant())/. Follow the Private HTTPS administrator guide before enabling staff access.",
            'Configuration saved', 'OK', 'Information')
    } catch {
        [void][Windows.Forms.MessageBox]::Show($form, $_.Exception.Message, 'Private HTTPS setup', 'OK', 'Warning')
    }
})

try {
    if ($SmokeTest) {
        if ($save.Enabled -or $prepare.Enabled) { throw 'Proxy preparation must begin disabled.' }
        $confirm.Checked = $true
        if (-not $save.Enabled -or -not $prepare.Enabled) { throw 'Proxy preparation did not enable.' }
        $confirm.Checked = $false
        if ($save.Enabled -or $prepare.Enabled) { throw 'Proxy preparation remained enabled.' }
        'Private HTTPS form initialized.'
        return
    }
    [void]$form.ShowDialog()
} finally { $form.Dispose() }
