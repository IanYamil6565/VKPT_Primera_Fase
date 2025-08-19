import os
import serial
import time
import pymysql
from flask import Flask, render_template, request, redirect, url_for
from flask_socketio import SocketIO

# === CONFIGURACIÓN RÁPIDA ===
SERIAL_PORT = "COM12"  # Cámbialo aquí cuando varíe
BAUD = 115200

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

uid_global = ""
esp32 = None


def conectar_serial():
    """Intenta abrir el puerto serial con el ESP32."""
    global esp32
    if esp32 is None or not (esp32 and esp32.is_open):
        try:
            esp32 = serial.Serial(
                port=SERIAL_PORT,
                baudrate=BAUD,
                timeout=1,
                write_timeout=1
            )
            esp32.reset_input_buffer()
            esp32.reset_output_buffer()
            print(f"Puerto {SERIAL_PORT} conectado correctamente.")
        except serial.SerialException as e:
            esp32 = None
            print(f"No se pudo abrir el puerto {SERIAL_PORT}. Verifica la conexión del ESP32. Detalle: {e}")


def read_rfid():
    """Lee datos del puerto serial y emite los UID recibidos."""
    global uid_global, esp32
    conectar_serial()
    while True:
        if esp32 and esp32.is_open:
            try:
                line = esp32.readline()
                if line:
                    uid = line.decode("utf-8", errors="ignore").strip()
                    if uid:
                        uid_global = uid
                        print(f"UID leído: {uid_global}")
                        socketio.emit("nuevo_uid", {"uid": uid_global})
            except Exception as e:
                print(f"Error leyendo del puerto serial: {e}")
                try:
                    esp32.close()
                except Exception:
                    pass
                esp32 = None
        time.sleep(0.05)


def iniciar_hilo_si_corresponde():
    """Evita que el hilo lector se duplique en modo debug."""
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        socketio.start_background_task(read_rfid)


# === RUTAS DE FLASK ===

@app.route("/")
def index():
    return render_template("menu.html")


@app.route("/menu")
def menu():
    return render_template("menu.html")


@app.route("/ingreso")
def ingreso():
    return render_template("ingreso.html")


@app.route("/medicamentos")
def medicamentos():
    return render_template("medicamentos.html")


@app.route("/datos")
def datos():
    return render_template("datos.html")


@app.route("/tabla")
def tabla():
    uid = request.args.get("uid")
    if not uid:
        return render_template("tabla.html", datos=[])

    try:
        conexion = pymysql.connect(**db_config)
        with conexion.cursor() as cursor:
            query = "SELECT codigo, especie, raza, produccion FROM animales WHERE codigo = %s"
            cursor.execute(query, (uid,))
            datos = cursor.fetchall()
            return render_template("tabla.html", datos=datos)
    except pymysql.MySQLError as e:
        print(f"Error en MySQL: {e}")
        return render_template("tabla.html", datos=[])
    finally:
        if "conexion" in locals() and conexion.open:
            conexion.close()


@app.route("/detalles/<uid>")
def detalles(uid):
    try:
        conexion = pymysql.connect(**db_config)
        with conexion.cursor() as cursor:
            query = """
            SELECT codigo, especie, raza, sexo, peso, col_patron, tratamientos, est_reproductivo,
                   produccion, origen, lugar, coste, obs
            FROM animales
            WHERE codigo = %s
            """
            cursor.execute(query, (uid,))
            row = cursor.fetchone()

            if row:
                campos = ["codigo", "especie", "raza", "sexo", "peso", "col_patron", "tratamientos",
                          "est_reproductivo", "produccion", "origen", "lugar", "coste", "obs"]
                datos = dict(zip(campos, row))
                return render_template("detalles.html", datos=datos)
            else:
                return f"No se encontró el animal con UID {uid}", 404
    except pymysql.MySQLError as e:
        return f"Error en la base de datos: {e}", 500
    finally:
        if "conexion" in locals() and conexion.open:
            conexion.close()

@app.route("/registrar_tratamiento", methods=["POST"])
def registrar_tratamiento():
    data = request.get_json()
    uid = data.get("uid")
    medicamento = data.get("medicamento")

    if not uid or not medicamento:
        return {"status": "error", "message": "Faltan datos"}, 400

    try:
        conexion = pymysql.connect(**db_config)
        with conexion.cursor() as cursor:
            sql = "INSERT INTO tratamientos (uid_animal, medicamento) VALUES (%s, %s)"
            cursor.execute(sql, (uid, medicamento))
            conexion.commit()
        return {"status": "success", "message": f"Tratamiento registrado para {uid}"}
    except pymysql.MySQLError as e:
        return {"status": "error", "message": str(e)}, 500
    finally:
        if "conexion" in locals() and conexion.open:
            conexion.close()

