"""Regresión del formato WBF del DigitalPersona 4500, sin datos biométricos."""
import struct
import unittest
import zlib

from estacion import fingerprint_png


class Imagen4500Test(unittest.TestCase):
    def test_ignora_reserva_del_controlador_al_generar_png(self):
        width, height = 320, 360
        row = bytes(i % 256 for i in range(width))
        pixels = row * height
        record_size = 16 + len(pixels) + 640
        block = bytearray(40 + record_size)
        struct.pack_into("<QII", block, 0, len(block), 0x46495200, 0x30313000)
        block[34] = 8
        struct.pack_into("<IHH", block, 40, record_size, width, height)
        block[56:56 + len(pixels)] = pixels
        block[-640:] = b"\xff" * 640
        bir = bytearray(80) + block
        struct.pack_into("<II", bir, 8, len(block), 80)
        self.assertEqual(len(bir), 115976)
        png, image_width, image_height = fingerprint_png(bir)
        self.assertEqual((image_width, image_height), (width, height))
        length, kind = struct.unpack_from(">I4s", png, 33)
        self.assertEqual(kind, b"IDAT")
        self.assertEqual(zlib.decompress(png[41:41 + length]), (b"\x00" + row) * height)
