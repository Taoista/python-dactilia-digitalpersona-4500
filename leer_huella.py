"""Prueba local del DigitalPersona 4500 mediante Windows Biometric Framework."""
import argparse
import os
import threading
from multiprocessing.connection import Client
import time
import ctypes as c
from pathlib import Path
import sys

U32 = c.c_uint32
Size = c.c_size_t
Ptr = c.POINTER
Text = c.c_wchar * 256
FINGERPRINT = 8
SYSTEM_POOL = 1
RAW_ACCESS = 1
DEFAULT_DB = 1
RAW_DATA = 0x20


class Unit(c.Structure):
    _fields_ = [
        ("id", U32), ("pool", U32), ("factor", U32), ("subtype", U32),
        ("capabilities", U32), ("instance", Text), ("description", Text),
        ("manufacturer", Text), ("model", Text), ("serial", Text),
        ("firmware", U32 * 2),
    ]


def api():
    dll = c.WinDLL("winbio.dll", winmode=0x800)  # LOAD_LIBRARY_SEARCH_SYSTEM32
    signatures = {
        "WinBioEnumBiometricUnits": [U32, Ptr(Ptr(Unit)), Ptr(Size)],
        "WinBioOpenSession": [U32, U32, U32, Ptr(U32), Size, c.c_void_p, Ptr(U32)],
        "WinBioCaptureSample": [U32, c.c_ubyte, c.c_ubyte, Ptr(U32),
                                Ptr(c.c_void_p), Ptr(Size), Ptr(U32)],
        "WinBioCloseSession": [U32],
        "WinBioCancel": [U32],
        "WinBioFree": [c.c_void_p],
    }
    for name, args in signatures.items():
        fn = getattr(dll, name)
        fn.argtypes = args
        fn.restype = c.c_int32
    return dll


def check(result, operation):
    if result < 0:
        code = result & 0xffffffff
        hint = ("Abre PowerShell como administrador." if code == 0x80070005
                else c.FormatError(result).strip())
        raise RuntimeError(f"{operation} (0x{code:08X}). {hint}")


def readers(dll):
    units = Ptr(Unit)()
    count = Size()
    check(dll.WinBioEnumBiometricUnits(FINGERPRINT, c.byref(units), c.byref(count)),
          "Error al consultar lectores WBF")
    try:
        return {u.id: u.description for u in units[:count.value]
                if "VID_05BA&PID_000A" in u.instance.upper()} if count.value else {}
    finally:
        if units:
            dll.WinBioFree(units)


def capture(dll, devices, output, timeout=None):
    session, unit, reason = U32(), U32(), U32()
    sample, size = c.c_void_p(), Size()
    check(dll.WinBioOpenSession(FINGERPRINT, SYSTEM_POOL, RAW_ACCESS, None, 0,
                                DEFAULT_DB, c.byref(session)), "Error al abrir sesión")
    try:
        print("Mantén esta ventana activa y apoya un dedo sobre el 4500.", flush=True)
        timer = threading.Timer(timeout, dll.WinBioCancel, args=(session,)) if timeout else None
        if timer:
            timer.start()
        try:
            result = dll.WinBioCaptureSample(session, 0, RAW_DATA, c.byref(unit),
                                             c.byref(sample), c.byref(size), c.byref(reason))
        finally:
            if timer:
                timer.cancel()
                timer.join()
        if timer and result & 0xffffffff == 0x80098004:
            raise RuntimeError("El lector aún no entregó una muestra. Reintentando la conexión.")
        check(result, f"Error al capturar (detalle del sensor {reason.value})")
        if unit.value not in devices:
            raise RuntimeError("La muestra proviene de otro lector. Repite usando el 4500.")
        if not sample or not size.value:
            raise RuntimeError("El sensor devolvió una muestra vacía.")
        print(f"Huella leída con {devices[unit.value]}: {size.value} bytes.")
        data = c.string_at(sample, size.value)
        if output:
            with output.open("xb") as file:
                file.write(data)
            print(f"Muestra BIR guardada en {output.resolve()}")
        return data
    finally:
        if sample:
            dll.WinBioFree(sample)
        dll.WinBioCloseSession(session)


def stream(port, key):
    c.windll.kernel32.SetConsoleTitleW("Dactilia - sensor 4500")
    dll = api()
    with Client(("127.0.0.1", port), authkey=bytes.fromhex(key)) as link:
        # Al cerrar Angular, terminar incluso si WinBio está bloqueado en captura.
        def monitor():
            try:
                link.recv_bytes(1)
            except (OSError, EOFError):
                os._exit(0)
        threading.Thread(target=monitor, daemon=True).start()
        while True:
            try:
                devices = readers(dll)
                if not devices:
                    raise RuntimeError("Conecta el DigitalPersona 4500 por USB.")
                link.send_bytes(b"R")
                data = capture(dll, devices, None, timeout=30)
                link.send_bytes(b"I" + data)
                time.sleep(1)
            except RuntimeError as exc:
                link.send_bytes(b"E" + str(exc).encode("utf-8"))
                time.sleep(3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("listar", help="Comprobar si WBF reconoce el 4500")
    scan = actions.add_parser("capturar", help="Leer una sola huella")
    scan.add_argument("--guardar", type=Path, metavar="ARCHIVO.bir",
                      help="Guardar la muestra en un archivo nuevo")
    live = actions.add_parser("escuchar", help=argparse.SUPPRESS)
    live.add_argument("port", type=int)
    live.add_argument("key")
    args = parser.parse_args()
    if args.action == "escuchar":
        return stream(args.port, args.key)
    dll = api()
    devices = readers(dll)
    if not devices:
        raise RuntimeError("WBF no detecta el 4500. Comprueba el controlador WBF y la conexión USB.")
    for unit, name in devices.items():
        print(f"Unidad {unit}: {name}")
    if args.action == "capturar":
        capture(dll, devices, args.guardar)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError) as exc:
        sys.exit(str(exc))
