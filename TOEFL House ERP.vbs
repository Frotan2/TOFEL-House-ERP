Option Explicit
' Double-click this file to open the Windows GUI without a terminal.
Dim shell, fs, root, gui, command
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
root = fs.GetParentFolderName(WScript.ScriptFullName)
gui = fs.BuildPath(root, "product\windows\TOEFL House ERP.ps1")
If Not fs.FileExists(gui) Then
    MsgBox "This TOEFL House ERP package is incomplete. Contact support.", vbCritical, "TOEFL House ERP"
    WScript.Quit 1
End If
command = "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & gui & """"
shell.Run command, 0, False
