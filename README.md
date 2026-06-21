# Sincronización de Conversaciones - Antigravity CLI

Esta herramienta te permite sincronizar, respaldar y fusionar de manera automática tus conversaciones del CLI de Antigravity entre diferentes computadoras de desarrollo utilizando una conexión SSH. 

Está diseñada especialmente para desarrolladores que trabajan en varios equipos (como una computadora de escritorio y una portátil) y desean continuar sus sesiones de trabajo exactamente donde las dejaron.

## ¿Qué hace esta herramienta?
* **Sincronización completa (Espejo):** Combina los historiales de conversación de ambas computadoras en orden cronológico, elimina registros duplicados y actualiza los archivos de memoria (`brain/`) y las bases de datos de sesión (`conversations/`) en ambos extremos.
* **Sincronización selectiva:** Permite buscar una conversación específica usando una parte de su título y transferir únicamente sus archivos asociados, sin alterar el resto de las conversaciones locales.
* **Protección de sesión activa:** Si la sincronización es ejecutada por el propio agente de IA, se excluye de forma automática la base de datos de la conversación activa para evitar que los archivos se corrompan mientras se escribe en ellos.
* **Portabilidad total en Python:** Toda la compresión y transferencia se realiza usando el módulo estándar `tarfile` de Python. No requiere comandos externos del sistema operativo (como `tar` o `find`), lo que garantiza que funcione nativamente en Windows (CMD/PowerShell), Linux, macOS y WSL sin configuraciones adicionales.

## Requisitos previos
Para que la sincronización funcione correctamente, debes cumplir con lo siguiente:
1. **Conexión de red:** Ambas computadoras deben estar conectadas a la misma red local o mediante una red privada virtual (como Tailscale).
2. **Acceso SSH configurado:** La computadora que inicia el proceso debe tener acceso SSH configurado hacia el equipo remoto. Se recomienda usar autenticación con llave pública (sin contraseña) para facilitar el flujo automático.
3. **Python 3 instalado:** Al no depender de herramientas de sistema externas, es necesario que ambas computadoras tengan instalado Python 3.

## Cómo funciona el script
1. **Validación previa:** Al iniciar, realiza un chequeo rápido de conexión SSH con un tiempo de espera de 10 segundos. Si no hay conexión, aborta inmediatamente con un mensaje claro en lugar de fallar a mitad del proceso.
2. **Fusión de historial:** Descarga el archivo de índice `history.jsonl` del host remoto, lo mezcla en memoria con el local descartando duplicados por marca de tiempo y guarda el archivo combinado.
3. **Transferencia binaria:** Empaqueta y descomprime los archivos de conversación (`brain/` y `conversations/`) directamente a través de la red leyendo los flujos binarios del canal SSH, sin crear archivos intermedios grandes.
4. **Coherencia de identidad:** Durante la sincronización completa, el entorno local copia el `installation_id` del remoto para que el backend de Antigravity valide correctamente el espacio de trabajo y reconozca la sesión de inmediato.

## Instrucciones de uso

El script soporta dos modos de ejecución dependiendo de cómo prefieras utilizarlo:

### 1. Modo Automático (Sin preguntas)
Para ejecutar la sincronización de forma automática sin preguntas, introduce los parámetros directamente en la consola:

* **Sincronización completa automática (todas las conversaciones):**
  ```
  python scripts/sync_antigravity.py <host_remoto>
  ```
* **Sincronización selectiva automática (una conversación específica):**
  ```
  python scripts/sync_antigravity.py <host_remoto> --name "Nombre de la conversación"
  ```
*(Reemplaza `<host_remoto>` por el nombre o alias que le diste al equipo remoto en tu configuración SSH, por ejemplo `pc-escritorio` o `portatil`).*

### 2. Modo Interactivo (Guiado por consola)
Si ejecutas el script de forma manual desde un IDE (como la terminal de VS Code) o directamente desde la terminal de tu sistema sin pasar argumentos de comandos, el script iniciará un asistente interactivo que te guiará con las siguientes preguntas:

1. **Host remoto de SSH:** Si no proporcionas el argumento del host, te pedirá que lo ingreses:  
   *`Introduce el host remoto o alias de SSH (ej. pc, portatil, usuario@host):`*
2. **Tipo de sincronización:** Te preguntará qué tipo de proceso deseas realizar:  
   *`¿Qué tipo de sincronización deseas realizar?`*  
   *` 1. Sincronización completa (Espejo de todas las conversaciones)`*  
   *` 2. Sincronización selectiva (Una conversación específica)`*
3. **Búsqueda (solo selectiva):** Si eliges la opción selectiva, te solicitará ingresar el título de la conversación:  
   *`Introduce el título o palabras clave de la conversación:`*
4. **Resolución de coincidencias:** Si hay más de una conversación que coincide con tu búsqueda, el script te mostrará una lista numerada para que elijas la correcta antes de continuar:  
   *`Selecciona una opción (1-N) o escribe 'c' para cancelar:`*

---

## Análisis de Seguridad (Falsos Positivos)
Si analizas este script con herramientas de seguridad estática (como Gen Agent Trust Hub o Snyk), podrían generarse advertencias de transferencia insegura de datos o de información confidencial. Estas alertas son falsos positivos esperados: la herramienta realiza una transferencia legítima de tus bases de datos de sesión y unifica el identificador de instalación a través de tu túnel SSH privado para garantizar la continuidad del servicio en tus propios equipos.

---

## Contribuciones

Las contribuciones, issues y feature requests son bienvenidos. Siéntete libre de revisar los issues abiertos o enviar un PR.
