"""Estación Angular local. Abrir mediante Abrir estacion.cmd."""
import base64
import hashlib
import os
from pathlib import Path
import sqlite3
import struct
import ctypes
from contextlib import closing
import threading
import logging
import site
from ctypes import wintypes

site.addsitedir(str(Path(__file__).resolve().parent / '.venv/Lib/site-packages'))
import webview
import zlib

from registro import Registro
from leer_huella import api, readers, capture




ROOT = Path(__file__).resolve().parent
DB = Path(os.environ["LOCALAPPDATA"]) / "Huellas4500" / "capturas.sqlite3"


def fingerprint_png(bir):
    if len(bir) < 32:
        raise ValueError("Registro biométrico incompleto.")
    size, offset = struct.unpack_from("<II", bir, 8)
    block = bir[offset:offset + size]
    if len(block) != size or size < 50:
        raise ValueError("El registro carece de un bloque de imagen válido.")
    if block[8:12] == b"\x00RIF":
        # Windows serializa las estructuras ANSI 381 con enteros little-endian.
        depth, compression = block[34:36]
        # El 4500 declara 320 x 360 píxeles y reserva 640 bytes adicionales
        # al final del registro. BlockLength incluye esa reserva.
        for header_size, record_size in ((40, 16), (38, 14)):
            length, width, height = struct.unpack_from("<IHH", block, header_size)
            count = width * height
            available = size - header_size
            if width and height and record_size + count <= length <= available:
                start = header_size + record_size
                break
        else:
            raise ValueError("El formato de la imagen WBF requiere revisión. Ver lector.log.")
    elif block[:4] == b"FIR\x00":
        depth, compression = block[32:34]
        length = int.from_bytes(block[36:40], "big")
        width, height = struct.unpack_from(">HH", block, 45)
        start = 50
        record_size = 14
    else:
        raise ValueError("El lector entregó un formato de imagen desconocido.")
    count = width * height
    if (depth, compression) != (8, 0) or not 0 < count <= 8_000_000 or start + count > size or (block[:4] == b"FIR\x00" and length != count + record_size):
        raise ValueError(f"Imagen incompatible: {width} × {height}, {depth} bits, compresión {compression}.")
    pixels = memoryview(block)[start:start + count]
    scanlines = b"".join(b"\0" + pixels[row:row + width] for row in range(0, count, width))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b"")
    return png, width, height



class Station:
    def __init__(self):
        self._lock = threading.Lock()
        self._end = threading.Event()
        self._registro = Registro(DB)
        self._sample = None
        self._sequence = 0
        self._connected = False
        self._status = "Conectando con el lector…"

    def _prepare_windows(self, form_hwnd):
        user = ctypes.windll.user32
        kernel = ctypes.windll.kernel32
        kernel.GetConsoleWindow.restype = wintypes.HWND
        self._console = kernel.GetConsoleWindow()
        if not self._console:
            raise RuntimeError("Abre Dactilia con Abrir estacion.cmd.")
        self._window = form_hwnd
        user.GetForegroundWindow.restype = wintypes.HWND
        user.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        user.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        # La pantalla es una ventana propiedad de la consola de adquisición.
        # Windows conserva la pantalla encima incluso cuando WinBio usa la consola.
        user.SetWindowLongPtrW(form_hwnd, -8, self._console)
        self._align_console()

    def _align_console(self):
        user = ctypes.windll.user32
        rect = wintypes.RECT()
        if user.GetWindowRect(self._window, ctypes.byref(rect)) and not user.IsIconic(self._window):
            user.SetWindowPos(self._console, 0, rect.left + 32, rect.top + 64,
                              180, 56, 0x0014)  # NOACTIVATE | NOZORDER

    def _focus_loop(self):
        user = ctypes.windll.user32
        while not self._end.wait(0.3):
            if self._registro.modo == "enrolar" and not self._registro.nombre:
                continue
            if user.GetForegroundWindow() == self._window and not user.GetAsyncKeyState(1) & 0x8000:
                self._align_console()
                user.SetForegroundWindow(self._console)

    def _listen(self):
        dll = api()
        while not self._end.is_set():
            try:
                if self._registro.modo == "enrolar" and not self._registro.nombre:
                    self._end.wait(0.2)
                    continue
                devices = readers(dll)
                self._connected = bool(devices)
                if not devices:
                    raise RuntimeError("Conecta el DigitalPersona 4500 por USB.")
                self._status = "Apoya un dedo en el lector."
                data = capture(dll, devices, None, timeout=45)
                png, width, height = fingerprint_png(data)
                with self._lock:
                    if self._registro.modo == "enrolar" and not self._registro.nombre:
                        continue
                    self._sequence += 1
                    self._sample = (hashlib.sha256(png).hexdigest(), png, width, height)
                    try:
                        self._registro.procesar(png)
                    except Exception:
                        logging.exception("Error al comparar la captura")
                        self._registro.resultado = "Error al comparar o guardar la huella. Repite la captura."
                logging.info("Lectura %d recibida: %d x %d", self._sequence, width, height)
                self._status = "Levanta el dedo para la siguiente lectura."
                self._end.wait(0.6)
            except (OSError, ValueError, RuntimeError) as exc:
                self._status = str(exc)
                logging.warning("%s", exc)
                self._end.wait(1)

    def _close(self):
        self._end.set()

    def imagen_visible(self, digest, width, height):
        with self._lock:
            sample = self._sample
        if sample and (digest, width, height) == (sample[0], sample[2], sample[3]):
            logging.info("Angular mostró lectura %d: %d x %d", self._sequence, width, height)

    def seccion(self, modo, nombre=""):
        with self._lock:
            self._registro.cambiar(modo, nombre)
            self._sample = None
            return True

    def estado(self, last_sequence):
        with self._lock:
            result = {"connected": self._connected, "status": self._status}
            result.update(modo=self._registro.modo, nombre=self._registro.nombre,
                          aceptadas=len(self._registro.muestras), resultado=self._registro.resultado)
            if self._sample and self._sequence != last_sequence:
                digest, png, width, height = self._sample
                result["sample"] = {"sequence": self._sequence, "hash": digest, "image": base64.b64encode(png).decode(),
                                    "bytes": len(png), "width": width, "height": height}
            return result

    def guardar(self, digest):
        with self._lock:
            sample = self._sample
        if not sample or sample[0] != digest:
            raise ValueError("La captura cambió. Revisa la nueva imagen.")
        DB.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(DB)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS capturas (sha256 TEXT PRIMARY KEY, imagen_png BLOB NOT NULL, ancho INTEGER, alto INTEGER, fecha_utc TEXT DEFAULT CURRENT_TIMESTAMP)")
            db.execute("INSERT OR IGNORE INTO capturas(sha256,imagen_png,ancho,alto) VALUES (?,?,?,?)", sample)
        return True


if __name__ == "__main__":
    DB.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=DB.parent / "lector.log", level=logging.INFO,
                        format="%(asctime)s %(message)s", encoding="utf-8")
    logging.info("Inicio de Dactilia, captura integrada")
    station = Station()
    # WinBio recibe el foco de la ventana que muestra Angular.
    window = webview.create_window("Dactilia · Estación de huellas", (ROOT / "public/index.html").as_uri(),
                                   js_api=station, width=1100, height=850, min_size=(650, 600))
    window.events.closed += station._close
    def start_listener():
        station._prepare_windows(window.native.Handle.ToInt64())
        threading.Thread(target=station._focus_loop, daemon=True).start()
        threading.Thread(target=station._listen, daemon=True).start()

    window.events.loaded += start_listener
    webview.start(gui="edgechromium", private_mode=True)
