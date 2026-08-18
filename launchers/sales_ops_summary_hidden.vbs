Set sh = CreateObject("WScript.Shell")
sh.Run "cmd /c ""C:\Python314\python.exe"" ""C:\Users\jjky0\welperion-automation\scripts\sales_report_ops_summary.py"" >> ""C:\Users\jjky0\welperion-automation\logs\sales_ops_summary.log"" 2>&1", 0, False
