# Visor 3D de casos (exploratorio)

Visor geoespacial en 3D de incendios de la estación seca 2025 en Coclé. Combina relieve real, detecciones FIRMS del paquete público y comparaciones Sentinel-2 antes/después.

Los Picachos se analizó y se retiró del visor: las nubes taparon el 77 % de la zona y no hay nada que mostrar sobre el incendio reportado. El resultado queda documentado en `results/picachos/` y abajo.

> **Fuera de FirePA Scientific Pilot v1.** Nada de esta carpeta modifica el freeze, el paquete `site-data/` ni el sitio publicado. Las mediciones Sentinel-2 de aquí son exploratorias, no revisadas por expertos, y no son resultados del piloto.

## Qué muestra

| Caso | Observado (v1) | Medido aquí (exploratorio) |
|---|---|---|
| Cerro Guacamaya | 6 grupos FIRMS, 19 detecciones VIIRS, 72.7 h | Cicatriz de ~691 ha (dNBR 0.20; 601–754 ha entre umbrales 0.40 y 0.10). Envolvente de ~1,210 ha (huella completa de los píxeles) frente a 1,035–1,500 ha reportadas |
| Cerro Los Picachos (retirado del visor) | 0 coincidencias; señal más cercana a 10.4 km | Solo el 23 % de la zona de 5 km tiene dato válido: no se confirma ni se descarta el incendio. La señal del 15 ene coincide con una quema nueva de ~25 ha a 195 m |

Reglas de presentación:

- Nada se interpola entre detecciones.
- Los puntos son centroides de visualización, no ubicaciones del fuego.
- Las columnas codifican el FRP máximo (35 m por MW), no llamas.
- Lo que no se pudo observar se marca en gris como "sin dato".
- La cicatriz se mide en celdas de 20 m. Para mostrarla se suaviza a 5 m (`scripts/scar_style.py`) y su borde se dibuja como vector; el área sale siempre de las celdas.
- La cortina antes/después solo cambia qué foto se ve a cada lado de una línea norte-sur. No anima el fuego.
- Las columnas suben en 90 min de la línea de tiempo como animación de aparición; su altura final es el dato.

## Cómo reconstruirlo

Requiere Python con `numpy`, `Pillow` y `pyproj`, y acceso a internet para los datos abiertos. Desde la raíz del repositorio:

1. **Relieve.** Descargar las teselas `Copernicus_DSM_COG_10_N08_00_W081_00_DEM.tif` y `..._N09_...` (~47 MB) del bucket público `https://copernicus-dem-30m.s3.amazonaws.com/` a `data/raw/` dentro de esta carpeta. Luego:
   ```bash
   python explorations/case-viewer-3d/scripts/build_tiles.py
   ```
2. **Guacamaya Sentinel-2.** Ejecutar `s2_guacamaya.py` (descarga ~50 MB de recortes) y después `s2_context.py` (~37 MB; solo imagen de presentación).
3. **Los Picachos (opcional, retirado del visor).** `build_picachos_case.py` y después `s2_picachos.py` (~206 MB de recortes) reescriben `results/picachos/`.
4. **Ver.** Servir `web/` con cualquier servidor estático, por ejemplo `python -m http.server 8765 --directory explorations/case-viewer-3d/web`, y abrir `?caso=guacamaya`.

5. **Publicar en el sitio.** Ejecutar `python explorations/case-viewer-3d/scripts/export_to_site.py`. Copia el visor generado a `site/public/explorar/` con un `manifest.json` de hashes. El sitio lo sirve en `/explorar/` y la prueba del contrato del sitio verifica cada archivo. Cualquier cambio en el visor requiere volver a exportar.

Los recortes quedan en `data/s2_cache/`. Las ejecuciones posteriores no vuelven a descargar. Se pueden borrar cuando los resultados estén generados.

## Archivos

- `scripts/build_tiles.py`: teselas de elevación (Terrarium) y relieve sombreado para ambos casos, y `case.json` de Guacamaya a partir de `site-data/`.
- `scripts/build_picachos_case.py`: ancla, cero oficial y eventos FirePA v1 a ≤ 15 km entre el 5 y el 31 de enero (contexto, no coincidencias).
- `scripts/cog.py`: lector de Cloud-Optimized GeoTIFF por peticiones HTTP Range. Solo baja los bloques del recorte, incluidas las versiones reducidas internas.
- `scripts/s2_guacamaya.py`, `scripts/s2_picachos.py`: análisis dNBR.
- `scripts/s2_context.py`: imágenes de contexto (20 m) y de detalle con bordes difuminados.
- `scripts/scar_style.py`: relleno suavizado y contorno vectorial de la cicatriz, solo para mostrarla.
- `scripts/scar_search.py`: búsqueda de cicatrices en todo Coclé (ver abajo).
- `scripts/export_to_site.py`: copia el visor a `site/public/explorar/` para publicarlo.
- `web/`: visor MapLibre GL JS 5.6.0. `viewer.js` es el motor y `cases.js` el contenido de cada caso. Se suben los JSON de resultados; las imágenes y teselas se regeneran.

