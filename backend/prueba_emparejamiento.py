"""Prueba del buscador de productos (sin servidor ni IA): que tolere el dictado sin confundir tamaños ni marcas.

Uso:  python prueba_emparejamiento.py
"""
import sys
from pathlib import Path

src = Path(__file__).with_name("main.py").read_text(encoding="utf-8")
ns = {}
exec("import re, difflib, unicodedata\n" + src[src.index("def normalizar"):src.index("# ------------------------------------------------"
                                                                                       "---------------- Lotes")], ns)


class Con:
    def __init__(self, nombres):
        self.filas = [{"nombre": n, "id": i + 1} for i, n in enumerate(nombres)]

    def execute(self, *_):
        filas = self.filas
        return type("R", (), {"fetchall": lambda _s: filas})()


INVENTARIO = ["Coca-Cola 600 ml", "Coca-Cola 2.5 L", "Agua Ciel 1 L", "Leche Lala 1 L", "Artículo de prueba número 1",
              "Huevo", "Sabritas sal 45 g", "Jabón Zote", "Pan Bimbo grande", "Tortillas", "Galletas Marías",
              "Papel higiénico 4 rollos", "Atún Dolores", "Frijol pinto", "Maruchan", "Aceite 1-2-3 1 L", "Azúcar",
              "Arroz", "Jamón de pavo", "Café Nescafé 42 g"]
CASOS = {
    # lo que dicta el tendero o escribe el proveedor -> producto esperado (None = es otro producto: darlo de alta)
    "coca": "Coca-Cola 600 ml", "cocas": "Coca-Cola 600 ml", "Coca Cola": "Coca-Cola 600 ml",
    "COCA-COLA 600ML": "Coca-Cola 600 ml", "coca cola 2.5": "Coca-Cola 2.5 L", "Coca 600": "Coca-Cola 600 ml",
    "huevos": "Huevo", "jabones zote": "Jabón Zote", "Jabon zotte": "Jabón Zote", "Sabritas": "Sabritas sal 45 g",
    "sabritaz": "Sabritas sal 45 g", "leches lala": "Leche Lala 1 L", "panes bimbo": "Pan Bimbo grande",
    "tortilla": "Tortillas", "galleta maria": "Galletas Marías", "papel higienico": "Papel higiénico 4 rollos",
    "atunes": "Atún Dolores", "frijoles": "Frijol pinto", "maruchanes": "Maruchan", "azucar": "Azúcar",
    "arros": "Arroz", "Agua Ciel": "Agua Ciel 1 L", "jamon": "Jamón de pavo", "nescafe": "Café Nescafé 42 g",
    "agua": "Agua Ciel 1 L", "Bimbo": "Pan Bimbo grande",
    "Artículo de prueba número 12": None, "Artículo de prueba número 2": None, "Agua Ciel 600 ml": None,
    "Pepsi 600": None, "Gansito Marinela": None, "Leche Alpura 1 L": None, "Coca Light 600": None,
    "Leche Lala deslactosada 1 L": None, "": None,
}

con = Con(INVENTARIO)
fallas = 0
for dicho, esperado in CASOS.items():
    r = ns["buscar_producto"](con, dicho)
    obtenido = r["nombre"] if r else None
    if obtenido != esperado:
        fallas += 1
        print(f"❌ {dicho!r} -> {obtenido} (se esperaba {esperado})")
print(f"{len(CASOS) - fallas}/{len(CASOS)} emparejamientos correctos")
sys.exit(1 if fallas else 0)
