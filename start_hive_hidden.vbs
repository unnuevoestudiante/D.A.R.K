' Lanza start_hive.bat oculto usando la carpeta donde vive este .vbs
' (antes tenía una ruta absoluta de un PC concreto: C:\Users\samue\...)
Set fso = CreateObject("Scripting.FileSystemObject")
carpeta = fso.GetParentFolderName(WScript.ScriptFullName)
bat = fso.BuildPath(carpeta, "start_hive.bat")
Set sh = CreateObject("Wscript.Shell")
sh.Run """" & bat & """", 0, False