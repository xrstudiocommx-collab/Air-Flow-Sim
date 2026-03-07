import sqlite3
import os
import bcrypt
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "users.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('superadmin', 'admin', 'cliente')),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS proyectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            fecha TEXT NOT NULL DEFAULT (datetime('now')),
            imagen_original TEXT,
            imagen_resultado TEXT,
            datos_csv TEXT,
            admin_id INTEGER NOT NULL,
            asignado_a INTEGER,
            FOREIGN KEY (admin_id) REFERENCES users(id),
            FOREIGN KEY (asignado_a) REFERENCES users(id)
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'superadmin'")
    if cursor.fetchone()[0] == 0:
        hashed = bcrypt.hashpw("admin".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", hashed, "superadmin"),
        )

    conn.commit()
    conn.close()


def get_user(username):
    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(user) if user else None


def get_user_by_id(user_id):
    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None


def get_all_users():
    conn = get_connection()
    users = conn.execute("SELECT id, username, role, created_at FROM users ORDER BY id").fetchall()
    conn.close()
    return [dict(u) for u in users]


def get_users_by_role(role):
    conn = get_connection()
    users = conn.execute("SELECT id, username, role, created_at FROM users WHERE role = ?", (role,)).fetchall()
    conn.close()
    return [dict(u) for u in users]


def create_user(username, password, role):
    conn = get_connection()
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, hashed, role),
        )
        conn.commit()
        conn.close()
        return True, "Usuario creado exitosamente."
    except sqlite3.IntegrityError:
        conn.close()
        return False, "El nombre de usuario ya existe."


def update_user(user_id, username=None, password=None, role=None):
    conn = get_connection()
    if username:
        try:
            conn.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))
        except sqlite3.IntegrityError:
            conn.close()
            return False, "El nombre de usuario ya existe."
    if password:
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hashed, user_id))
    if role:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    conn.commit()
    conn.close()
    return True, "Usuario actualizado."


def delete_user(user_id):
    conn = get_connection()
    conn.execute("UPDATE proyectos SET asignado_a = NULL WHERE asignado_a = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def create_proyecto(nombre, admin_id, imagen_original=None, imagen_resultado=None, datos_csv=None, asignado_a=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO proyectos (nombre, admin_id, imagen_original, imagen_resultado, datos_csv, asignado_a)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (nombre, admin_id, imagen_original, imagen_resultado, datos_csv, asignado_a),
    )
    proyecto_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return proyecto_id


def update_proyecto(proyecto_id, **kwargs):
    conn = get_connection()
    for key, value in kwargs.items():
        if key in ("nombre", "imagen_original", "imagen_resultado", "datos_csv", "asignado_a"):
            conn.execute(f"UPDATE proyectos SET {key} = ? WHERE id = ?", (value, proyecto_id))
    conn.commit()
    conn.close()


def get_proyectos_by_admin(admin_id):
    conn = get_connection()
    rows = conn.execute(
        """SELECT p.*, u.username as admin_name, c.username as cliente_name
           FROM proyectos p
           JOIN users u ON p.admin_id = u.id
           LEFT JOIN users c ON p.asignado_a = c.id
           WHERE p.admin_id = ?
           ORDER BY p.fecha DESC""",
        (admin_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_proyectos():
    conn = get_connection()
    rows = conn.execute(
        """SELECT p.*, u.username as admin_name, c.username as cliente_name
           FROM proyectos p
           JOIN users u ON p.admin_id = u.id
           LEFT JOIN users c ON p.asignado_a = c.id
           ORDER BY p.fecha DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_proyectos_by_cliente(cliente_id):
    conn = get_connection()
    rows = conn.execute(
        """SELECT p.*, u.username as admin_name
           FROM proyectos p
           JOIN users u ON p.admin_id = u.id
           WHERE p.asignado_a = ?
           ORDER BY p.fecha DESC""",
        (cliente_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_proyecto(proyecto_id):
    conn = get_connection()
    row = conn.execute(
        """SELECT p.*, u.username as admin_name, c.username as cliente_name
           FROM proyectos p
           JOIN users u ON p.admin_id = u.id
           LEFT JOIN users c ON p.asignado_a = c.id
           WHERE p.id = ?""",
        (proyecto_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_proyecto(proyecto_id):
    conn = get_connection()
    proyecto = conn.execute("SELECT * FROM proyectos WHERE id = ?", (proyecto_id,)).fetchone()
    if proyecto:
        for field in ("imagen_original", "imagen_resultado", "datos_csv"):
            path = proyecto[field]
            if path and os.path.exists(path):
                os.remove(path)
    conn.execute("DELETE FROM proyectos WHERE id = ?", (proyecto_id,))
    conn.commit()
    conn.close()
