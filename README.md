# qnode-vigilante-externo · comprobador del hombre muerto de Q-Node

Repositorio público **mínimo y sin datos de negocio**. Su único trabajo: cada 15 minutos, desde GitHub (fuera del PC de Q-Node),
leer un buzón de latidos (un gist no listado con un fichero por robot) y comprobar que cada robot de Windows de Q-Node ha latido
dentro de su plazo (periodo + gracia) y acabó bien.

- Si un robot calla o acabó mal → el run **falla** (GitHub manda correo al dueño) y se abre o actualiza una **issue** asignada al dueño.
- Cuando todo vuelve a latir → la issue se cierra sola.
- `comprobador.py` aplica la misma ley que el censo local de Q-Node (`qnode/guardian/hombre_muerto.py`); `avisar.py` gestiona la issue.
- Prueba de fuego: `gh workflow run vigilante.yml -f simular_mudo=<slug>` da un robot por mudo a propósito.

Este repositorio lo mantiene la máquina (`python -m qnode.guardian.hombre_muerto --configurar-externo`): no editar a mano.
