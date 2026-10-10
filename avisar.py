# ruff: noqa: E501 · plantilla PUBLICADA en el repo comprobador (sin datos de negocio) · solo librería estándar + gh del runner
"""AVISO del comprobador externo: una issue asignada al dueño (segundo canal · el primero es el correo del run fallido).

Lee estado.json (lo escribe comprobador.py) y, con el gh del runner (GITHUB_TOKEN · permisos issues: write):
  ROJO / SIN_DATO → si ya hay una issue abierta con la etiqueta, la COMENTA con el informe de hoy; si no, la ABRE asignada al dueño.
  OK / AVISO      → CIERRA las abiertas con un comentario (todos los robots vuelven a latir).
Nunca revienta (exit 0 siempre): el veredicto del run lo decide el último paso del workflow. decidir() es pura y se prueba en Q-Node.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ETIQUETA = "hombre-muerto"


def decidir(veredicto: str, n_abiertas: int) -> str:
    """'abrir' | 'comentar' | 'cerrar' | 'nada' · la ley: rojo o sin dato avisan; verde o aviso cierran lo abierto."""
    if veredicto in ("ROJO", "SIN_DATO"):
        return "comentar" if n_abiertas else "abrir"
    return "cerrar" if n_abiertas else "nada"


def _gh(args: list[str], entrada: str | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(["gh", *args], input=entrada, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False)
        return r.returncode, (r.stdout if r.returncode == 0 else (r.stderr or r.stdout)).strip()
    except Exception as e:  # noqa: BLE001
        return 1, f"{type(e).__name__}: {str(e)[:120]}"


def main() -> int:
    repo = os.environ.get("REPO") or os.environ.get("GITHUB_REPOSITORY") or ""
    dueno = os.environ.get("DUENO") or os.environ.get("GITHUB_REPOSITORY_OWNER") or ""
    run_url = os.environ.get("RUN_URL") or ""
    try:
        with open("estado.json", encoding="utf-8") as fh:
            st = json.load(fh)
    except (OSError, json.JSONDecodeError):
        st = {"veredicto": os.environ.get("VEREDICTO") or "SIN_DATO", "motivo": os.environ.get("RESUMEN") or "sin estado.json", "informe": ""}
    veredicto = str(st.get("veredicto") or "SIN_DATO")
    code, out = _gh(["issue", "list", "-R", repo, "--label", ETIQUETA, "--state", "open", "--json", "number"])
    try:
        abiertas = [int(x["number"]) for x in json.loads(out or "[]")] if code == 0 else []
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        abiertas = []
    accion = decidir(veredicto, len(abiertas))
    cuerpo = f"**{veredicto}** · {st.get('motivo', '')}\n\n```\n{st.get('informe', '')}\n```\n\nRun: {run_url}\n\n_Lo escribe el comprobador externo del hombre muerto de Q-Node (github-actions[bot])._"
    print(f"veredicto {veredicto} · issues abiertas {len(abiertas)} · acción: {accion}")
    if accion == "abrir":
        _gh(["label", "create", ETIQUETA, "-R", repo, "--color", "B60205", "--force", "--description", "aviso del hombre muerto: un robot de Q-Node calla o acabó mal"])
        titulo = f"🫀 Hombre muerto: {veredicto} · {str(st.get('motivo', ''))[:80]}"
        code, out = _gh(["issue", "create", "-R", repo, "--title", titulo, "--body", cuerpo, "--label", ETIQUETA, "--assignee", dueno])
        print(("issue abierta: " + out) if code == 0 else ("⛔ no se pudo abrir la issue: " + out))
    elif accion == "comentar":
        code, out = _gh(["issue", "comment", str(abiertas[0]), "-R", repo, "--body", cuerpo])
        print((f"issue #{abiertas[0]} comentada") if code == 0 else ("⛔ no se pudo comentar: " + out))
    elif accion == "cerrar":
        for n in abiertas:
            _gh(["issue", "comment", str(n), "-R", repo, "--body", f"✅ **{veredicto}** · {st.get('motivo', '')} · todos los robots vuelven a latir.\n\nRun: {run_url}"])
            code, out = _gh(["issue", "close", str(n), "-R", repo])
            print((f"issue #{n} cerrada") if code == 0 else (f"⛔ no se pudo cerrar #{n}: " + out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
