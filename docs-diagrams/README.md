# docs-diagrams — Upasser

Documentación técnica visual del sistema. Todos los diagramas están escritos en Mermaid y se renderizan directamente en GitHub, GitLab y la mayoría de editores modernos.

---

## Contenido

| Archivo | Tipo | Descripción |
|---------|------|-------------|
| [`data_dictionary.md`](./data_dictionary.md) | Referencia | Diccionario completo de tablas, columnas, tipos y relaciones de la base de datos |
| [`erd.md`](./erd.md) | `erDiagram` | Diagrama entidad-relación con todas las tablas y sus FK |
| [`c4-context.md`](./c4-context.md) | `C4Context` | L1 — Upasser como caja negra: actores externos y sistema |
| [`c4-container.md`](./c4-container.md) | `C4Container` | L2 — Contenedores: Web App, Backend API, PostgreSQL y dispositivos IoT |
| [`c4-component.md`](./c4-component.md) | `C4Component` | L3 — Componentes del Backend API: routers, RBAC, seguridad y sesión de BD |

---

## Cómo leer los diagramas C4

El modelo C4 describe la arquitectura en cuatro niveles de zoom. Este proyecto documenta los tres primeros:

```
L1 Context  →  ¿Quién usa el sistema y cómo encaja en su entorno?
L2 Container →  ¿Qué procesos/apps componen el sistema?
L3 Component →  ¿Qué módulos hay dentro de cada contenedor?
```

Para navegar: empieza por `c4-context.md` y profundiza hacia `c4-component.md` según lo que necesites entender.

---

## Renderizado local

Cualquier editor con soporte Mermaid muestra los diagramas inline:

- **VS Code** — extensión [Mermaid Preview](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid)
- **JetBrains** — plugin [Mermaid](https://plugins.jetbrains.com/plugin/20146-mermaid)
- **GitHub / GitLab** — se renderizan automáticamente en la vista de archivos `.md`
