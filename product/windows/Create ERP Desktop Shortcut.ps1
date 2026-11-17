# Run on an approved, already installed Windows host.
$ErrorActionPreference = 'Stop'
$customer = Join-Path $env:LOCALAPPDATA 'TOEFL House ERP\Customer'
$entry = Join-Path $customer 'TOEFL House ERP.vbs'
$gui = Join-Path $customer 'product\windows\TOEFL House ERP.ps1'
$identity = Join-Path $customer 'product\data\activation\installed-image-identity.json'
$scriptHost = Join-Path $env:WINDIR 'System32\wscript.exe'
$desktop = [Environment]::GetFolderPath('Desktop')
if (-not $desktop -or -not (Test-Path -LiteralPath $desktop -PathType Container)) {
    throw 'The current Windows desktop folder is unavailable.'
}
foreach ($required in @($entry, $gui, $identity, $scriptHost)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw 'The installed ERP launcher or its installation record is missing.'
    }
}

$destination = Join-Path $desktop 'TOEFL House ERP.lnk'
$arguments = '"' + $entry + '"'
$shell = New-Object -ComObject WScript.Shell
if (Test-Path -LiteralPath $destination) {
    $item = Get-Item -LiteralPath $destination -Force
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'The desktop shortcut path is already occupied.'
    }
    $link = $shell.CreateShortcut($destination)
    if ($link.TargetPath -ine $scriptHost -or $link.Arguments -cne $arguments -or
        $link.WorkingDirectory -ine $customer) {
        throw 'A different TOEFL House ERP shortcut already exists. Review it before replacing it.'
    }
} else {
    $link = $shell.CreateShortcut($destination)
    $link.TargetPath = $scriptHost
    $link.Arguments = $arguments
    $link.WorkingDirectory = $customer
    $link.Description = 'Open the installed TOEFL House ERP graphical launcher'
    $link.Save()

    $saved = $shell.CreateShortcut($destination)
    if ($saved.TargetPath -ine $scriptHost -or $saved.Arguments -cne $arguments -or
        $saved.WorkingDirectory -ine $customer) {
        throw 'Windows did not preserve the expected shortcut target.'
    }
}
Write-Output 'The TOEFL House ERP desktop shortcut is ready.'

$startup = [Environment]::GetFolderPath('Startup')
$worker = Join-Path $customer 'product\windows\Run TOEFL House ERP.ps1'
$windowsPowerShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not $startup -or -not (Test-Path -LiteralPath $startup -PathType Container) -or
    -not (Test-Path -LiteralPath $worker -PathType Leaf) -or
    -not (Test-Path -LiteralPath $windowsPowerShell -PathType Leaf) -or
    ((Get-Item -LiteralPath $startup).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'The current Windows sign-in shortcut location is unavailable.'
}
$startupLink = Join-Path $startup 'TOEFL House ERP - Start at sign-in.lnk'
$startArguments = '-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File "' + $worker + '" -Action Start'
$product = Join-Path $customer 'product'
if (Test-Path -LiteralPath $startupLink) {
    $existing = Get-Item -LiteralPath $startupLink -Force
    if ($existing.PSIsContainer -or ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'The ERP startup shortcut path is already occupied.'
    }
    $saved = $shell.CreateShortcut($startupLink)
    if ($saved.TargetPath -ine $windowsPowerShell -or $saved.Arguments -cne $startArguments -or
        $saved.WorkingDirectory -ine $product) {
        throw 'A different ERP startup shortcut already exists. It was preserved.'
    }
} else {
    $signIn = $shell.CreateShortcut($startupLink)
    $signIn.TargetPath = $windowsPowerShell
    $signIn.Arguments = $startArguments
    $signIn.WorkingDirectory = $product
    $signIn.Description = 'Start TOEFL House ERP when the current Windows operator signs in.'
    $signIn.Save()
    $saved = $shell.CreateShortcut($startupLink)
    if ($saved.TargetPath -ine $windowsPowerShell -or $saved.Arguments -cne $startArguments -or
        $saved.WorkingDirectory -ine $product) {
        throw 'Windows did not preserve the expected ERP startup shortcut.'
    }
}
Write-Output 'The TOEFL House ERP will start when this Windows user signs in.'
