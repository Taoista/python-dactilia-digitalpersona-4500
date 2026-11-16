# Dactilia · Manual de instalación en Windows

Dactilia es una aplicación de escritorio para enrolar e identificar huellas con el lector USB DigitalPersona U.are.U 4500. La interfaz usa Angular, la captura usa Windows Biometric Framework y la comparación usa SourceAFIS. Los nombres, imágenes y plantillas de enrolamiento se guardan en SQLite en el equipo.

## 1. Instalar el controlador del 4500

1. Abre el enlace público y pulsa **Descargar** en Google Drive. El archivo es `4500_wbf_driver_5.0.0.5_rs3.zip`, versión WBF 5.0.0.5. [Descargar el controlador desde Google Drive](https://drive.google.com/file/d/1YJJEzeA7i3qT31JY1o3QhazD7N7vRRIG/view?usp=drivesdk) · [Ficha y descarga oficial de HID](https://www.hidglobal.com/es/media/4171)
2. Extrae el ZIP. En Windows de 64 bits, abre `setup\setup64.exe`, acepta el aviso de administrador y sigue el instalador.
3. Reinicia Windows al terminar y conecta el lector. En el Administrador de dispositivos debe aparecer **U.are.U 4500 Fingerprint Reader (WBF)**. La estación se probó en Windows 11 x64. La ficha de HID enumera sistemas hasta Windows 10.

El SHA-256 del ZIP es `cbd83f6abedd98fceceffe4c9005d895fc04530dc10867d649c396360c209cc6`. Puedes comprobarlo desde PowerShell en la carpeta de descarga.

```powershell
Get-FileHash .\4500_wbf_driver_5.0.0.5_rs3.zip -Algorithm SHA256
```

## 2. Instalar la aplicación

1. Clona el repositorio o descarga y extrae su ZIP en una carpeta donde tengas permiso de escritura.
2. Instala **Python 3.14 x64** con el comando `py`, **OpenJDK 17 x64** y **Microsoft Edge WebView2 Runtime** si aún faltan en el equipo. [Python para Windows](https://www.python.org/downloads/windows/) · [OpenJDK de Microsoft](https://learn.microsoft.com/es-es/java/openjdk/download) · [WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)
3. Desde la carpeta del proyecto, ejecuta **Instalar.cmd** con acceso a internet. El instalador prepara Python en `.venv`, descarga los componentes de SourceAFIS en `.runtime`, comprueba sus hashes y ejecuta una prueba de conversión de imagen. La interfaz Angular viene compilada.
4. Ejecuta **Abrir estacion.cmd** y acepta el aviso de Windows para que Dactilia pueda leer muestras del sensor.

## 3. Probar el lector

En **Enrolar**, escribe un nombre, pulsa **Iniciar enrolamiento** y apoya el mismo dedo tres veces. Levántalo entre lecturas. Espera la confirmación de guardado. En **Leer**, vuelve a apoyar el dedo y comprueba que aparezca el nombre registrado.

La base local se encuentra en `%LOCALAPPDATA%\Huellas4500\capturas.sqlite3`. Cada instalación nueva empieza con los registros disponibles en ese perfil de Windows.

Si la estación no detecta el lector, ejecuta `py -3.14 leer_huella.py listar` desde la carpeta del proyecto. Si el instalador informa que falta la JVM, comprueba que `JAVA_HOME` apunte a la carpeta del JDK de 64 bits y vuelve a ejecutar **Instalar.cmd**.
