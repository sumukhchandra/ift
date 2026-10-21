' AlphaNSE V3 - Standalone Detached Background Live Trader
' Runs completely independent of Antigravity or any IDE window in hidden mode (0).
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = currentDir
WshShell.Run "python launch_background.py", 0, False
