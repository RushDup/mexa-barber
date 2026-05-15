from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_session import Session
import psycopg2
from psycopg2.extras import RealDictCursor
from functools import wraps
from datetime import datetime
from urllib.parse import quote
import os

app = Flask(__name__)

app.config["SECRET_KEY"] = "mexa_secret"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"

Session(app)

HORARIOS = [
    "10:00", "10:30",
    "11:00", "11:30",
    "12:00", "12:30",
    "13:00", "13:30",
    "14:00", "14:30",
    "15:00", "15:30",
    "16:00", "16:30",
    "17:00", "17:30",
    "18:00", "18:30",
    "19:00"
]


def conectar():
    database_url = os.environ.get("DATABASE_URL")

    if database_url:
        return psycopg2.connect(database_url)

    return psycopg2.connect(
        host="dpg-d83m88pkh4rs739s0t50-a.oregon-postgres.render.com",
        database="mexa_barber_db",
        user="mexa_barber_db_user",
        password="v0q8kDRCPW9bkdoMUqIklNlvkrlOKkBl",
        port=5432
    )


def init_db():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS citas (
            id SERIAL PRIMARY KEY,
            cliente TEXT NOT NULL,
            telefono TEXT NOT NULL,
            servicio TEXT NOT NULL,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            estado TEXT DEFAULT 'pendiente'
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "admin" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/horarios-disponibles")
def horarios_disponibles():
    fecha = request.args.get("fecha")
    excluir_id = request.args.get("excluir_id")

    if not fecha:
        return jsonify([])

    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d")

    if fecha_obj.weekday() == 0:
        return jsonify([])

    conn = conectar()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    if excluir_id:
        cursor.execute("""
            SELECT hora FROM citas
            WHERE fecha = %s
            AND estado != 'cancelada'
            AND id != %s
        """, (fecha, excluir_id))
    else:
        cursor.execute("""
            SELECT hora FROM citas
            WHERE fecha = %s
            AND estado != 'cancelada'
        """, (fecha,))

    ocupadas = [fila["hora"] for fila in cursor.fetchall()]

    cursor.close()
    conn.close()

    disponibles = [hora for hora in HORARIOS if hora not in ocupadas]

    return jsonify(disponibles)


@app.route("/agendar", methods=["GET", "POST"])
def agendar():
    if request.method == "POST":
        cliente = request.form["cliente"]
        telefono = request.form["telefono"]
        servicio = request.form["servicio"]
        fecha = request.form["fecha"]
        hora = request.form["hora"]

        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d")

        if fecha_obj.weekday() == 0:
            return render_template(
                "error.html",
                titulo="Los lunes no trabajamos",
                mensaje="Selecciona otro día disponible."
            )

        conn = conectar()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT * FROM citas
            WHERE fecha = %s
            AND hora = %s
            AND estado != 'cancelada'
        """, (fecha, hora))

        cita_existente = cursor.fetchone()

        if cita_existente:
            cursor.close()
            conn.close()

            return render_template(
                "error.html",
                titulo="Hora ocupada",
                mensaje="Selecciona otro horario disponible."
            )

        cursor.execute("""
            INSERT INTO citas (
                cliente,
                telefono,
                servicio,
                fecha,
                hora,
                estado
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            cliente,
            telefono,
            servicio,
            fecha,
            hora,
            "pendiente"
        ))

        conn.commit()
        cursor.close()
        conn.close()

        return render_template("confirmacion.html")

    return render_template("agendar.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        usuario = request.form["usuario"]
        password = request.form["password"]

        if usuario == "admin" and password == "1234":
            session["admin"] = True
            return redirect(url_for("admin"))

        error = "Usuario o contraseña incorrectos"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/admin")
@login_required
def admin():
    conn = conectar()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT * FROM citas
        ORDER BY fecha ASC, hora ASC
    """)

    citas = cursor.fetchall()

    hoy = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT COUNT(*) AS total FROM citas
        WHERE fecha = %s
    """, (hoy,))
    citas_hoy = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) AS total FROM citas
        WHERE estado = 'pendiente'
    """)
    pendientes = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) AS total FROM citas
        WHERE estado = 'aceptada'
    """)
    aceptadas = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) AS total FROM citas
        WHERE estado = 'cancelada'
    """)
    canceladas = cursor.fetchone()["total"]

    cursor.close()
    conn.close()

    return render_template(
        "admin.html",
        citas=citas,
        citas_hoy=citas_hoy,
        pendientes=pendientes,
        aceptadas=aceptadas,
        canceladas=canceladas
    )


@app.route("/aceptar/<int:id>")
@login_required
def aceptar(id):
    conn = conectar()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT * FROM citas
        WHERE id = %s
    """, (id,))

    cita = cursor.fetchone()

    if not cita:
        cursor.close()
        conn.close()

        return render_template(
            "error.html",
            titulo="Cita no encontrada",
            mensaje="La cita que intentas aceptar no existe."
        )

    cursor.execute("""
        UPDATE citas
        SET estado = 'aceptada'
        WHERE id = %s
    """, (id,))

    conn.commit()
    cursor.close()
    conn.close()

    telefono = cita["telefono"]

    mensaje = f"""
Hola {cita['cliente']} 👋

Tu cita en MEXA Barber Shop fue confirmada 💈

📅 Fecha: {cita['fecha']}
⏰ Hora: {cita['hora']}
✂️ Servicio: {cita['servicio']}

Te esperamos 🔥
"""

    mensaje = quote(mensaje)
    whatsapp_url = f"https://wa.me/52{telefono}?text={mensaje}"

    return redirect(whatsapp_url)


