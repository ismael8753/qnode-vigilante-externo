# ruff: noqa: E501 · plantilla PUBLICADA en el repo comprobador (sin datos de negocio) · solo librería estándar
"""COMPROBADOR EXTERNO del hombre muerto de Q-Node (corre en GitHub Actions, fuera del PC · guardián V1 ventana 3 · 10-oct-2026).

Lee el buzón de latidos (gist no listado · id en el secreto QNODE_GIST_ID): `roster.json` (periodo y gracia EN MINUTOS por robot) y un
`latido_<slug>.json` por robot ({ts, rc}). Aplica LA MISMA LEY que el censo local de qnode/guardian/hombre_muerto.py:
FALLO si el último latido trae rc ≠ 0 · MUDO si es más viejo que periodo+gracia · VIVO si está dentro · SIN_LATIDO si nunca latió.
Veredicto: ROJO si hay mudos o fallos · si NADIE ha latido: AVISO, y ROJO cuando el roster lleva >48 h subido · SIN_DATO si el buzón
no se puede leer (tras 3 intentos) · OK en el resto. Sin dato NUNCA es verde.
Salida: informe por pantalla · estado.json (lo lee avisar.py) · latidos/ultimo_dia.txt (un commit al día mantiene el cron encendido) ·
GITHUB_OUTPUT (veredicto · resumen) · GITHUB_STEP_SUMMARY. rc: 0 OK/AVISO · 2 ROJO · 3 SIN_DATO (el workflow falla con 2 y 3).
Prueba de fuego: QNODE_SIMULAR_MUDO=<slug> da ese robot por MUDO a propósito (marcado SIMULADO) sin tocar robots reales.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com/gists/{id}"
RAW = "https://gist.githubusercontent.com/{owner}/{id}/raw/{fichero}"
ARCHIVO_ROSTER = "roster.json"
PREFIJO_LATIDO = "latido_"
TOPE_SIN_LATIDO_H = 48.0
INTENTOS = 3


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse(ts):
    try:
        t = dt.datetime.fromisoformat(str(ts))
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def _get(url: str, token: str | None = None, timeout: float = 20.0) -> tuple[int | None, str]:
    cab = {"User-Agent": "QNodeVigilanteExterno/2.0", "Accept": "application/vnd.github+json"}
    if token:
        cab["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=cab), timeout=timeout) as r:  # noqa: S310
            return int(r.status), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return int(e.code), str(e)[:200]
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:160]}"


def leer_buzon(gist_id: str, owner: str, token: str | None, get=_get, dormir=time.sleep) -> tuple[dict[str, str] | None, str]:
    """{nombre_fichero: contenido} del gist · API con token (1.000 peticiones/h) → API anónima → ficheros crudos por URL. None = ilegible."""
    detalle = ""
    for intento in range(INTENTOS):
        for tok in ((token, None) if token else (None,)):
            code, cuerpo = get(API.format(id=gist_id), tok)
            if code == 200:
                try:
                    d = json.loads(cuerpo)
                    return {n: (f.get("content") or "") for n, f in (d.get("files") or {}).items()}, "api"
                except json.JSONDecodeError:
                    detalle = "api: json ilegible"
            else:
                detalle = f"api http {code}: {cuerpo[:80]}"
        code, cuerpo = get(RAW.format(owner=owner, id=gist_id, fichero=ARCHIVO_ROSTER) + f"?t={int(time.time())}") if owner else (None, "sin dueño del gist: no hay modo crudo")
        if code == 200:
            try:
                roster = json.loads(cuerpo)
                out = {ARCHIVO_ROSTER: cuerpo}
                for r in roster.get("robots") or []:
                    n = f"{PREFIJO_LATIDO}{r.get('slug')}.json"
                    c2, b2 = get(RAW.format(owner=owner, id=gist_id, fichero=n) + f"?t={int(time.time())}")
                    if c2 == 200:
                        out[n] = b2
                return out, "raw"
            except json.JSONDecodeError:
                detalle = "raw: roster ilegible"
        else:
            detalle = detalle or f"raw http {code}"
        if intento < INTENTOS - 1:
            dormir(5 * (intento + 1))
    return None, detalle


def _num(x, defecto: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return defecto


def estado_robot(r: dict, u: dict | None, now: dt.datetime) -> tuple[str, float | None]:
    """LA LEY por robot (idéntica a qnode/guardian/hombre_muerto.py::estado_robot) · a prueba de basura: un latido que no es un
    objeto = SIN_LATIDO · un rc ilegible = FALLO (nunca verde por basura) · un plazo ilegible = tope 0 (todo latido viejo es MUDO)."""
    if not u or not isinstance(u, dict):
        return "SIN_LATIDO", None
    t = _parse(u.get("ts"))
    edad_min = round((now - t).total_seconds() / 60.0, 1) if t else None
    tope = _num(r.get("periodo_min") or 0) + _num(r.get("gracia_min") or 0)
    try:
        rc = int(u.get("rc") or 0)
    except (TypeError, ValueError):
        rc = -1
    if rc != 0:
        return "FALLO", edad_min
    if edad_min is None or edad_min > tope:
        return "MUDO", edad_min
    return "VIVO", edad_min


def censar(ficheros: dict[str, str] | None, now: dt.datetime, simular_mudo: str = "", detalle_lectura: str = "") -> dict:
    """Veredicto honesto desde fuera: ROJO (mudos/fallos) · AVISO (nadie late aún) · ROJO si nadie late >48 h tras subir el roster ·
    SIN_DATO (buzón ilegible o sin roster) · OK."""
    base = {"generado_utc": now.isoformat(), "simulado": simular_mudo or None}
    if ficheros is None:
        return {**base, "veredicto": "SIN_DATO", "motivo": f"buzón de latidos ilegible: {detalle_lectura or 'sin detalle'}", "robots": []}
    try:
        roster = json.loads(ficheros.get(ARCHIVO_ROSTER) or "{}")
    except json.JSONDecodeError:
        roster = {}
    robots_def = [r for r in ((roster.get("robots") if isinstance(roster, dict) else None) or []) if isinstance(r, dict)]
    if not robots_def:
        return {**base, "veredicto": "SIN_DATO", "motivo": "el buzón no tiene roster.json (corre --configurar-externo en el PC)", "robots": []}
    robots, mudos, fallos, sin_latido = [], [], [], []
    for r in robots_def:
        slug = str(r.get("slug"))
        try:
            u = json.loads(ficheros.get(f"{PREFIJO_LATIDO}{slug}.json") or "null")
        except json.JSONDecodeError:
            u = None
        estado, edad_min = estado_robot(r, u if isinstance(u, dict) else None, now)
        simulado = bool(simular_mudo) and slug == simular_mudo
        if simulado:
            estado = "MUDO"
        robots.append({"slug": slug, "tarea": r.get("tarea"), "norte": bool(r.get("norte")), "estado": estado + (" (SIMULADO)" if simulado else ""),
                       "edad_min": edad_min, "tope_min": _num(r.get("periodo_min") or 0) + _num(r.get("gracia_min") or 0), "rc": (u or {}).get("rc") if isinstance(u, dict) else None})
        {"MUDO": mudos, "FALLO": fallos, "SIN_LATIDO": sin_latido}.get(estado, []).append(slug)
    n = len(robots_def)
    if mudos or fallos:
        veredicto = "ROJO"
        motivo = (f"mudos {len(mudos)} de {n}: {', '.join(mudos)}" if mudos else "") + (" · " if mudos and fallos else "") + (f"con fallo {len(fallos)}: {', '.join(fallos)}" if fallos else "")
    elif len(sin_latido) == n:
        subido = _parse(roster.get("subido_utc"))
        horas = (now - subido).total_seconds() / 3600.0 if subido else None
        if horas is not None and horas > TOPE_SIN_LATIDO_H:
            veredicto, motivo = "ROJO", f"nadie late desde que se subió el roster hace {horas:.0f} h: el PC o las líneas de los robots no están"
        else:
            veredicto, motivo = "AVISO", f"0 de {n} robots han latido aún (roster subido hace {horas:.0f} h)" if horas is not None else f"0 de {n} robots han latido aún"
    else:
        veredicto, motivo = "OK", f"vivos {n - len(sin_latido)} de {n}" + (f" · sin latido aún {len(sin_latido)}: {', '.join(sin_latido)}" if sin_latido else "")
    return {**base, "veredicto": veredicto, "motivo": motivo, "robots": robots, "mudos": mudos, "fallos": fallos, "sin_latido": sin_latido, "roster_n": n}


def informe(st: dict) -> str:
    lineas = [f"🫀 Hombre muerto · vista desde fuera: {st['veredicto']} · {st['motivo']} · {st['generado_utc'][:19]}Z"]
    for r in st.get("robots") or []:
        if not r["estado"].startswith("VIVO"):
            lineas.append(f"  · {r['estado']:<18} {r['slug']} ({r.get('tarea')}) · edad {r.get('edad_min')} min · tope {r.get('tope_min'):.0f} min · rc {r.get('rc')}")
    if st.get("simulado"):
        lineas.append(f"  (prueba de fuego: «{st['simulado']}» mudo A PROPÓSITO · no es una avería real)")
    return "\n".join(lineas)


def _escribir_salidas(st: dict, texto: str, now: dt.datetime) -> None:
    with open("estado.json", "w", encoding="utf-8") as fh:
        json.dump({**st, "informe": texto}, fh, ensure_ascii=False, indent=1)
    os.makedirs("latidos", exist_ok=True)
    with open("latidos/ultimo_dia.txt", "w", encoding="utf-8") as fh:
        fh.write(now.strftime("%Y-%m-%d") + "\n")
    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a", encoding="utf-8") as fh:
            resumen = " ".join(str(st.get("motivo", "")).split())[:200]  # una sola línea, sin saltos
            marca = f"QNODE_EOF_{int(now.timestamp())}"
            fh.write(f"veredicto={st['veredicto']}\nresumen<<{marca}\n{resumen}\n{marca}\n")
    resumen = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumen:
        with open(resumen, "a", encoding="utf-8") as fh:
            fh.write("```\n" + texto + "\n```\n")


def main() -> int:
    gist_id = (os.environ.get("QNODE_GIST_ID") or "").strip()
    owner = (os.environ.get("QNODE_GIST_OWNER") or "").strip()
    token = (os.environ.get("GITHUB_TOKEN") or "").strip() or None
    now = _now()
    if not gist_id:
        st = censar(None, now, detalle_lectura="falta el secreto QNODE_GIST_ID en el repo")
    else:
        ficheros, det = leer_buzon(gist_id, owner, token)
        st = censar(ficheros, now, (os.environ.get("QNODE_SIMULAR_MUDO") or "").strip(), det)
    texto = informe(st)
    print(texto)
    _escribir_salidas(st, texto, now)
    return {"OK": 0, "AVISO": 0, "ROJO": 2}.get(st["veredicto"], 3)


if __name__ == "__main__":
    sys.exit(main())
