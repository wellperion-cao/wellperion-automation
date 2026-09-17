' Wellperion Guide Edits Apply - hidden launcher (no console window)
' Pulls the server save queue (/api/guide/pending) and commits it into the repo every 10 minutes.
' Consumers: erp/admin/clevel-guide.html (bootsetup_matrix.json) and erp/admin/ideas.html (status/gm_personal_routine.json).
' Created by AI CTO (2026-09-17): the scheduled task was documented in scripts/guide_edits_apply.py but never registered.
' ASCII only in this file (cp949 shell) - see lessons 2026-09-16.
rc = CreateObject("WScript.Shell").Run("cmd /c cd /d C:\Users\jjky0\welperion-automation& set PYTHONIOENCODING=utf-8& C:\Python314\python.exe -u scripts\guide_edits_apply.py >> logs\guide_edits_apply.log 2>&1", 0, True)
WScript.Quit rc
