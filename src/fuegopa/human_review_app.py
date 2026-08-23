"""Local Streamlit interface for the blinded, two-pass human review."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .human_review_schema import (
    CALIBRATION_ROUND,
    COMPETING_LAND_CHANGE_CODES,
    DEFAULT_AUDIT_DIR,
    DEFAULT_DB_PATH,
    DEFAULT_EXPORT_DIR,
    EVENT_ASSOCIATION_CODES,
    MODE_AGREEMENT_CODES,
    ROOT,
    SCAR_CONFIDENCE_CODES,
    VISIBLE_BURN_SCAR_CODES,
)
from .human_review_store import HumanReviewStore, ReviewStoreError


DNBR_WARNING = "dNBR es evidencia espectral descriptiva; no confirma por sí solo un incendio."

CODE_LABELS: dict[str, dict[str, str]] = {
    "visible_burn_scar": {
        "": "Seleccione una opción",
        "yes": "Sí — cambio compatible con cicatriz visible",
        "no": "No — no se observa una cicatriz clara",
        "ambiguous": "Ambigua — la evidencia visual no permite decidir",
        "unobserved": "No observable — requiere una razón explícita",
    },
    "scar_confidence": {
        "": "Seleccione una opción",
        "high": "Alta — la observación es consistente",
        "medium": "Media — hay evidencia, con reservas",
        "low": "Baja — la señal es débil o difícil de interpretar",
        "not_applicable": "No aplica — la escena no es observable",
    },
    "event_association": {
        "": "Seleccione una opción",
        "likely": "Probable — asociación visual fuerte",
        "possible": "Posible — asociación plausible pero incierta",
        "unlikely": "Improbable — la asociación no convence",
        "indeterminate": "Indeterminada — no se puede resolver",
    },
    "competing_land_change": {
        "": "Seleccione una opción",
        "none_visible": "Ninguno visible",
        "agriculture_or_harvest": "Agricultura o cosecha",
        "soil_exposure": "Suelo expuesto",
        "vegetation_phenology": "Fenología de la vegetación",
        "moisture_or_flooding": "Humedad o inundación",
        "cloud_or_haze": "Nube o bruma",
        "shadow_or_atmosphere": "Sombra o atmósfera",
        "water": "Agua",
        "urban_or_construction": "Urbanización o construcción",
        "mixed": "Mezcla de cambios",
        "unknown": "Causa desconocida",
    },
    "mode_agreement": {
        "": "Seleccione una opción",
        "agree": "Coinciden",
        "partially_agree": "Coinciden parcialmente",
        "disagree": "No coinciden",
        "selected_pair_only": "Solo selected_pair es consistente",
        "window_median_only": "Solo window_median es consistente",
        "unavailable": "No disponible",
    },
}


def _rerun(st: Any) -> None:
    rerun = getattr(st, "rerun", None)
    if callable(rerun):
        rerun()


def _code_select(
    st: Any,
    *,
    field: str,
    title: str,
    codes: Sequence[str],
    value: str | None,
    key: str,
    disabled: bool = False,
) -> str:
    options = [""] + list(codes)
    current = value if value in options else ""
    index = options.index(current)
    labels = CODE_LABELS[field]
    return st.selectbox(
        title,
        options=options,
        index=index,
        format_func=lambda code: labels.get(code, code),
        key=key,
        disabled=disabled,
    )


def _show_locked_pass_a(st: Any, review: Mapping[str, Any], event_id: str) -> None:
    st.subheader("Pasada A — guardada y bloqueada")
    _code_select(
        st,
        field="visible_burn_scar",
        title="¿Se observa una cicatriz visible?",
        codes=VISIBLE_BURN_SCAR_CODES,
        value=review.get("pass_a_visible_burn_scar"),
        key=f"locked_pass_a_visible_{event_id}",
        disabled=True,
    )
    _code_select(
        st,
        field="scar_confidence",
        title="Confianza en la observación",
        codes=SCAR_CONFIDENCE_CODES,
        value=review.get("pass_a_scar_confidence"),
        key=f"locked_pass_a_confidence_{event_id}",
        disabled=True,
    )
    _code_select(
        st,
        field="event_association",
        title="Asociación visual con el evento",
        codes=EVENT_ASSOCIATION_CODES,
        value=review.get("pass_a_event_association"),
        key=f"locked_pass_a_association_{event_id}",
        disabled=True,
    )
    _code_select(
        st,
        field="competing_land_change",
        title="Cambio competidor visible",
        codes=COMPETING_LAND_CHANGE_CODES,
        value=review.get("pass_a_competing_land_change"),
        key=f"locked_pass_a_competing_{event_id}",
        disabled=True,
    )
    st.text_area(
        "Notas de Pasada A",
        value=review.get("pass_a_notes") or "",
        disabled=True,
        key=f"locked_pass_a_notes_{event_id}",
    )
    if review.get("exclusion_reason"):
        st.caption(f"Razón registrada: {review['exclusion_reason']}")


def _pass_a_form(
    st: Any,
    store: HumanReviewStore,
    *,
    round_id: str,
    event_id: str,
    reviewer_id: str,
    review: Mapping[str, Any] | None,
    amend: bool,
) -> None:
    prefix = "amend" if amend else "new"
    st.subheader("Pasada A — evidencia multiespectral")
    st.caption("Registre solo lo que observa en el panel multiespectral. No se muestran valores auxiliares ni sugerencias.")
    visible = _code_select(
        st,
        field="visible_burn_scar",
        title="¿Se observa una cicatriz visible?",
        codes=VISIBLE_BURN_SCAR_CODES,
        value=review.get("pass_a_visible_burn_scar") if review else None,
        key=f"{prefix}_pass_a_visible_{event_id}",
    )
    confidence = _code_select(
        st,
        field="scar_confidence",
        title="Confianza en la observación",
        codes=SCAR_CONFIDENCE_CODES,
        value=review.get("pass_a_scar_confidence") if review else None,
        key=f"{prefix}_pass_a_confidence_{event_id}",
    )
    association = _code_select(
        st,
        field="event_association",
        title="Asociación visual con el evento",
        codes=EVENT_ASSOCIATION_CODES,
        value=review.get("pass_a_event_association") if review else None,
        key=f"{prefix}_pass_a_association_{event_id}",
    )
    competing = _code_select(
        st,
        field="competing_land_change",
        title="Cambio competidor visible",
        codes=COMPETING_LAND_CHANGE_CODES,
        value=review.get("pass_a_competing_land_change") if review else None,
        key=f"{prefix}_pass_a_competing_{event_id}",
    )
    notes = st.text_area(
        "Notas de Pasada A",
        value=review.get("pass_a_notes") or "" if review else "",
        key=f"{prefix}_pass_a_notes_{event_id}",
        help="Texto libre para justificar ambigüedades; no es una clase automática.",
    )
    exclusion_reason = ""
    if visible == "unobserved":
        exclusion_reason = st.text_input(
            "Razón explícita de no observabilidad",
            value=review.get("exclusion_reason") or "" if review else "",
            key=f"{prefix}_exclusion_reason_{event_id}",
        )
    amendment_reason = ""
    if amend:
        amendment_reason = st.text_input(
            "Razón de la enmienda de Pasada A",
            key=f"{prefix}_amendment_reason_{event_id}",
        )
        st.warning("La enmienda queda registrada en el historial; el valor anterior no se elimina.")
    button_label = "Guardar enmienda de Pasada A" if amend else "Guardar Pasada A"
    if st.button(button_label, key=f"{prefix}_save_pass_a_{event_id}", type="primary"):
        try:
            saved = store.save_pass_a(
                round_id=round_id,
                event_id=event_id,
                reviewer_id=reviewer_id,
                pass_a_visible_burn_scar=visible,
                pass_a_scar_confidence=confidence,
                pass_a_event_association=association,
                pass_a_competing_land_change=competing,
                pass_a_notes=notes,
                exclusion_reason=exclusion_reason or None,
                amend=amend,
                amendment_reason=amendment_reason or None,
            )
            st.session_state[f"amend_pass_a_{event_id}"] = False
            st.success(f"Pasada A guardada (revisión {saved['pass_a_revision']}).")
            _rerun(st)
        except ReviewStoreError as exc:
            st.error(str(exc))


def _pass_b_form(
    st: Any,
    store: HumanReviewStore,
    *,
    round_id: str,
    event_id: str,
    reviewer_id: str,
    review: Mapping[str, Any],
) -> None:
    st.subheader("Pasada B — robustez temporal")
    st.caption("Ahora puede abrirse el panel temporal. La Pasada B nunca modifica los campos de la Pasada A.")
    mode = _code_select(
        st,
        field="mode_agreement",
        title="Concordancia entre selected_pair y window_median",
        codes=MODE_AGREEMENT_CODES,
        value=review.get("pass_b_mode_agreement"),
        key=f"pass_b_mode_{event_id}",
    )
    confidence = _code_select(
        st,
        field="scar_confidence",
        title="Confianza después de comparar los modos",
        codes=SCAR_CONFIDENCE_CODES,
        value=review.get("pass_b_confidence_after"),
        key=f"pass_b_confidence_{event_id}",
    )
    requires_adjudication = st.checkbox(
        "Requiere adjudicación",
        value=bool(review.get("pass_b_requires_adjudication")),
        key=f"pass_b_requires_{event_id}",
    )
    notes_label = "Notas de Pasada B / adjudicación" if requires_adjudication else "Notas de Pasada B"
    notes = st.text_area(notes_label, value=review.get("pass_b_notes") or "", key=f"pass_b_notes_{event_id}")
    if st.button("Guardar Pasada B", key=f"save_pass_b_{event_id}", type="primary"):
        try:
            saved = store.save_pass_b(
                round_id=round_id,
                event_id=event_id,
                reviewer_id=reviewer_id,
                pass_b_mode_agreement=mode,
                pass_b_confidence_after=confidence,
                pass_b_requires_adjudication=requires_adjudication,
                pass_b_notes=notes,
                adjudication_notes=notes if requires_adjudication else None,
            )
            st.success(f"Pasada B guardada como {saved['review_status']}.")
            _rerun(st)
        except ReviewStoreError as exc:
            st.error(str(exc))


def _navigation(st: Any, *, order: int, total: int) -> None:
    previous, current, following = st.columns(3)
    with previous:
        if st.button("Anterior", disabled=order <= 1, key="previous_item"):
            st.session_state["current_order"] = order - 1
            _rerun(st)
    with current:
        st.write(f"Orden {order} de {total}")
    with following:
        if st.button("Siguiente", disabled=order >= total, key="next_item"):
            st.session_state["current_order"] = order + 1
            _rerun(st)


def run_app(
    *,
    root: Path | str = ROOT,
    db_path: Path | str = DEFAULT_DB_PATH,
    export_dir: Path | str = DEFAULT_EXPORT_DIR,
    audit_dir: Path | str = DEFAULT_AUDIT_DIR,
    store: HumanReviewStore | None = None,
) -> None:
    """Run the local app; Streamlit is imported only when this function runs."""

    try:
        import streamlit as st
    except ImportError as exc:  # pragma: no cover - exercised by the CLI environment
        raise RuntimeError(
            "Falta Streamlit. Instale las dependencias de desarrollo antes de ejecutar esta herramienta."
        ) from exc

    root_path = Path(root)
    if store is None:
        store = HumanReviewStore.from_frozen_round(db_path=db_path, root=root_path)
    items = store.list_items(CALIBRATION_ROUND)
    if not items:
        st.error("No hay una ronda de revisión inicializada.")
        return

    st.set_page_config(page_title="FirePA · revisión humana local", layout="wide")
    st.title("FirePA — revisión humana local")
    st.caption("Herramienta interna de ciencia para la calibración ciega; no es un dashboard, una predicción ni una publicación.")
    st.warning(DNBR_WARNING)
    st.write(f"Ronda: `{CALIBRATION_ROUND}` · Protocolo: `draft-v1` · Quicklook: `fuegopa-dnbr-quicklook-level2-v1`")

    reviewer_id = st.text_input("Reviewer ID (obligatorio)", key="reviewer_id").strip()
    if not reviewer_id:
        st.info("Introduzca un Reviewer ID para habilitar el registro y las exportaciones.")
        return

    summary = store.round_summary(CALIBRATION_ROUND, reviewer_id)
    completed = summary.get("pass_b_complete", 0) + summary.get("needs_adjudication", 0)
    st.progress(completed / len(items), text=f"Pasadas B cerradas: {completed} de {len(items)}")
    current_order = int(st.session_state.get("current_order", 1))
    current_order = max(1, min(current_order, len(items)))
    st.session_state["current_order"] = current_order
    item = store.get_item_by_order(CALIBRATION_ROUND, current_order)
    if item is None:
        st.error("No se encontró el item del orden congelado.")
        return
    event_id = item["event_id"]
    review = store.get_review(CALIBRATION_ROUND, event_id, reviewer_id)
    status = review.get("review_status", "pending") if review else "pending"
    st.divider()
    st.write(f"**Orden:** {item['randomized_order']} · **Evento:** `{event_id}` · **Estado:** `{status}`")
    st.image(str(root_path / item["multispectral_panel_path"]), caption="Panel multiespectral — Pasada A")

    if review and review.get("pass_a_saved_at"):
        _show_locked_pass_a(st, review, event_id)
        amend_key = f"amend_pass_a_{event_id}"
        if not st.session_state.get(amend_key, False):
            if st.button("Amend Pass A", key=f"enable_{amend_key}"):
                st.session_state[amend_key] = True
                _rerun(st)
        else:
            _pass_a_form(
                st,
                store,
                round_id=CALIBRATION_ROUND,
                event_id=event_id,
                reviewer_id=reviewer_id,
                review=review,
                amend=True,
            )
    else:
        _pass_a_form(
            st,
            store,
            round_id=CALIBRATION_ROUND,
            event_id=event_id,
            reviewer_id=reviewer_id,
            review=review,
            amend=False,
        )

    review = store.get_review(CALIBRATION_ROUND, event_id, reviewer_id)
    if review and review.get("pass_a_saved_at") and review.get("review_status") != "unobserved":
        st.divider()
        st.image(str(root_path / item["temporal_panel_path"]), caption="Panel temporal — Pasada B")
        _pass_b_form(
            st,
            store,
            round_id=CALIBRATION_ROUND,
            event_id=event_id,
            reviewer_id=reviewer_id,
            review=review,
        )
    elif not review or not review.get("pass_a_saved_at"):
        st.info("La Pasada B permanece oculta hasta guardar todos los campos obligatorios de la Pasada A.")
    else:
        st.info("Este item quedó como no observable con una razón explícita; no se abre una Pasada B.")

    st.divider()
    _navigation(st, order=current_order, total=len(items))
    if st.button("Exportar snapshot y auditoría", key="export_snapshot"):
        try:
            paths = store.export_snapshot(
                round_id=CALIBRATION_ROUND,
                reviewer_id=reviewer_id,
                export_dir=export_dir,
                audit_dir=audit_dir,
            )
            st.success("Exportación determinista creada.")
            for path in paths.values():
                st.code(str(path))
        except ReviewStoreError as exc:
            st.error(str(exc))
