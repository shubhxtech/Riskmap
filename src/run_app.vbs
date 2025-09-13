Option Explicit

Dim fso, logFile, shell, scriptDir, appDir, Python, mainScript, modelsDir, logPath

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' Define paths
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
' go up one more parent
appDir = fso.GetParentFolderName(scriptDir)
Python = appDir & "\python\python.exe"
mainScript = appDir & "\src\main.py"
modelsDir = appDir & "\models"
logPath = appDir & "\logs\launcher.log"

' Ensure logs directory
If Not fso.FolderExists(appDir & "\logs") Then
    fso.CreateFolder(appDir & "\logs")
End If

' Open log file
Set logFile = fso.OpenTextFile(logPath, 8, True)
logFile.WriteLine "=== Launch attempt: " & Now & " ==="

' Check models folder
If Not fso.FolderExists(modelsDir) Then
    logFile.WriteLine "ERROR: Models folder missing."
    MsgBox "Models folder missing. Please reinstall or check your setup.", vbCritical, "Launch Error"
    WScript.Quit 1
End If

' Check Python
If Not fso.FileExists(Python) Then
    logFile.WriteLine "ERROR: Python environment missing."
    MsgBox "Python environment missing at " & Python & " . Please reinstall.", vbCritical, "Launch Error"
    WScript.Quit 1
End If

' Check main script
If Not fso.FileExists(mainScript) Then
    logFile.WriteLine "ERROR: Main script missing."
    MsgBox "Main application script not found.", vbCritical, "Launch Error"
    WScript.Quit 1
End If

' Launch app
logFile.WriteLine "Launching: " & Python & " " & mainScript
logFile.Close
shell.Run """" & Python & """ """ & mainScript & """", 0, False