@app.route("/cancelar/<int:id>")
@login_required
def cancelar(id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE citas
        SET estado = 'cancelada'
        WHERE id = %s
    """, (id,))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for("admin"))


@app.route("/reagendar/<int:id>", methods=["GET", "POST"])
@login_required
def reagendar(id):
    conn = conectar()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT * FROM citas
        WHERE id = %s
    """, (id,))

    cita = cursor.fetchone()

    if not cita:
        cursor.close()
        conn.close()

        return render_template(
            "error.html",
            titulo="Cita no encontrada",
            mensaje="La cita que intentas reagendar no existe."
        )

    if request.method == "POST":
        nueva_fecha = request.form["fecha"]
        nueva_hora = request.form["hora"]

        fecha_obj = datetime.strptime(nueva_fecha, "%Y-%m-%d")

        if fecha_obj.weekday() == 0:
            cursor.close()
            conn.close()

            return render_template(
                "error.html",
                titulo="Los lunes no trabajamos",
                mensaje="Selecciona otro día disponible."
            )

        cursor.execute("""
            SELECT * FROM citas
            WHERE fecha = %s
            AND hora = %s
            AND estado != 'cancelada'
            AND id != %s
        """, (nueva_fecha, nueva_hora, id))

        cita_existente = cursor.fetchone()

        if cita_existente:
            cursor.close()
            conn.close()

            return render_template(
                "error.html",
                titulo="Hora ocupada",
                mensaje="Selecciona otro horario disponible."
            )

        cursor.execute("""
            UPDATE citas
            SET fecha = %s,
                hora = %s,
                estado = 'aceptada'
            WHERE id = %s
        """, (nueva_fecha, nueva_hora, id))

        conn.commit()
        cursor.close()
        conn.close()

        telefono = cita["telefono"]

        mensaje = f"""
Hola {cita['cliente']} 👋

Tu cita en MEXA Barber Shop fue reagendada 💈

📅 Nueva fecha: {nueva_fecha}
⏰ Nueva hora: {nueva_hora}
✂️ Servicio: {cita['servicio']}

Te esperamos 🔥
"""

        mensaje = quote(mensaje)
        whatsapp_url = f"https://wa.me/52{telefono}?text={mensaje}"

        return redirect(whatsapp_url)

    cursor.close()
    conn.close()

    return render_template("reagendar.html", cita=cita)


@app.route("/agenda")
@login_required
def agenda():
    return render_template("agenda.html")


@app.route("/api/citas")
@login_required
def api_citas():
    conn = conectar()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT * FROM citas
        WHERE estado != 'cancelada'
        ORDER BY fecha ASC, hora ASC
    """)

    citas = cursor.fetchall()

    cursor.close()
    conn.close()

    eventos = []

    for cita in citas:
        if cita["estado"] == "aceptada":
            color = "#16a34a"
        elif cita["estado"] == "pendiente":
            color = "#d4a85f"
        else:
            color = "#ef4444"

        eventos.append({
            "id": cita["id"],
            "title": f"{cita['hora']} - {cita['cliente']} ({cita['servicio']})",
            "start": f"{cita['fecha']}T{cita['hora']}:00",
            "backgroundColor": color,
            "borderColor": color,
            "extendedProps": {
                "cliente": cita["cliente"],
                "telefono": cita["telefono"],
                "servicio": cita["servicio"],
                "fecha": cita["fecha"],
                "hora": cita["hora"],
                "estado": cita["estado"]
            }
        })

    return jsonify(eventos)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)