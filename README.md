# FINANCIERA - Tradex MVP

Sistema web en Flask para gestionar una micro-financiera con capital compartido.

## Funciones incluidas
- Login por PIN con roles:
  - **Administrador** (`666666`)
  - **Operador/Cobrador** (`9999`)
- Dashboard con KPIs:
  - Total prestado
  - Recaudado hoy
  - Ganancia proyectada
  - Capital disponible
- Gestión de préstamos:
  - Interés simple y compuesto
  - Frecuencia diaria/semanal/mensual
  - Cálculo automático de fecha de vencimiento
- Registro de cobros con **fecha actualizable** (editable por formulario)
- Control de estado del préstamo: activo / pagado / en mora
- Gestión de capital por socio
- Exportación de cartera y cobros a CSV

## Stack
- Python + Flask
- HTML + Jinja + Bootstrap
- Persistencia en JSON (`data/*.json`)

## Ejecución local
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Abrir: `http://localhost:5000`
