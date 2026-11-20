"""Ayuda compartida de las suites de prueba: entrar con el PIN de la tienda.

El PIN de prueba se toma de la variable STOCK_PIN (por defecto 246810). Si la tienda todavía no tiene PIN,
las pruebas lo crean con ese valor; si ya tiene otro, pon STOCK_PIN con el PIN real antes de correrlas.
"""
import os

PIN = os.getenv("STOCK_PIN", "246810")


def entrar(cliente) -> None:
    """Inicia sesión en un httpx.Client (la cookie de sesión queda guardada en el cliente)."""
    estado = cliente.get("/api/acceso/estado").json()
    ruta = "/api/acceso/entrar" if estado["configurado"] else "/api/acceso/crear"
    r = cliente.post(ruta, json={"pin": PIN})
    assert r.status_code == 200, f"no pude entrar con el PIN de prueba ({r.status_code}): {r.text[:150]}"
