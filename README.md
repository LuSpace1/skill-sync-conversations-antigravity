# Sync Conversations - Antigravity CLI

Bienvenido a la skill Sync Conversations para Antigravity CLI. Esta skill te permite respaldar, fusionar y sincronizar de forma impecable todo tu historial conversacional de IA a traves de multiples dispositivos.

## Para quien es esto?
- Desarrolladores Nomadas: Si inicias un proyecto complejo en un potente PC de escritorio y necesitas continuarlo exactamente donde lo dejaste en tu laptop desde una cafeteria.
- Precavidos con los Datos: Desarrolladores que desean mantener respaldos locales del contexto y recuerdos de su agente de IA.
- Usuarios Avanzados Multi-Dispositivo: Cualquier persona que quiera que su asistente de IA se sienta como una entidad unica y unificada.

## Que hace?
Cuando cambias a una nueva maquina, tus conversaciones de Antigravity CLI se quedan en el dispositivo original. Esta skill automatiza la segura transferencia, fusion e integracion de las bases de datos SQLite de tu IA, los logs de memoria y los indices JSON para que puedas usar /resume en una nueva maquina como si nunca te hubieras ido.

## Requisitos Previos (CRITICOS)
Para que esta skill funcione, debe comunicarse entre tus dispositivos. Debes tener SSH configurado:
1. Conexion de Red: Ambas maquinas deben estar en la misma red local, o conectadas via una red virtual como Tailscale.
2. Acceso SSH: La maquina destino debe tener acceso SSH configurado para alcanzar la maquina origen.
3. Entorno Linux / WSL: Los scripts utilizan comandos bash nativos (tar, cat).
   - Si tu maquina remota es Linux Nativo (Ubuntu, Mac, etc.) o te conectas por SSH directamente a la IP interna de WSL: Debes editar el script de Python y eliminar el prefijo 'wsl ' de los comandos SSH.
   - Si tu maquina remota es Windows y te conectas por SSH al host de Windows (CMD): El script funciona tal cual, ya que el prefijo 'wsl ' puentea el comando hacia tu subsistema Linux.

## Compatibilidad con macOS
Antigravity CLI y esta skill son totalmente compatibles con macOS, ya que dependen de comandos UNIX universales y rutas estandar (~/.gemini/antigravity-cli).
Lo que debes hacer: Si tu maquina remota es una Mac (o un Linux nativo), el prefijo 'wsl ' en los comandos SSH fallara.
La Solucion Agentica: No necesitas programar. Una vez que descargues esta skill, simplemente pidele a tu agente de IA:
"Estoy en macOS. Por favor edita el script de python en la skill sync-conversations-antigravity para eliminar todos los prefijos 'wsl ' de los comandos SSH."
Tu agente adaptara automaticamente el script para tu entorno.

## Compatibilidad con Windows Nativo (Sin WSL)
Si estas ejecutando Antigravity CLI en Windows puro (CMD o PowerShell) sin usar WSL, los comandos subyacentes (tar, cat) y las rutas pueden comportarse de manera diferente.
La Solucion Agentica: Simplemente pidele a tu agente de IA que adapte el script:
"Estoy en Windows nativo sin WSL. Por favor edita el script de python en la skill sync-conversations-antigravity para usar comandos de PowerShell en lugar de bash, y elimina los prefijos 'wsl ' de los comandos SSH."

## Sincronizacion Bidireccional (No Destructiva)
Esta skill realiza una Sincronizacion Bidireccional Verdadera. Debido a que Antigravity guarda las conversaciones en bases de datos separadas, el script trae los datos remotos de forma segura, los fusiona con tus datos locales sin borrar absolutamente nada, y luego empuja el historial maestro combinado de regreso a la maquina remota. Ambos dispositivos se convierten en un espejo perfecto al instante.

## Como Funciona (Bajo el Capo)
Antigravity CLI tiene una arquitectura de cliente descentralizada. Para lograr una transicion perfecta, esta skill ejecuta el siguiente flujo:
1. Fusion de Indices: Descarga de forma segura el history.jsonl de la maquina remota y ejecuta un algoritmo en Python para fusionarlo con tu historial local.
2. Tuberia Tar Atomica: Transmite tu carpeta brain/ y conversations/ sobre SSH usando una tuberia comprimida de tarball.
3. Sincronizacion de Entorno: Copia el installation_id. Al sincronizarlo, evitamos que el backend arroje el error de proyecto invalido, permitiendo al servidor mantener la continuidad de la sesion en la nueva maquina.

## Como Usarlo
1. Asegurate de que tu conexion SSH este funcionando.
2. Instala esta skill en tu directorio ~/.agents/skills/.
3. Abre Antigravity CLI y dile a tu agente:
   "Ejecuta la skill sync-conversations-antigravity para traer mis sesiones desde mi PC (usuario@direccion_ip)."
4. Navega a la misma carpeta del proyecto y escribe /resume.

## Auditorías de Seguridad (Falsos Positivos)
Si analizas esta skill con herramientas de seguridad (como Gen Agent Trust Hub o Snyk), es probable que detecten alertas como `DATA_EXFILTRATION` y `CREDENTIALS_UNSAFE`. Estos son **falsos positivos** y corresponden al comportamiento esperado y necesario: la herramienta transfiere explícitamente bases de datos locales y sincroniza el `installation_id` a través de tu red privada para lograr la continuidad de sesiones entre tus propios dispositivos.
