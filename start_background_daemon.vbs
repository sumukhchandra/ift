Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "c:\Users\sumuk\OneDrive\Desktop\lft"
WshShell.Run "cmd /c start_continuous_trader.bat", 0, False
