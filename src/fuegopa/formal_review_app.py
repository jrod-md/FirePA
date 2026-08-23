"""Local Streamlit UI for one explicitly authorized formal-review slot.

The launcher supplies the round, slot and profile.  There is intentionally no
free slot selector: the server validates the binding before loading the
slot-specific private map.  This is a local supervised isolation boundary, not
a claim of protection from a person who owns the filesystem or SQLite file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .formal_review import (
    ASSOCIATION_CODES,
    CONFIDENCE_CODES,
    FORMAL_OUTPUT_DIR,
    FORMAL_ROUND_ID,
    LIMITATION_CODES,
    MODE_CODES,
    REQUEST_REASON_CODES,
    SURFACE_CODES,
    VISIBLE_CODES,
    FormalReviewError,
    FormalReviewStore,
)
from .human_review_schema import DEFAULT_DB_PATH, ROOT


LABELS = {
    "yes": "Sí", "no": "No", "ambiguous": "Ambigua", "high": "Alta",
    "medium": "Media", "low": "Baja", "likely": "Probable",
    "possible": "Posible", "unlikely": "Improbable", "indeterminate": "Indeterminada",
    "none_visible": "Ninguno visible", "agriculture_or_harvest": "Agricultura o cosecha",
    "soil_exposure": "Suelo expuesto", "vegetation_phenology": "Fenología",
    "moisture_or_flooding": "Humedad o inundación", "water": "Agua",
    "urban_or_construction": "Urbanización o construcción", "mixed": "Mezcla",
    "unknown": "Desconocido", "none": "Ninguna", "cloud_or_haze": "Nube o bruma",
    "mask_or_nodata": "Máscara o nodata", "shadow": "Sombra",
    "partial_coverage": "Cobertura parcial", "insufficient_temporal_separation": "Separación temporal insuficiente",
    "other": "Otra", "agree": "Coinciden", "partially_agree": "Coinciden parcialmente",
    "disagree": "No coinciden",
}


def _select(st: Any, title: str, codes: tuple[str, ...], value: str | None, key: str, *, disabled: bool = False) -> str:
    options = [""] + list(codes)
    current = value if value in options else ""
    return st.selectbox(
        title,
        options=options,
        index=options.index(current),
        format_func=lambda code: "Seleccione una opción" if not code else LABELS.get(code, code),
        key=key,
        disabled=disabled,
    )


def _slot_private_map(path: Path, slot_id: str) -> dict[str, Any]:
    """Load only one slot's private map; never load the combined A+B join."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FormalReviewError(f"No se pudo leer el mapa privado del slot: {path}") from exc
    if payload.get("slot_id") != slot_id or set(payload.get("items", {})) != {slot_id}:
        raise FormalReviewError("El mapa privado no corresponde exclusivamente al slot solicitado")
    return payload


