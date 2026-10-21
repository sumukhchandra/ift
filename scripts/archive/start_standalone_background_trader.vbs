' AlphaNSE V3 - Windows Standalone Detached Background Launcher
' Runs completely independent of Antigravity or any IDE window.
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "c:\Users\sumuk\.gemini\antigravity-ide\scratch\ift"
WshShell.Run "pythonw scripts\run_session14_kotak_live_trader.py", 0, False
