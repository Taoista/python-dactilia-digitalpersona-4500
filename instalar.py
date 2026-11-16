"""Instala los componentes de Dactilia en la carpeta del proyecto."""
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PYTHON = VENV / "Scripts/python.exe"
MOTOR = ROOT / ".runtime/sourceafis-3.18.1"


def digest(path):
    with path.open("rb") as data:
        return hashlib.file_digest(data, "sha256").hexdigest()


def instalar_motor():
    MOTOR.mkdir(parents=True, exist_ok=True)
    for line in (ROOT / "motor.lock").read_text(encoding="ascii").splitlines():
        artifact, expected = line.split()
        target = MOTOR / Path(artifact).name
        if target.is_file() and digest(target) == expected:
            continue
        print(f"Descargando {target.name}", flush=True)
        with tempfile.TemporaryDirectory(dir=MOTOR) as tmp:
            download = Path(tmp) / target.name
            with urlopen("https://repo.maven.apache.org/maven2/" + artifact, timeout=90) as response:
                with download.open("wb") as output:
                    shutil.copyfileobj(response, output)
            if digest(download) != expected:
                raise ValueError(f"SHA-256 incorrecto para {target.name}")
            download.replace(target)


def main():
    if sys.platform != "win32" or sys.version_info[:2] != (3, 14) or struct.calcsize("P") != 8:
        raise SystemExit("Ejecuta Instalar.cmd con Python 3.14 de 64 bits en Windows.")
    subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    subprocess.run([str(PYTHON), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True)
    instalar_motor()
    subprocess.run([str(PYTHON), "-B", "-c",
                    "import webview, jpype; from registro import MOTOR; "
                    "jpype.startJVM(classpath=[str(MOTOR/'*')]); "
                    "jpype.JClass('com.machinezoo.sourceafis.FingerprintMatcher'); "
                    "print('Motor biometrico y dependencias Python verificados.')"],
                   cwd=ROOT, check=True)
    subprocess.run([str(PYTHON), "-B", "-m", "unittest", "test_imagen_4500"], cwd=ROOT, check=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(f"No se pudo completar la instalación: {exc}")
