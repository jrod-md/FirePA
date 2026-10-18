"""Cases built by build_scar_case.py, chosen from scar_search.py results.

Each entry fixes the scene pair, the measurement window and the text the viewer
shows. Numbers are not typed here: the viewer reads them from the JSON outputs.
Candidates were checked by eye on before/after thumbnails (candidate_thumbs.py);
field-shaped patches that turned out to be cane or rice harvests were dropped.
"""


def _views(lon, lat, pitch=62, bearing=-20):
    return {
        "overview": {"center": [lon, lat], "zoom": 11.9, "pitch": 40, "bearing": 0},
        "scar": {"center": [lon, lat], "zoom": 13.4, "pitch": pitch, "bearing": bearing},
        "close": {"center": [lon, lat], "zoom": 13.9, "pitch": pitch + 6, "bearing": bearing + 35},
    }


CASES: dict[str, dict] = {
    # scar_search rank 34: ridges south of Olá, burned around 28 Feb - 1 Mar 2025.
    "ola": {
        "title": "Cerros al sur de Olá",
        "place": "Olá, Coclé",
        "center": (-80.662, 8.385), "half_m": 6000,
        "view_aoi": (-80.79, 8.28, -80.53, 8.50),
        "pre": "S2B_17PNK_20250225_0_L2A", "post": "S2B_17PNK_20250307_0_L2A",
        "firms_window": ("2025-02-25", "2025-03-07"),
        "views": _views(-80.662, 8.385),
        "story": {
            "when": "febrero–marzo de 2025",
            "lede": "Un fuego sobre las crestas al sur de Olá que ninguna noticia registró. Lo encontramos buscando cicatrices desde el satélite.",
            "headline": "Un incendio que nadie reportó",
            "intro": "A finales de febrero de 2025 ardieron las laderas de unos cerros al sur de Olá. No encontramos noticias sobre él: apareció al revisar todo Coclé con fotos del satélite, y el sensor de calor VIIRS lo había detectado esos mismos días.",
            "chapter_title": "Cerros al sur de Olá",
            "chapter_intro": "Crestas y quebradas al sur de Olá, en el norte de Coclé. A unos kilómetros queda el Cerro Los Picachos, pero este fuego es de seis semanas después.",
            "unknowns": ["Si tiene relación con otras quemas de la zona en enero: las fechas no coinciden."],
        },
    },
    # scar_search rank 1: coastal plain east of Natá, burned in the second half of April 2025.
    "costa": {
        "title": "Llanura costera de Natá",
        "place": "Natá, Coclé",
        "center": (-80.431, 8.312), "half_m": 6000,
        "view_aoi": (-80.56, 8.21, -80.30, 8.43),
        "pre": "S2B_17PNK_20250416_0_L2A", "post": "S2C_17PNK_20250501_0_L2A",
        "firms_window": ("2025-04-16", "2025-05-01"),
        "views": _views(-80.431, 8.312, pitch=55, bearing=15),
        "story": {
            "when": "abril de 2025",
            "lede": "La quema más grande que encontramos en Coclé fuera de los cerros: una mancha negra que cruza potreros y linderos cerca de la costa.",
            "headline": "La mancha negra de la costa",
            "intro": "En la segunda mitad de abril de 2025 se quemó una gran extensión de sabana y pastizal en la llanura costera al este de Natá. Las fotos muestran el suelo negro cruzando cercas y caminos, algo distinto de la quema ordenada de una parcela.",
            "chapter_title": "La llanura costera",
            "chapter_intro": "Terreno plano, a pocos metros sobre el mar, entre potreros y estanques de camarón. Aquí el relieve no ayuda a ver el fuego: lo cuenta la foto.",
            "unknowns": ["Si empezó como una quema agrícola que se salió de control: la imagen no lo dice."],
        },
    },
}
