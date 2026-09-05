' Wellperion Reception/Lost-found health - hidden launcher (every 15 min, Wellperion-Reception-Health-15m)
' Created by AI COO (2026-09-05): GM "lost-found works on and off" -> probe member/staff paths every 15 min, alert only on change.
rc = CreateObject("WScript.Shell").Run("C:\Users\jjky0\welperion-automation\scripts\reception_health.bat", 0, True)
WScript.Quit rc
