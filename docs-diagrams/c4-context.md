# C4 — Level 1: System Context

```mermaid
C4Context
  title Upasser — Contexto del Sistema

  Person(platform_admin, "Platform Admin", "Equipo interno de Upasser. Gestiona empresas clientes, roles de plataforma y permisos globales.")
  Person(company_admin, "Company Admin / Manager", "Administrador de una empresa cliente. Gestiona sucursales, usuarios, credenciales y clientes.")
  Person(cajero, "Cajero / Operador", "Empleado de la empresa. Opera la caja rápida (POS) y procesa recargas de saldo.")

  System_Ext(esp32, "Dispositivo IoT (ESP32)", "Hardware de torniquete/puerta. Detecta chips NFC y llama al sistema para autorizar o denegar el paso.")

  System(upasser, "Upasser", "Sistema de control de acceso prepago. Gestiona clientes, billeteras, credenciales NFC/QR y eventos de acceso físico.")

  Rel(platform_admin, upasser, "Administra plataforma", "HTTPS / Browser")
  Rel(company_admin, upasser, "Administra empresa y operaciones", "HTTPS / Browser")
  Rel(cajero, upasser, "Opera caja y recargas", "HTTPS / Browser")
  Rel(esp32, upasser, "Envía UID al tapear chip — solicita GO/NO-GO", "HTTP POST /operations/scan")

  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```