def run_formal_app(
    *,
    round_id: str,
    slot_id: str,
    profile_id: str,
    session_token: str,
    root: Path | str = ROOT,
    db_path: Path | str = DEFAULT_DB_PATH,
    output_dir: Path | str = FORMAL_OUTPUT_DIR,
) -> None:
    """Run one server-validated slot session; no slot choice is exposed in UI."""

    try:
        import streamlit as st
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Falta Streamlit; instale las dependencias de desarrollo.") from exc
    if not round_id or not slot_id or not profile_id or not session_token:
        raise FormalReviewError("La sesión formal requiere round_id, slot_id, profile_id y token local")
    if round_id != FORMAL_ROUND_ID:
        raise FormalReviewError("La aplicación formal solo admite la ronda preparada declarada")
    root_path = Path(root)
    private_path = Path(output_dir) / "private" / slot_id.lower() / "assignment_map.json"
    with FormalReviewStore(db_path) as store:
        store.initialize()
        try:
            store.validate_slot_session(round_id, slot_id, profile_id)
        except FormalReviewError as exc:
            st.error("La sesión no está autorizada para este slot.")
            st.stop()
            raise exc
        private_map = _slot_private_map(private_path, slot_id)
        session_key = "formal_local_session_token"
        if session_key not in st.session_state:
            st.session_state[session_key] = session_token
        if st.session_state[session_key] != session_token:
            st.error("La sesión local no coincide con el contexto de lanzamiento.")
            st.stop()
        st.set_page_config(page_title="FirePA · revisión formal local", layout="wide")
        st.title("FirePA — revisión formal ciega")
        st.caption("Herramienta local de observación humana; no es una interfaz pública ni una salida científica.")
        st.warning("La revisión registra observaciones y limitaciones. No convierte una observación en verdad científica.")

        assignments = store.list_assignments(round_id, slot_id)
        private_items = private_map["items"][slot_id]
        private_by_alias = {item["blind_alias"]: item for item in private_items}
        if len(assignments) != 28 or len(private_by_alias) != 28:
            st.error("El paquete del slot no tiene exactamente 28 asignaciones.")
            return
        current_key = f"formal_order_{round_id}_{slot_id}"
        order = int(st.session_state.get(current_key, 1))
        order = max(1, min(order, len(assignments)))
        st.session_state[current_key] = order
        assignment = assignments[order - 1]
        alias = assignment["blind_alias"]
        private = private_by_alias.get(alias)
        if private is None:
            st.error("No se encontró la referencia visual privada del alias.")
            return
        event_id = str(private["event_id"])
        panel_path = root_path / str(private["quicklook_path"])
        st.write(f"**Alias ciego:** `{alias}` · **Orden:** {order} de {len(assignments)}")
        st.image(str(panel_path), caption="Panel multispectral — Pass A")
        current_a = store.get_pass_a(round_id, slot_id, event_id)
        if current_a:
            st.subheader("Pass A — bloqueada")
            for field, codes in (
                ("visible_burn_scar", VISIBLE_CODES), ("scar_confidence", CONFIDENCE_CODES),
                ("event_association", ASSOCIATION_CODES), ("competing_land_change", SURFACE_CODES),
                ("observation_limitation", LIMITATION_CODES),
            ):
                _select(st, field, codes, current_a.get(field), f"locked_{field}_{alias}", disabled=True)
            st.text_area("Notas Pass A", value=current_a.get("notes") or "", disabled=True, key=f"locked_notes_{alias}")
            amend = st.checkbox("Habilitar enmienda auditada", key=f"amend_{alias}")
        else:
            amend = False
        if not current_a or amend:
            st.subheader("Pass A — observación multiespectral")
            visible = _select(st, "Observación visible", VISIBLE_CODES, current_a.get("visible_burn_scar") if current_a else None, f"visible_{alias}")
            confidence = _select(st, "Confianza", CONFIDENCE_CODES, current_a.get("scar_confidence") if current_a else None, f"confidence_{alias}")
            association = _select(st, "Asociación con el evento", ASSOCIATION_CODES, current_a.get("event_association") if current_a else None, f"association_{alias}")
            surface = _select(st, "Cambio competidor", SURFACE_CODES, current_a.get("competing_land_change") if current_a else None, f"surface_{alias}")
            limitation = _select(st, "Limitación de observación", LIMITATION_CODES, current_a.get("observation_limitation") if current_a else None, f"limitation_{alias}")
            notes = st.text_area("Notas Pass A", value=current_a.get("notes") or "" if current_a else "", key=f"notes_{alias}")
            amendment_reason = st.text_input("Razón de enmienda", key=f"amend_reason_{alias}") if amend else ""
            if st.button("Guardar Pass A", key=f"save_a_{alias}", type="primary"):
                try:
                    store.save_pass_a(
                        round_id=round_id, slot_id=slot_id, event_id=event_id,
                        visible_burn_scar=visible, scar_confidence=confidence,
                        event_association=association, competing_land_change=surface,
                        observation_limitation=limitation, notes=notes, amend=amend,
                        amendment_reason=amendment_reason,
                    )
                    st.success("Pass A guardada y bloqueada.")
                except FormalReviewError as exc:
                    st.error(str(exc))
        current_a = store.get_pass_a(round_id, slot_id, event_id)
        if current_a and current_a.get("visible_burn_scar") != "unobserved":
            st.divider()
            st.info("Pass B permanece bloqueada: no existe una referencia local window_median congelada; selected_pair no se reutiliza como sustituto.")
        previous, _, following = st.columns(3)
        with previous:
            if st.button("Anterior", disabled=order <= 1, key="formal_previous"):
                st.session_state[current_key] = order - 1
                st.rerun()
        with following:
            if st.button("Siguiente", disabled=order >= len(assignments), key="formal_next"):
                st.session_state[current_key] = order + 1
                st.rerun()
