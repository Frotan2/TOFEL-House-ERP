Option Explicit
Dim shell, fs, folder, scriptPath, powershellPath
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
scriptPath = fs.BuildPath(folder, "Owner Activation Request.ps1")
powershellPath = shell.ExpandEnvironmentStrings("%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe")
If Not fs.FileExists(scriptPath) Then
    MsgBox "The Owner activation request form is missing. Use the verified delivery package.", vbCritical, "TOEFL House ERP"
    WScript.Quit 1
End If
shell.Run """" & powershellPath & """ -NoLogo -NoProfile -STA -WindowStyle Hidden -File """ & scriptPath & """", 0, False
