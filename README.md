# Sync Conversations - Antigravity CLI

Herramienta de sincronización de conversaciones para Antigravity CLI que permite transferir, fusionar y respaldar el historial conversacional entre múltiples dispositivos.

## Casos de uso
- **Desarrollo en múltiples equipos:** Continuar una sesión de trabajo activa en un segundo dispositivo (ej. pasar del PC de escritorio a una laptop o notebook).
- **Respaldos locales:** Mantener copias de seguridad del contexto del agente en local sin depender de la nube.
- **Continuidad de sesión:** Sincronizar el identificador de instalación y las bases de datos para mantener el contexto del agente unificado.

## Características
- **Sincronización total:** Fusiona de manera bidireccional el historial completo entre dos dispositivos de forma aditiva.
- **Sincronización selectiva:** Permite transferir una conversación específica buscando por su título en el historial, sin alterar los demás archivos locales.
- **Protección de base de datos activa:** Si se ejecuta el script durante una sesión activa del agente, este puede pasar el ID de la conversación para excluir sus archivos de la sobrescritura y evitar la corrupción de SQLite.
- **Compatibilidad multiplataforma:** Diseñado para funcionar en Linux nativo, macOS, Windows nativo y Windows WSL. El script detecta de forma automática si el destino remoto requiere el prefijo `wsl` para los comandos por SSH.

## Requisitos previos
- **Conectividad:** Ambos dispositivos deben estar en la misma red local o conectados mediante una red virtual (como Tailscale).
- **Acceso SSH:** Conexión SSH configurada y funcional hacia el equipo de destino. Se recomienda el uso de autenticación por llave pública.
- **Utilidades del sistema:** Requiere la disponibilidad del comando `tar` en ambos sistemas (incluido por defecto en Linux, macOS y Windows 10/11).

## Arquitectura y funcionamiento
El script realiza los siguientes pasos lógicos:
1. **Fusión de historial:** Descarga el archivo `history.jsonl` remoto y lo fusiona en memoria con el local, eliminando duplicados por marca de tiempo (`timestamp`).
2. **Transferencia de archivos:** Comprime y envía los directorios `brain/` y `conversations/` a través de un canal seguro SSH utilizando `tar`.
3. **Sincronización de identidad:** Copia el archivo `installation_id` para asegurar la coherencia del workspace en el backend de Antigravity.

## Instrucciones de uso

### Uso desde el agente (Lenguaje natural)
Una vez instalada la skill, el agente de Antigravity puede interpretar solicitudes como:
- "Sincroniza el historial de conversaciones desde mi PC."
- "Trae la conversación sobre 'refactorización de código' desde mi portátil."

### Uso manual (Terminal)
El script se ejecuta de la siguiente manera en tu PC local:

- **Sincronización total (todas las conversaciones):**
  ```bash
  python scripts/sync_antigravity.py <host_remoto>
  ```
- **Sincronización selectiva (una conversación por su título):**
  ```bash
  python scripts/sync_antigravity.py <host_remoto> --name "Título de la conversación"
  ```
*(Reemplazar `<host_remoto>` por el alias del dispositivo remoto en SSH, por ejemplo `pc` o `notebook`).*

## Auditorías de seguridad (Falsos positivos)
Los análisis de seguridad estática (como Gen Agent Trust Hub o Snyk) pueden alertar sobre `DATA_EXFILTRATION` o `CREDENTIALS_UNSAFE`. Estas advertencias son falsos positivos, ya que corresponden al comportamiento legítimo de la herramienta al transferir las bases de datos y el identificador de instalación a través de tu conexión SSH privada.
