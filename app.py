from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import Flask, flash, redirect, render_template, request, send_file, session, url_for

APP_ROOT = Path(__file__).parent
DATA_DIR = APP_ROOT / "data"
LOANS_FILE = DATA_DIR / "loans.json"
PAYMENTS_FILE = DATA_DIR / "payments.json"
INVESTORS_FILE = DATA_DIR / "investors.json"

ROLE_PINS = {
    "666666": "admin",
    "9999": "operator",
}

FREQUENCY_DAYS = {
    "diario": 1,
    "semanal": 7,
    "mensual": 30,
}

app = Flask(__name__)
app.config["SECRET_KEY"] = "tradex-dev-secret"


def ensure_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    defaults = {
        LOANS_FILE: [],
        PAYMENTS_FILE: [],
        INVESTORS_FILE: [
            {"name": "Hiriu Roding", "capital": 0},
            {"name": "Regin Lucio", "capital": 0},
            {"name": "Piero Ruiz", "capital": 0},
            {"name": "Anderson Inuma", "capital": 0},
        ],
    }
    for file_path, default in defaults.items():
        if not file_path.exists():
            file_path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def require_role(*roles: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if session.get("role") not in roles:
                flash("No autorizado para este módulo", "danger")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def logged_in_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("role"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrapper


def compute_interest(principal: float, rate_pct: float, loan_type: str, periods: int) -> float:
    rate = rate_pct / 100
    if loan_type == "simple":
        return principal * rate * periods
    return principal * ((1 + rate) ** periods - 1)


def recompute_loan_state(loan: dict[str, Any], payments: list[dict[str, Any]]) -> dict[str, Any]:
    loan_payments = [p for p in payments if p["loan_id"] == loan["id"]]
    paid_total = sum(float(p["amount"]) for p in loan_payments)
    balance = max(0, float(loan["total_due"]) - paid_total)

    today = date.today()
    due_date = datetime.strptime(loan["due_date"], "%Y-%m-%d").date()
    status = "pagado" if balance <= 0 else ("en_mora" if today > due_date else "activo")

    updated = dict(loan)
    updated.update({"paid_total": round(paid_total, 2), "balance": round(balance, 2), "status": status})
    return updated


def get_all_data() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    loans = load_json(LOANS_FILE)
    payments = load_json(PAYMENTS_FILE)
    investors = load_json(INVESTORS_FILE)
    loans = [recompute_loan_state(loan, payments) for loan in loans]
    save_json(LOANS_FILE, loans)
    return loans, payments, investors


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pin = request.form.get("pin", "")
        role = ROLE_PINS.get(pin)
        if role:
            session["role"] = role
            flash(f"Bienvenido, rol: {role}", "success")
            return redirect(url_for("dashboard"))
        flash("PIN inválido", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@logged_in_required
def dashboard():
    loans, payments, investors = get_all_data()

    total_lent = sum(float(l["principal"]) for l in loans)
    total_collected = sum(float(p["amount"]) for p in payments)
    today_str = date.today().isoformat()
    collected_today = sum(float(p["amount"]) for p in payments if p["payment_date"] == today_str)
    projected_profit = sum(float(l["total_due"]) - float(l["principal"]) for l in loans)
    available_capital = sum(float(i["capital"]) for i in investors) - sum(float(l["balance"]) for l in loans if l["status"] != "pagado")

    status_count = {
        "activo": sum(1 for l in loans if l["status"] == "activo"),
        "pagado": sum(1 for l in loans if l["status"] == "pagado"),
        "en_mora": sum(1 for l in loans if l["status"] == "en_mora"),
    }

    return render_template(
        "dashboard.html",
        loans=loans,
        investors=investors,
        kpis={
            "total_lent": round(total_lent, 2),
            "total_collected": round(total_collected, 2),
            "collected_today": round(collected_today, 2),
            "projected_profit": round(projected_profit, 2),
            "available_capital": round(available_capital, 2),
        },
        status_count=status_count,
    )


@app.route("/loans/new", methods=["GET", "POST"])
@logged_in_required
@require_role("admin")
def create_loan():
    loans, _, _ = get_all_data()

    if request.method == "POST":
        customer = request.form["customer"].strip()
        principal = float(request.form["principal"])
        rate = float(request.form["rate"])
        loan_type = request.form["loan_type"]
        frequency = request.form["frequency"]
        periods = int(request.form["periods"])
        start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()

        interest = compute_interest(principal, rate, loan_type, periods)
        total_due = principal + interest
        due_date = start_date + timedelta(days=FREQUENCY_DAYS[frequency] * periods)

        loan = {
            "id": str(uuid4())[:8],
            "customer": customer,
            "principal": round(principal, 2),
            "rate": rate,
            "loan_type": loan_type,
            "frequency": frequency,
            "periods": periods,
            "start_date": start_date.isoformat(),
            "due_date": due_date.isoformat(),
            "interest": round(interest, 2),
            "total_due": round(total_due, 2),
            "paid_total": 0,
            "balance": round(total_due, 2),
            "status": "activo",
        }
        loans.append(loan)
        save_json(LOANS_FILE, loans)
        flash("Préstamo creado correctamente", "success")
        return redirect(url_for("dashboard"))

    return render_template("loan_form.html")


@app.route("/payments/new", methods=["GET", "POST"])
@logged_in_required
@require_role("admin", "operator")
def register_payment():
    loans, payments, _ = get_all_data()
    active_loans = [l for l in loans if l["status"] != "pagado"]

    if request.method == "POST":
        loan_id = request.form["loan_id"]
        amount = float(request.form["amount"])
        payment_date = request.form["payment_date"]
        notes = request.form.get("notes", "").strip()

        loan = next((l for l in loans if l["id"] == loan_id), None)
        if not loan:
            flash("Préstamo no encontrado", "danger")
            return redirect(url_for("register_payment"))

        if amount <= 0 or amount > float(loan["balance"]):
            flash("Monto inválido para el saldo pendiente", "danger")
            return redirect(url_for("register_payment"))

        payments.append(
            {
                "id": str(uuid4())[:10],
                "loan_id": loan_id,
                "customer": loan["customer"],
                "amount": round(amount, 2),
                "payment_date": payment_date,
                "registered_by": session.get("role"),
                "notes": notes,
            }
        )
        save_json(PAYMENTS_FILE, payments)
        get_all_data()
        flash("Cobro registrado correctamente", "success")
        return redirect(url_for("dashboard"))

    return render_template("payment_form.html", loans=active_loans, today=date.today().isoformat())


@app.route("/investors", methods=["GET", "POST"])
@logged_in_required
@require_role("admin")
def manage_investors():
    _, _, investors = get_all_data()
    if request.method == "POST":
        name = request.form["name"]
        capital = float(request.form["capital"])
        updated = False
        for inv in investors:
            if inv["name"] == name:
                inv["capital"] = round(capital, 2)
                updated = True
                break
        if not updated:
            investors.append({"name": name, "capital": round(capital, 2)})
        save_json(INVESTORS_FILE, investors)
        flash("Capital de socio actualizado", "success")
        return redirect(url_for("manage_investors"))
    return render_template("investors.html", investors=investors)


@app.route("/export")
@logged_in_required
@require_role("admin")
def export_data():
    loans, payments, _ = get_all_data()

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["id", "customer", "principal", "interest", "total_due", "paid_total", "balance", "status", "due_date"])
    writer.writeheader()
    for loan in loans:
        writer.writerow({k: loan[k] for k in writer.fieldnames})

    out.write("\n")
    out.write("payments\n")
    pay_writer = csv.DictWriter(out, fieldnames=["id", "loan_id", "customer", "amount", "payment_date", "registered_by", "notes"])
    pay_writer.writeheader()
    for p in payments:
        pay_writer.writerow({k: p.get(k, "") for k in pay_writer.fieldnames})

    buffer = io.BytesIO(out.getvalue().encode("utf-8"))
    return send_file(buffer, as_attachment=True, download_name="tradex_report.csv", mimetype="text/csv")


if __name__ == "__main__":
    ensure_files()
    app.run(host="0.0.0.0", port=5000, debug=True)
else:
    ensure_files()