## Método Sentinel-2 y diferencias con el diseño dNBR del repo

- **Igual que el diseño del repo:** `NBR = (B8 − B12) / (B8 + B12)`, `dNBR = NBR_pre − NBR_post`, rejilla EPSG:32617 a 20 m, máscara común antes/después, umbrales 0.10–0.40 como sensibilidad descriptiva.
- **Distinto:**
  - La máscara de nubes usa la clasificación SCL de Sentinel-2, no Cloud Score+.
  - Se usa una ventana fija alrededor de cada caso, no el buffer de 500 m alrededor de las detecciones.
  - Se usa una sola pareja de escenas.
- **Guacamaya:**
  - Escenas del 21 ene (antes) y del 31 ene de 2025 (después), con 95.8 % de píxeles válidos comunes.
  - La mancha principal se conecta a los grupos FirePA (algún píxel a ≤ 1 km de un centroide).
  - No hay nubes a menos de 500 m de la cicatriz.
- **Los Picachos:**
  - "Antes" es un mosaico píxel a píxel de la escena despejada más reciente: 11 ene, si no 6 ene, si no 22 dic. "Después" es el 21 ene.
  - Se añade un margen circular de 300 m alrededor de nubes y sombras, sin envolver los bordes de la ventana. Sin él aparecían falsas quemas junto al ancla.
  - No hay detecciones FIRMS a las que conectar las manchas, así que se listan como candidatas, con su distancia al ancla y a la señal del 15 ene.
- **Corrección de reflectancia:** los metadatos STAC anuncian un desplazamiento de −0.1, pero estos COG ya lo traen aplicado (azul p5 ≈ 190 DN). El script lo comprueba y no lo aplica dos veces.

## Búsqueda de casos por satélite

Solo Guacamaya y Los Picachos tenían noticia con lugar y fecha. Para encontrar más casos se buscó al revés: primero la cicatriz, después la confirmación.

1. **Escaneo (`scar_search.py`).** Todas las escenas de la tesela 17PNK (casi todo Coclé) entre el 10 de diciembre de 2024 y el 21 de mayo de 2025, leídas solo en la versión interna de ~80 m de los COG (~130 MB en total). Por periodo (dic–ene, ene–feb, feb–mar, mar–abr, abr–may) se calcula la mediana por píxel del NBR de los píxeles despejados (SCL 2, 4, 5, 7, a más de 160 m de nubes o sombras). Una mancha candidata cumple dNBR > 0.27 entre periodos consecutivos, NBR posterior < 0.10 y al menos 40 ha dentro de Coclé.
2. **Corroboración.** Se cuentan los eventos FIRMS del paquete v1 a ≤ 1 km de la mancha y dentro de los dos periodos. Es una confirmación independiente: el escaneo no usa FIRMS.
3. **Orden (`rank_candidates.py`).** Área, relieve del DSM alrededor (lo que luce en 3D) y FIRMS. Las manchas con forma de parcela en llano se marcan, porque suelen ser quemas de caña o arroz.
4. **Medición (`build_scar_case.py`).** Los casos elegidos se miden de nuevo a 20 m con una sola pareja de escenas, como Guacamaya, más el margen de 300 m alrededor de nubes. El área del visor sale de ese paso, no del escaneo.

Las medianas por periodo quedan en `data/s2_cache/` para no repetir la descarga; se pueden borrar.

## Hallazgos que merecen revisión

- **Ancla de Guacamaya.** Está a 28 m de elevación, en llano, unos 3.8 km al este de la cumbre de 643 m que rodean los seis grupos.
- **Pasos del satélite.** Todas las detecciones de Guacamaya caen entre ~01:00–02:15 y ~13:15–14:20 hora de Panamá, que son las ventanas de paso de VIIRS. Los huecos pueden reflejar la cadencia del satélite y no pausas del fuego.

## Detalles técnicos

- MapLibre 5.6 guarda en caché las capas proyectadas sobre el terreno 3D. Tras cambiar opacidades se llama a `terrain.sourceCache.freeRtt()`, una API interna, con la versión fijada.
- El DEM de Copernicus es un modelo de superficie: incluye el dosel. La exageración vertical es ×1.5.

## Atribución

- Relieve: Copernicus DEM GLO-30 © DLR e.V. 2010-2014 y © Airbus Defence and Space GmbH 2014-2018, provisto bajo COPERNICUS por la Unión Europea y la ESA.
- Imagen: contains modified Copernicus Sentinel data 2024-2025, vía Earth Search (Element84) en AWS.
- Detecciones: NASA FIRMS a través del paquete público de FirePA v1.
