"""Enrolamiento local con tres impresiones y comparación de minucias SourceAFIS."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3

import jpype
import jpype.config

MOTOR = Path(__file__).resolve().parent / '.runtime' / 'sourceafis-3.18.1'
UMBRAL = 40


class Registro:
    def __init__(self, db):
        self.db = db
        self.db.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(db)) as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS personas (
                    id INTEGER PRIMARY KEY, nombre TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS impresiones (
                    persona INTEGER NOT NULL REFERENCES personas(id),
                    numero INTEGER NOT NULL CHECK(numero BETWEEN 1 AND 3),
                    png BLOB NOT NULL, plantilla BLOB NOT NULL,
                    PRIMARY KEY(persona, numero)
                );
            """)
        self.modo = 'leer'
        self.nombre = ''
        self.muestras = []
        self.resultado = 'Apoya un dedo para buscar su nombre.'

    def cambiar(self, modo, nombre=''):
        if modo not in ('leer', 'enrolar'):
            raise ValueError('Sección desconocida.')
        nombre = nombre.strip()
        if len(nombre) > 120:
            raise ValueError('Usa un nombre de hasta 120 caracteres.')
        self.modo = modo
        self.nombre = nombre if modo == 'enrolar' else ''
        self.muestras = []
        self.resultado = ('Apoya un dedo para buscar su nombre.' if modo == 'leer' else
                          'Apoya el mismo dedo tres veces, levantándolo entre lecturas.' if nombre else
                          'Escribe el nombre para iniciar el enrolamiento.')

    def _motor(self):
        if not jpype.isJVMStarted():
            # El comparador solo usa memoria; el hilo del sensor puede estar
            # bloqueado en WinBio cuando Windows cierra la ventana.
            jpype.config.onexit = False
            jpype.startJVM(classpath=[str(MOTOR / '*')])
        return jpype.JPackage('com').machinezoo.sourceafis

    def _nombres(self, con, matcher, motor):
        coincidencias = {}
        for persona, nombre, plantilla in con.execute("""
            SELECT p.id, p.nombre, i.plantilla FROM personas p
            JOIN impresiones i ON i.persona=p.id ORDER BY p.id, i.numero
        """):
            score = matcher.match(motor.FingerprintTemplate(plantilla))
            if score >= UMBRAL:
                coincidencias.setdefault(persona, []).append(nombre)
        return [nombres[0] for nombres in coincidencias.values() if len(nombres) >= 2]

    def procesar(self, png):
        if self.modo == 'enrolar' and not self.nombre:
            return
        motor = self._motor()
        imagen = motor.FingerprintImage(png, motor.FingerprintImageOptions().dpi(508))
        plantilla = motor.FingerprintTemplate(imagen)
        matcher = motor.FingerprintMatcher(plantilla)
        if self.modo == 'leer':
            with closing(sqlite3.connect(self.db)) as con:
                nombres = self._nombres(con, matcher, motor)
            if len(nombres) == 1:
                self.resultado = f'Huella registrada · {nombres[0]}'
            elif nombres:
                self.resultado = 'Coincidencia ambigua. Levanta el dedo y repite la lectura.'
            else:
                self.resultado = 'Huella no registrada.'
            return
        if any(matcher.match(anterior) < UMBRAL for _, anterior in self.muestras):
            self.resultado = 'La huella no coincide con las anteriores. Repite con el mismo dedo.'
            return
        lote = [*self.muestras, (png, plantilla)]
        if len(lote) < 3:
            self.muestras = lote
            self.resultado = f'{len(lote)} de 3 aceptadas. Levanta el dedo y vuelve a apoyarlo.'
            return
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute('BEGIN IMMEDIATE')
            existentes = self._nombres(con, matcher, motor)
            if existentes:
                self.resultado = ('Esta huella ya está registrada · ' + existentes[0]
                                  if len(existentes) == 1 else 'Esta huella coincide con varios registros.')
            else:
                persona = con.execute('INSERT INTO personas(nombre) VALUES (?)', (self.nombre,)).lastrowid
                con.executemany('INSERT INTO impresiones VALUES (?,?,?,?)', [
                    (persona, numero, foto, bytes(t.toByteArray()))
                    for numero, (foto, t) in enumerate(lote, 1)
                ])
                self.resultado = f'Enrolamiento completado · {self.nombre}. Se guardaron las tres capturas.'
        self.nombre = ''
        self.muestras = []