@app.route("/register", methods=["POST"])
def register():
    global uid_global
    uid = uid_global if uid_global else request.form.get("uid")

    especie = request.form.get("especie")
    raza = request.form.get("raza")
    sexo = request.form.get("sexo")
    peso = request.form.get("peso")
    col_patron = request.form.get("col_patron")
    tratamientos = request.form.get("tratamientos")
    est_reproductivo = request.form.get("est_reproductivo")
    produccion = request.form.get("produccion")
    origen = request.form.get("origen")
    lugar = request.form.get("lugar")
    coste = request.form.get("coste")
    obs = request.form.get("obs")

    try:
        conexion = pymysql.connect(**db_config)
        with conexion.cursor() as cursor:
            sql = """
            INSERT INTO animales (codigo, especie, raza, sexo, peso, col_patron, tratamientos, est_reproductivo,
                                  produccion, origen, lugar, coste, obs)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (uid, especie, raza, sexo, peso, col_patron, tratamientos,
                                 est_reproductivo, produccion, origen, lugar, coste, obs))
            conexion.commit()
            print(f"Registro insertado correctamente: {uid}")
    except pymysql.MySQLError as e:
        print(f"Error en MySQL: {e}")
    finally:
        if "conexion" in locals() and conexion.open:
            conexion.close()
            print("Conexión cerrada.")

    return redirect(url_for("index"))

@app.route("/consulta_tratamientos")
def consulta_tratamientos():
    uid = request.args.get("uid")
    tratamientos = None

    if uid:
        try:
            conexion = pymysql.connect(**db_config)
            with conexion.cursor() as cursor:
                sql = "SELECT medicamento, fecha FROM tratamientos WHERE uid_animal = %s ORDER BY fecha DESC"
                cursor.execute(sql, (uid,))
                tratamientos = cursor.fetchall()
        except pymysql.MySQLError as e:
            print(f"Error en MySQL: {e}")
            tratamientos = []
        finally:
            if "conexion" in locals() and conexion.open:
                conexion.close()

    return render_template("consulta_tratamientos.html", tratamientos=tratamientos)

@app.route("/registrar_nacimiento", methods=["GET", "POST"])
def registrar_nacimiento():
    if request.method == "GET":
        return render_template("registrar_nacimiento.html")

    data = request.get_json()
    uid = data.get("uid")
    observaciones = data.get("observaciones", "")

    if not uid:
        return {"status": "error", "message": "UID no recibido"}, 400

    try:
        conexion = pymysql.connect(**db_config)
        with conexion.cursor() as cursor:
            sql = "INSERT INTO partos (uid_animal, observaciones) VALUES (%s, %s)"
            cursor.execute(sql, (uid, observaciones))
            conexion.commit()
        return {"status": "success", "message": f"Parto registrado para {uid}"}
    except pymysql.MySQLError as e:
        return {"status": "error", "message": str(e)}, 500
    finally:
        if "conexion" in locals() and conexion.open:
            conexion.close()

@app.route("/consulta_nacimiento")
def consulta_nacimiento():
    uid = request.args.get("uid")
    partos = None

    if uid:
        try:
            conexion = pymysql.connect(**db_config)
            with conexion.cursor() as cursor:
                sql = "SELECT fecha, observaciones FROM partos WHERE uid_animal = %s ORDER BY fecha DESC"
                cursor.execute(sql, (uid,))
                partos = cursor.fetchall()
        except pymysql.MySQLError as e:
            print(f"Error en MySQL: {e}")
            partos = []
        finally:
            if "conexion" in locals() and conexion.open:
                conexion.close()

    return render_template("consulta_nacimiento.html", partos=partos)

@app.route("/registrar_leche", methods=["GET", "POST"])
def registrar_leche():
    if request.method == "GET":
        return render_template("registrar_leche.html")

    data = request.get_json()
    uid = data.get("uid")
    litros = data.get("litros")

    if not uid:
        return {"status": "error", "message": "UID no recibido"}, 400
    if not litros:
        return {"status": "error", "message": "Cantidad de litros no recibida"}, 400

    try:
        litros = float(litros)  # Convertir a número
    except ValueError:
        return {"status": "error", "message": "Cantidad inválida"}, 400

    try:
        conexion = pymysql.connect(**db_config)
        with conexion.cursor() as cursor:
            sql = "INSERT INTO ordeñe (uid_animal, litros) VALUES (%s, %s)"
            cursor.execute(sql, (uid, litros))
            conexion.commit()
        return {"status": "success", "message": f"✅ Registrado {litros} L para {uid}"}
    except pymysql.MySQLError as e:
        return {"status": "error", "message": str(e)}, 500
    finally:
        if "conexion" in locals() and conexion.open:
            conexion.close()

@app.route("/consulta_leche")
def consulta_leche():
    uid = request.args.get("uid")
    ordeñes = None

    if uid:
        try:
            conexion = pymysql.connect(**db_config)
            with conexion.cursor() as cursor:
                sql = "SELECT fecha, litros FROM ordeñe WHERE uid_animal = %s ORDER BY fecha DESC"
                cursor.execute(sql, (uid,))
                ordeñes = cursor.fetchall()
        except pymysql.MySQLError as e:
            print(f"Error en MySQL: {e}")
            ordeñes = []
        finally:
            if "conexion" in locals() and conexion.open:
                conexion.close()

    return render_template("consulta_leche.html", ordeñes=ordeñes)

# === EVENTOS SOCKET.IO ===

@socketio.on("rfid_uid")
def recibir_uid(data):
    global uid_global
    uid_global = data["uid"]
    print(f"UID recibido desde la web: {uid_global}")
    socketio.emit("nuevo_uid", {"uid": uid_global})


# === CONFIG DB ===
db_config = {
    "host": "localhost",
    "user": "root",
    "password": "12345",
    "database": "VKPT",
    "port": 3306,
}


if __name__ == "__main__":
    iniciar_hilo_si_corresponde()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, use_reloader=False)
