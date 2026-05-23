# Regla: Sincronización Automática con GitHub

**Contexto:** Este proyecto utiliza Git y GitHub para el control de versiones. Es vital mantener el repositorio remoto actualizado con los últimos cambios locales.

**Instrucción Obligatoria:** A partir de ahora, SIEMPRE que finalices de ejecutar una tarea que implique crear, modificar o eliminar archivos en este espacio de trabajo (refactorización de código, actualización de prompts, instalación de dependencias, etc.), debes ejecutar secuencialmente los siguientes comandos de Git en la terminal integrada antes de dar por terminada tu respuesta:

1. `pip freeze > requirements.txt` (Para asegurar que las dependencias estén al día).
2. `git add .`
3. `git commit -m "update: [Breve descripción de los cambios que acabas de realizar]"`
4. `git push origin main`

**Excepciones:** Si el comando `git push` falla (por ejemplo, por un conflicto de ramas), realiza un `git pull --rebase` e inténtalo de nuevo, o informa al usuario del problema.
