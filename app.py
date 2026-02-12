# ---------- IMPORTS ----------
# =========================
# Standard Library
# =========================
import os
import io
import csv
from datetime import datetime, date, timedelta
from calendar import monthrange
from email.message import EmailMessage
import smtplib

# =========================
# Flask
# =========================
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    flash,
    url_for,
    jsonify,
    Response,
    send_file,
    send_from_directory,
    abort,
)

# =========================
# Database
# =========================
import mysql.connector
from mysql.connector import Error

# =========================
# Security / Auth
# =========================
import bcrypt
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# =========================
# PDF / Reports (ReportLab)
# =========================
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import mm, cm
from reportlab.lib import colors

# =========================
# IO Helpers
# =========================
from io import BytesIO
# -------------------------------------------------------------------------



# ---- App & config ----
app = Flask(__name__)
app.secret_key = "super_secret_key_123"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif"}
MAX_FILE_SIZE = 2 * 1024 * 1024

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT
# -------------------------------------------------------------------------



# ---------- DATABASE CONNECTION ----------
def get_db():
    return mysql.connector.connect(
        host="127.0.0.1",
        user="school_user",
        password="school123",
        database="SMIPS",
        auth_plugin="mysql_native_password"
    )
# -------------------------------------------------------------------------



# ---------- AUTH / LOGIN ----------
@app.route("/")
def index():
    return redirect("/login")

from werkzeug.security import check_password_hash

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        print("LOGIN ATTEMPT:", username)

        conn = get_db()
        cur = conn.cursor(dictionary=True)

        # 1️⃣ Get user
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()

        print("USER FOUND:", user)

        if not user or not check_password_hash(user["password"], password):
            flash("Invalid username or password")
            cur.close()
            conn.close()
            return redirect("/login")

        # 2️⃣ Reset session
        session.clear()
        session["user"] = user["username"]
        session["role"] = user["role"]
        session["user_id"] = user["id"]

        # ✅ 3️⃣ IMPORTANT: STUDENT LINK
        if user["role"] == "student":
            cur.execute(
                "SELECT id FROM students WHERE user_id=%s",
                (user["id"],)
            )
            student = cur.fetchone()

            print("STUDENT LINK:", student)

            if not student:
                flash("Student profile not linked. Contact admin.")
                cur.close()
                conn.close()
                return redirect("/login")

            # 🔥 THIS WAS MISSING
            session["student_id"] = student["id"]

        print("SESSION SET:", dict(session))

        cur.close()
        conn.close()

        return redirect("/dashboard")

    return render_template("login.html")

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username = request.form.get("username")
        flash("Please contact the administrator to reset your password.")
        return redirect("/")

    return render_template("forgot_password.html")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/login")

    role = session.get("role")

    if role == "admin":
        return redirect("/admin/dashboard")
    elif role == "teacher":
        return redirect("/teacher/dashboard")
    elif role == "student":
        return redirect("/student/dashboard")
    elif role == "parent":
        return redirect("/parent/dashboard")
    else:
        abort(403)

@app.route("/admin/dashboard")
def admin_dashboard():
    if "user" not in session or session.get("role") != "admin":
        abort(403)

    conn = get_db()
    cur = conn.cursor()

    # total users
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]

    # ✅ total students (FROM students table)
    cur.execute("SELECT COUNT(*) FROM students")
    total_students = cur.fetchone()[0]

    # teachers
    cur.execute("SELECT COUNT(*) FROM users WHERE role='teacher'")
    total_teachers = cur.fetchone()[0]

    # parents
    cur.execute("SELECT COUNT(*) FROM users WHERE role='parent'")
    total_parents = cur.fetchone()[0]

    cur.close()
    conn.close()

    stats = {
        "total_users": total_users,
        "total_students": total_students,
        "total_teachers": total_teachers,
        "total_parents": total_parents,
    }

    return render_template("dashboard_admin.html", stats=stats)

@app.route("/teacher/dashboard")
def teacher_dashboard():
    if "user" not in session:
        return redirect("/login")

    if session.get("role") != "teacher":
        abort(403)

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # 1️⃣ Total classes
    cur.execute("SELECT COUNT(*) AS cnt FROM classes")
    classes_count = cur.fetchone()["cnt"]

    # 2️⃣ Total students
    cur.execute("SELECT COUNT(*) AS cnt FROM students")
    students_count = cur.fetchone()["cnt"]

    # 3️⃣ Total assignments
    cur.execute("SELECT COUNT(*) AS cnt FROM assignments")
    assignments_count = cur.fetchone()["cnt"]

    # 4️⃣ Pending marks (students without submission)
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM students s
        JOIN assignments a ON a.class_id = s.class_id
        LEFT JOIN assignment_submissions sub
            ON sub.student_id = s.id
            AND sub.assignment_id = a.id
        WHERE sub.id IS NULL
    """)
    pending_marks = cur.fetchone()["cnt"]

    cur.close()
    conn.close()

    stats = {
        "classes": classes_count,
        "students": students_count,
        "assignments": assignments_count,
        "pending_marks": pending_marks
    }

    return render_template(
        "dashboard_teacher.html",
        stats=stats,
        year=2026
    )

@app.route("/student/dashboard")
def student_dashboard():
    if "user" not in session or session.get("role") != "student":
        abort(403)

    student_id = session.get("student_id")
    if not student_id:
        return redirect("/logout")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # Student + class
    cur.execute("""
        SELECT s.id, s.name, s.class_id, c.name AS class_name, c.section
        FROM students s
        LEFT JOIN classes c ON c.id = s.class_id
        WHERE s.id = %s
    """, (student_id,))
    student = cur.fetchone()

    if not student:
        cur.close()
        conn.close()
        return redirect("/logout")

    # Attendance %
    cur.execute("""
        SELECT ROUND((SUM(status='Present') / COUNT(*)) * 100, 0) AS pct
        FROM attendance
        WHERE student_id = %s
    """, (student_id,))
    attendance = cur.fetchone()["pct"] or 0

    # Total assignments (BY CLASS)
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM assignments
        WHERE class_id = %s
    """, (student["class_id"],))
    total_assignments = cur.fetchone()["cnt"]

    # Completed assignments
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM assignment_submissions
        WHERE student_id = %s
    """, (student_id,))
    completed = cur.fetchone()["cnt"]

    cur.close()
    conn.close()

    stats = {
        "attendance": attendance,
        "assignments": total_assignments,
        "completed": completed,
        "pending": max(total_assignments - completed, 0)
    }

    return render_template(
        "dashboard_student.html",
        student=student,
        stats=stats,
        year=2026
    )

@app.route("/parent/dashboard")
def parent_dashboard():
    if "user" not in session or session.get("role") != "parent":
        abort(403)

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT
            s.id,
            s.name,
            c.name AS class_name,
            c.section
        FROM parent_student ps
        JOIN students s ON s.id = ps.student_id
        LEFT JOIN classes c ON c.id = s.class_id
        WHERE ps.parent_user_id = %s
    """, (session["user_id"],))

    children = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "dashboard_parent.html",
        children=children
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")
# -------------------------------------------------------------------------



# ---------- USER MANAGEMENT: Add User ----------
@app.route("/users")
def users():
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, username, role
        FROM users
        ORDER BY id DESC
    """)
    users = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("users_list.html", users=users)

@app.route("/users/add", methods=["GET", "POST"])
def add_user():
    if "user" not in session:
        return redirect("/login")

    if session.get("role") != "admin":
        abort(403)

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "").strip().lower()

        allowed_roles = ("admin", "teacher", "student", "parent")
        if role not in allowed_roles:
            flash("Invalid role selected.")
            return redirect(url_for("add_user"))

        if not username or not password:
            flash("Username and password are required.")
            return redirect(url_for("add_user"))

        hashed_password = generate_password_hash(password)

        conn = get_db()
        cur = conn.cursor()

        # prevent duplicate usernames
        cur.execute("SELECT id FROM users WHERE username=%s", (username,))
        if cur.fetchone():
            flash("Username already exists.")
            cur.close()
            conn.close()
            return redirect(url_for("add_user"))

        cur.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
            (username, hashed_password, role)
        )
        conn.commit()
        cur.close()
        conn.close()

        flash("User added successfully")
        return redirect(url_for("users"))

    return render_template("add_user.html")

@app.route("/users/edit/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):
    if "user" not in session:
        return redirect("/login")

    if session.get("role") != "admin":
        abort(403)

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT id, username, role FROM users WHERE id=%s", (user_id,))
    user = cur.fetchone()

    if not user:
        cur.close()
        conn.close()
        abort(404)

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        role = request.form.get("role", "teacher").strip().lower()

        if role not in ("admin", "teacher", "student", "parent"):
            role = "teacher"


        if not username:
            flash("Username is required.")
            return redirect(url_for("edit_user", user_id=user_id))

        cur.execute(
            "UPDATE users SET username=%s, role=%s WHERE id=%s",
            (username, role, user_id)
        )
        conn.commit()

        cur.close()
        conn.close()

        flash("User updated successfully")
        return redirect(url_for("users"))

    cur.close()
    conn.close()
    return render_template("edit_user.html", user=user)

@app.route("/users/delete/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    if "user" not in session:
        return redirect("/login")

    if session.get("role") != "admin":
        abort(403)

    # prevent deleting yourself
    if session.get("user_id") == user_id:
        flash("You cannot delete your own account.")
        return redirect(url_for("users"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
    conn.commit()

    cur.close()
    conn.close()

    flash("User deleted successfully")
    return redirect(url_for("users"))
# -------------------------------------------------------------------------



# ---------- STUDENTS: List / Add / Edit / Delete ----------
@app.route("/students")
def students_list():
    if "user" not in session:
        return redirect("/")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT 
            s.id,
            s.name,
            c.name AS class_name
        FROM students s
        LEFT JOIN classes c ON s.class_id = c.id
        ORDER BY s.id DESC
    """)

    students = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("students.html", students=students)

@app.route("/students/add", methods=["GET", "POST"])
def add_student():
    if "user" not in session:
        return redirect("/")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # LOAD CLASSES FOR DROPDOWN
    cur.execute("SELECT id, name, section FROM classes ORDER BY name, section")
    classes = cur.fetchall()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        class_id = request.form.get("class_id")

        dob = request.form.get("dob")
        phone = request.form.get("phone", "").strip()
        parent_name = request.form.get("parent_name", "").strip()
        parent_phone = request.form.get("parent_phone", "").strip()
        address = request.form.get("address", "").strip()

        photo_file = request.files.get("photo")
        photo_filename = None

        # -------- IMAGE UPLOAD ----------
        if photo_file and photo_file.filename:
            if not allowed_file(photo_file.filename):
                flash("Invalid image type")
                return redirect(request.url)

            fname = secure_filename(photo_file.filename)
            uniq = f"{int(datetime.utcnow().timestamp())}_{fname}"
            dest = os.path.join(app.config["UPLOAD_FOLDER"], uniq)

            photo_file.save(dest)
            photo_filename = uniq

        # -------- INSERT ----------
        cur.execute("""
            INSERT INTO students
            (name, class_id, dob, phone, parent_name, parent_phone, address, photo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (name, class_id, dob, phone, parent_name, parent_phone, address, photo_filename))

        conn.commit()

        cur.close()
        conn.close()

        flash("Student added successfully")
        return redirect(url_for("students_list"))

    cur.close()
    conn.close()

    return render_template("add_student.html", classes=classes)


@app.route("/students/edit/<int:student_id>", methods=["GET", "POST"])
def edit_student(student_id):
    if "user" not in session:
        return redirect("/")
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        cls = request.form.get("class", "").strip()
        section = request.form.get("section", "").strip()
        dob = request.form.get("dob", None)
        phone = request.form.get("phone", "").strip()
        parent_name = request.form.get("parent_name", "").strip()
        parent_phone = request.form.get("parent_phone", "").strip()
        address = request.form.get("address", "").strip()

        photo_file = request.files.get("photo")
        if photo_file and photo_file.filename != "":
            if not allowed_file(photo_file.filename):
                flash("Invalid image type.")
                return redirect(request.url)
            # save new photo
            fname = secure_filename(photo_file.filename)
            uniq = f"{int(datetime.utcnow().timestamp())}_{fname}"
            dest = os.path.join(app.config["UPLOAD_FOLDER"], uniq)
            photo_file.save(dest)
            # delete old photo
            cur.execute("SELECT photo FROM students WHERE id=%s", (student_id,))
            old = cur.fetchone()
            if old and old.get("photo"):
                try:
                    os.remove(os.path.join(app.config["UPLOAD_FOLDER"], old["photo"]))
                except Exception:
                    pass
            # update photo filename
            cur.execute("UPDATE students SET photo=%s WHERE id=%s", (uniq, student_id))

        cur.execute(
            """UPDATE students SET name=%s, class=%s, section=%s, dob=%s, phone=%s,
               parent_name=%s, parent_phone=%s, address=%s WHERE id=%s""",
            (name, cls, section, dob, phone, parent_name, parent_phone, address, student_id)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Student updated.")
        return redirect(url_for("students_list"))

    cur.execute("SELECT * FROM students WHERE id=%s", (student_id,))
    student = cur.fetchone()
    cur.close()
    conn.close()
    if not student:
        flash("Student not found.")
        return redirect(url_for("students_list"))
    return render_template("edit_student.html", student=student)

@app.route("/students/delete/<int:student_id>", methods=["POST"])
def delete_student(student_id):
    if "user" not in session:
        return redirect("/")
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT photo FROM students WHERE id=%s", (student_id,))
    r = cur.fetchone()
    if r and r.get("photo"):
        try:
            os.remove(os.path.join(app.config["UPLOAD_FOLDER"], r["photo"]))
        except Exception:
            pass
    cur.execute("DELETE FROM students WHERE id=%s", (student_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Student deleted.")
    return redirect(url_for("students_list"))

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/students/<int:student_id>")
def student_view(student_id):
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT s.*, c.name AS class_name, c.section
        FROM students s
        LEFT JOIN classes c ON c.id = s.class_id
        WHERE s.id = %s
    """, (student_id,))

    student = cur.fetchone()
    cur.close()
    conn.close()

    if not student:
        abort(404)

    return render_template("student_view.html", student=student)
# -------------------------------------------------------------------------



# ---------- STUDENT PROFILE ----------
@app.route("/students/profile/<int:student_id>")
def student_profile(student_id):
    if "user" not in session:
        return redirect("/")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # Student info
    cur.execute("SELECT * FROM students WHERE id = %s", (student_id,))
    student = cur.fetchone()

    if not student:
        cur.close()
        conn.close()
        flash("Student not found")
        return redirect("/students")

    # Fees history
    cur.execute("""
        SELECT amount, status, DATE(created_at) AS date, note
        FROM fees
        WHERE student_id = %s
        ORDER BY created_at DESC
    """, (student_id,))
    fees = cur.fetchall()

    # Fee summary
    cur.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN status='paid' THEN amount ELSE 0 END),0) AS total_paid,
            COALESCE(SUM(CASE WHEN status='unpaid' THEN amount ELSE 0 END),0) AS total_due
        FROM fees
        WHERE student_id = %s
    """, (student_id,))
    fee_summary = cur.fetchone()

    # Attendance summary
    cur.execute("""
        SELECT
            SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) AS present,
            SUM(CASE WHEN status='absent' THEN 1 ELSE 0 END) AS absent,
            COUNT(*) AS total
        FROM attendance
        WHERE student_id = %s
    """, (student_id,))
    attendance = cur.fetchone()

    cur.close()
    conn.close()

    return render_template(
        "student_profile.html",
        student=student,
        fees=fees,
        fee_summary=fee_summary,
        attendance=attendance
    )

def get_parent_students(parent_username):
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT s.id, s.name, s.class_id
        FROM parent_student ps
        JOIN users u ON u.id = ps.parent_user_id
        JOIN students s ON s.id = ps.student_id
        WHERE u.username = %s
    """, (parent_username,))

    students = cur.fetchall()
    cur.close()
    conn.close()

    return students

@app.route("/parents/link", methods=["GET", "POST"])
def link_parent_student():
    if "user" not in session:
        return redirect("/login")

    if session.get("role") != "admin":
        abort(403)

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # load parents (IMPORTANT: from parents table)
    cur.execute("""
        SELECT p.id, p.name
        FROM parents p
        JOIN users u ON u.id = p.user_id
        ORDER BY p.name
    """)
    parents = cur.fetchall()

    # load students
    cur.execute("""
        SELECT id, name
        FROM students
        ORDER BY name
    """)
    students = cur.fetchall()

    if request.method == "POST":
        parent_id = request.form.get("parent_id")
        student_id = request.form.get("student_id")

        if parent_id and student_id:
            cur.execute("""
                INSERT IGNORE INTO parent_student (parent_id, student_id)
                VALUES (%s, %s)
            """, (parent_id, student_id))

            conn.commit()
            flash("Parent linked to student successfully 🔗")

    cur.close()
    conn.close()

    return render_template(
        "parent_student_link.html",
        parents=parents,
        students=students
    )

@app.route("/parent/some-page")
def parent_some_page():
    if "user" not in session:
        return redirect("/login")

    if session.get("role") != "parent":
        abort(403)

    students = get_parent_students(session["user"])

    if not students:
        flash("No student linked to this parent.")
        return redirect("/dashboard")
# -------------------------------------------------------------------------



# ---------- CLASSES MODULE ----------
@app.route("/classes")
def classes():
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT id, name, section
        FROM classes
        ORDER BY name, section
    """)
    classes = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("classes.html", classes=classes)

@app.route("/classes/add", methods=["GET", "POST"])
def classes_add():
    if request.method == "POST":
        name = request.form.get("name").strip()
        section = request.form.get("section").strip() or None

        conn = get_db()
        cur = conn.cursor()

        try:
            cur.execute(
                "INSERT INTO classes (name, section) VALUES (%s, %s)",
                (name, section)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            flash("Class already exists or invalid data.")
        finally:
            cur.close()
            conn.close()

        return redirect("/classes")

    return render_template("classes_add.html")

@app.route("/classes/edit/<int:class_id>", methods=["GET", "POST"])
def classes_edit(class_id):
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form.get("name").strip()
        section = request.form.get("section").strip() or None

        cur.execute(
            "UPDATE classes SET name=%s, section=%s WHERE id=%s",
            (name, section, class_id)
        )
        conn.commit()

        cur.close()
        conn.close()
        return redirect("/classes")

    # GET request → load class data
    cur.execute(
        "SELECT id, name, section FROM classes WHERE id=%s",
        (class_id,)
    )
    cls = cur.fetchone()

    cur.close()
    conn.close()

    if not cls:
        abort(404)

    return render_template("classes_edit.html", cls=cls)
# -------------------------------------------------------------------------



# ---------- NOTICES MODULE ----------
@app.route("/notices/add", methods=["GET", "POST"])
def add_notice():
    if "user" not in session:
        return redirect("/login")

    if session.get("role") not in ("admin", "teacher"):
        abort(403)

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # load classes for dropdown
    cur.execute("SELECT id, name FROM classes ORDER BY name")
    classes = cur.fetchall()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        message = request.form.get("message", "").strip()
        class_id = request.form.get("class_id") or None

        if not title or not message:
            flash("Title and message are required.")
            return redirect(url_for("add_notice"))

        cur.execute(
            "SELECT id FROM users WHERE username=%s",
            (session["user"],)
        )
        user_id = cur.fetchone()["id"]

        cur.execute(
            """
            INSERT INTO notices (title, message, class_id, created_by)
            VALUES (%s, %s, %s, %s)
            """,
            (title, message, class_id, user_id)
        )
        conn.commit()

        flash("Notice posted successfully 📢")
        return redirect(url_for("list_notices"))

    return render_template("notice_add.html", classes=classes)

@app.route("/notices")
def list_notices():
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    sql = """
        SELECT
            n.title,
            n.message,
            n.created_at,
            c.name AS class_name
        FROM notices n
        LEFT JOIN classes c ON n.class_id = c.id
        ORDER BY n.created_at DESC
    """

    cur.execute(sql)
    notices = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("notices.html", notices=notices)
# -------------------------------------------------------------------------



# ---------- ASSIGNMENTS MODULE ----------
@app.route("/assignments/add", methods=["GET", "POST"])
def add_assignment():
    if "user" not in session:
        return redirect("/login")

    if session.get("role") not in ("admin", "teacher"):
        abort(403)

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT id, name FROM classes ORDER BY name")
    classes = cur.fetchall()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        class_id = request.form.get("class_id")
        due_date = request.form.get("due_date")

        cur.execute(
            "SELECT id FROM users WHERE username=%s",
            (session["user"],)
        )
        user_id = cur.fetchone()["id"]

        cur.execute("""
            INSERT INTO assignments (title, description, class_id, due_date, created_by)
            VALUES (%s,%s,%s,%s,%s)
        """, (title, description, class_id, due_date, user_id))

        conn.commit()
        flash("Assignment created successfully 📄")
        return redirect(url_for("list_assignments"))

    return render_template("assignment_add.html", classes=classes)

@app.route("/assignments")
def list_assignments():
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT
            a.id,
            a.title,
            a.description,
            a.due_date,
            c.name AS class_name
        FROM assignments a
        JOIN classes c ON a.class_id = c.id
        ORDER BY a.due_date ASC
    """)

    assignments = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("assignments.html", assignments=assignments)

@app.route("/assignments/submit/<int:assignment_id>", methods=["GET", "POST"])
def submit_assignment(assignment_id):
    if "user" not in session:
        return redirect("/login")

    if session.get("role") != "student":
        abort(403)

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # get student id
    cur.execute("""
        SELECT s.id FROM students s
        JOIN users u ON u.username=%s
    """, (session["user"],))
    student = cur.fetchone()

    if request.method == "POST":
        submission_text = request.form.get("submission_text", "").strip()

        cur.execute("""
            INSERT INTO assignment_submissions (assignment_id, student_id, submission_text)
            VALUES (%s,%s,%s)
            ON DUPLICATE KEY UPDATE
            submission_text=VALUES(submission_text),
            submitted_at=CURRENT_TIMESTAMP
        """, (assignment_id, student["id"], submission_text))

        conn.commit()
        flash("Assignment submitted ✅")
        return redirect(url_for("list_assignments"))

    cur.execute(
        "SELECT title, description, due_date FROM assignments WHERE id=%s",
        (assignment_id,)
    )
    assignment = cur.fetchone()

    return render_template("assignment_submit.html", assignment=assignment)

@app.route("/assignments/submissions/<int:assignment_id>", methods=["GET", "POST"])
def view_submissions(assignment_id):
    if "user" not in session:
        return redirect("/login")

    if session.get("role") not in ("admin", "teacher"):
        abort(403)

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # assignment info
    cur.execute(
        "SELECT title FROM assignments WHERE id=%s",
        (assignment_id,)
    )
    assignment = cur.fetchone()

    if request.method == "POST":
        submission_id = request.form.get("submission_id")
        marks = request.form.get("marks") or None
        remarks = request.form.get("remarks", "").strip()

        cur.execute("""
            UPDATE assignment_submissions
            SET marks=%s, remarks=%s
            WHERE id=%s
        """, (marks, remarks, submission_id))

        conn.commit()
        flash("Grade saved successfully ✅")
        return redirect(request.url)

    # load submissions
    cur.execute("""
        SELECT
            sub.id,
            s.name AS student_name,
            sub.submission_text,
            sub.file_path,
            sub.marks,
            sub.remarks,
            sub.submitted_at
        FROM assignment_submissions sub
        JOIN students s ON s.id = sub.student_id
        WHERE sub.assignment_id = %s
        ORDER BY sub.submitted_at DESC
    """, (assignment_id,))

    submissions = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "assignment_submissions.html",
        assignment=assignment,
        submissions=submissions
    )

@app.route("/parent/assignments")
def parent_assignments():
    if "user" not in session:
        return redirect("/login")

    if session.get("role") != "parent":
        abort(403)

    students = get_parent_students(session["user"])
    if not students:
        flash("No student linked.")
        return redirect("/parent/dashboard")

    student_ids = [s["id"] for s in students]
    placeholders = ",".join(["%s"] * len(student_ids))

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute(f"""
        SELECT
            a.title,
            a.due_date,
            s.name AS student_name,
            sub.marks,
            sub.remarks
        FROM assignment_submissions sub
        JOIN assignments a ON a.id = sub.assignment_id
        JOIN students s ON s.id = sub.student_id
        WHERE sub.student_id IN ({placeholders})
        ORDER BY a.due_date
    """, tuple(student_ids))

    assignments = cur.fetchall()
    cur.close()
    conn.close()

    return render_template(
        "parent_assignments.html",
        assignments=assignments
    )
# -------------------------------------------------------------------------



# ---------- BOOKS MODULE ----------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

UPLOAD_FOLDER = "static/uploads/books"
ALLOWED_EXTENSIONS = {"pdf"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

@app.route("/books/add", methods=["GET", "POST"])
def add_book():
    if "user" not in session:
        return redirect("/login")

    if session.get("role") not in ("admin", "teacher"):
        abort(403)

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # load classes
    cur.execute("SELECT id, name FROM classes ORDER BY name")
    classes = cur.fetchall()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        subject = request.form.get("subject", "").strip()
        description = request.form.get("description", "").strip()
        class_id = request.form.get("class_id")
        file = request.files.get("file")

        if not title or not subject or not class_id or not file:
            flash("All fields are required.")
            return redirect(url_for("add_book"))

        if not allowed_file(file.filename):
            flash("Only PDF files are allowed.")
            return redirect(url_for("add_book"))

        filename = secure_filename(file.filename)
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(save_path)

        # get uploader id
        cur.execute(
            "SELECT id FROM users WHERE username=%s",
            (session["user"],)
        )
        user_id = cur.fetchone()["id"]

        cur.execute("""
            INSERT INTO books (title, subject, description, class_id, file_path, uploaded_by)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (title, subject, description, class_id, save_path, user_id))

        conn.commit()
        cur.close()
        conn.close()

        flash("Book uploaded successfully 📚")
        return redirect(url_for("list_books"))

    return render_template("book_add.html", classes=classes)

@app.route("/books")
def list_books():
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT
            b.title,
            b.subject,
            b.description,
            c.name AS class_name,
            CONCAT('/', b.file_path) AS file_url
        FROM books b
        JOIN classes c ON b.class_id = c.id
        ORDER BY b.uploaded_at DESC
    """)

    books = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("books.html", books=books)
# -------------------------------------------------------------------------



# ---------- HOMEWORK MODULE ----------
@app.route("/homework/add", methods=["GET", "POST"])
def add_homework():
    if "user" not in session:
        return redirect("/login")

    if session.get("role") not in ("admin", "teacher"):
        abort(403)

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT id, name FROM classes ORDER BY name")
    classes = cur.fetchall()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        class_id = request.form.get("class_id")
        due_date = request.form.get("due_date")

        if not title or not description or not class_id or not due_date:
            flash("All fields are required.")
            return redirect(url_for("add_homework"))

        cur.execute(
            "SELECT id FROM users WHERE username=%s",
            (session["user"],)
        )
        user_id = cur.fetchone()["id"]

        cur.execute(
            """
            INSERT INTO homework (title, description, class_id, due_date, created_by)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (title, description, class_id, due_date, user_id)
        )
        conn.commit()

        flash("Homework assigned successfully 📝")
        return redirect(url_for("list_homework"))

    return render_template("homework_add.html", classes=classes)

@app.route("/homework")
def list_homework():
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    sql = """
        SELECT
            h.title,
            h.description,
            h.due_date,
            h.created_at,
            c.name AS class_name
        FROM homework h
        JOIN classes c ON h.class_id = c.id
        ORDER BY h.due_date ASC
    """

    cur.execute(sql)
    homework = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("homework.html", homework=homework)

@app.route("/parent/homework")
def parent_homework():
    if "user" not in session:
        return redirect("/login")

    if session.get("role") != "parent":
        abort(403)

    students = get_parent_students(session["user"])
    if not students:
        flash("No student linked.")
        return redirect("/parent/dashboard")

    student_ids = [s["id"] for s in students]
    placeholders = ",".join(["%s"] * len(student_ids))

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute(f"""
        SELECT
            h.title,
            h.due_date,
            s.name AS student_name
        FROM homework h
        JOIN students s ON s.class_id = h.class_id
        WHERE s.id IN ({placeholders})
        ORDER BY h.due_date
    """, tuple(student_ids))

    homework = cur.fetchall()
    cur.close()
    conn.close()

    return render_template(
        "parent_homework.html",
        homework=homework
    )
# -------------------------------------------------------------------------



# ---------- ATTENDANCE MODULE ----------
@app.route("/attendance/classes_json")
def attendance_classes_json():
    if "user" not in session:
        return jsonify([]), 401
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT class FROM students WHERE class IS NOT NULL AND class <> '' ORDER BY class")
    rows = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(rows)

# --- 1) attendance ---
from datetime import date, datetime

@app.route("/attendance")
def attendance():
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT id, name, section
        FROM classes
        ORDER BY name, section
    """)
    classes = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "attendance.html",
        classes=classes,
        today=date.today().isoformat()
    )

# --- 2) attendance roster ---
@app.route("/attendance/roster", methods=["GET", "POST"])
def attendance_roster():
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # --------------------------------
    # LOAD CLASSES
    # --------------------------------
    cur.execute("""
        SELECT id, name, section
        FROM classes
        ORDER BY name, section
    """)
    classes = cur.fetchall()

    # --------------------------------
    # HANDLE POST (SAVE ATTENDANCE)
    # --------------------------------
    if request.method == "POST":
        class_id = request.form.get("class_id")
        d = request.form.get("date") or date.today().isoformat()

        if not class_id:
            flash("Class is required")
            return redirect(url_for("attendance_roster"))

        try:
            datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            flash("Invalid date")
            return redirect(url_for("attendance_roster"))

        for key, value in request.form.items():
            if key.startswith("status_"):
                student_id = key.replace("status_", "")
                status = value
                remarks = request.form.get(f"remarks_{student_id}", "")

                cur.execute("""
                    INSERT INTO attendance (student_id, class_id, date, status, remarks)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        status = VALUES(status),
                        remarks = VALUES(remarks)
                """, (student_id, class_id, d, status, remarks))

        conn.commit()
        flash("Attendance saved successfully ✅")

        # ✅ safer redirect
        return redirect(url_for("attendance_roster", class_id=class_id, date=d))

    # --------------------------------
    # HANDLE GET (SHOW STUDENTS)
    # --------------------------------
    class_id = request.args.get("class_id")
    d = request.args.get("date") or date.today().isoformat()

    try:
        datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        flash("Invalid date")
        return redirect(url_for("attendance_roster"))

    students = []
    att_map = {}

    if class_id:
        cur.execute("""
            SELECT id, name
            FROM students
            WHERE class_id = %s
            ORDER BY name
        """, (class_id,))
        students = cur.fetchall()

        if students:
            ids = [s["id"] for s in students]
            placeholders = ",".join(["%s"] * len(ids))

            cur.execute(
                f"""
                SELECT student_id, status, remarks
                FROM attendance
                WHERE date = %s
                  AND student_id IN ({placeholders})
                """,
                tuple([d] + ids)
            )

            for r in cur.fetchall():
                att_map[r["student_id"]] = r

    cur.close()
    conn.close()

    return render_template(
        "attendance_roster.html",
        classes=classes,
        students=students,
        class_selected=class_id,
        date_selected=d,
        att_map=att_map
    )

# --- 3) attendance save ---
@app.route("/attendance/save", methods=["POST"])
def attendance_save():
    if "user" not in session:
        return redirect("/")
    d = request.form.get("date", date.today().isoformat()).strip()
    cls = request.form.get("class", "").strip()

    try:
        dt = datetime.strptime(d, "%Y-%m-%d").date()
    except Exception:
        flash("Invalid date format")
        return redirect(url_for("attendance_roster"))

    student_ids = []
    for key in request.form.keys():
        if key.startswith("status_"):
            sid = key.split("_", 1)[1]
            if sid.isdigit():
                student_ids.append(int(sid))

    if not student_ids:
        flash("No students submitted.")
        return redirect(url_for("attendance_roster"))

    conn = get_db()
    cur = conn.cursor()
    insert_sql = """
        INSERT INTO attendance (student_id, date, status, remarks, created_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE status = VALUES(status), remarks = VALUES(remarks), created_at = NOW()
    """
    params = []
    for sid in student_ids:
        status = request.form.get(f"status_{sid}", "absent")
        remarks = request.form.get(f"remarks_{sid}", "")
        params.append((sid, d, status, remarks))

    try:
        cur.executemany(insert_sql, params)
        conn.commit()
        flash("Attendance saved.")
    except Exception as e:
        conn.rollback()
        print("Attendance save error:", repr(e))
        flash("Failed to save attendance.")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("attendance_roster", **{"class": cls, "date": d}))

# --- 4) attendance export ---
import csv
from flask import Response

@app.route("/attendance/export")
def export_attendance():
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT s.name, a.date, a.status, a.class_id
        FROM attendance a
        JOIN students s ON s.id = a.student_id
    """)
    rows = cur.fetchall()

    def generate():
        yield "Name,Date,Status,Class\n"
        for r in rows:
            yield f"{r['name']},{r['date']},{r['status']},{r['class_id']}\n"

    return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=attendance.csv"}
    )

# --- 5) attendance history ---
@app.route("/attendance/history", methods=["GET", "POST"])
def attendance_history():
    if "user" not in session:
        return redirect("/")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    class_id = request.form.get("class_id")
    date = request.form.get("date")

    query = """
        SELECT a.id, s.name, a.status, a.date, a.class_id
        FROM attendance a
        JOIN students s ON s.id = a.student_id
        WHERE 1=1
    """
    params = []

    if class_id:
        query += " AND a.class_id=%s"
        params.append(class_id)
    if date:
        query += " AND a.date=%s"
        params.append(date)

    query += " ORDER BY a.date DESC"

    cur.execute(query, params)
    data = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("attendance_history.html", data=data)

# --- 6) attendance monthly_data ---
@app.route("/attendance/monthly", methods=["GET"])
def attendance_monthly():
    if "user" not in session:
        return redirect("/")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # Monthly attendance summary per student
    cur.execute("""
        SELECT 
            s.id AS student_id,
            s.name,
            COUNT(a.id) AS total_days,
            SUM(a.status = 'Present') AS present_days,
            SUM(a.status = 'Absent') AS absent_days,
            SUM(a.status = 'Leave') AS leave_days
        FROM students s
        LEFT JOIN attendance a ON s.id = a.student_id
        GROUP BY s.id, s.name
        ORDER BY s.name
    """)

    data = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("attendance_monthly.html", data=data)

# --- 7) attendance report ---
@app.route("/attendance/report")
def attendance_report():
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT s.name,
               COUNT(a.id) AS total,
               SUM(a.status='Present') AS present,
               ROUND((SUM(a.status='Present')/COUNT(a.id))*100,2) AS percentage
        FROM attendance a
        JOIN students s ON s.id = a.student_id
        GROUP BY s.id
    """)
    data = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("attendance_report.html", data=data)

# --- 8) Prevent duplicate attendance ---
@app.route("/attendance/mark", methods=["POST"])
def mark_attendance():
    if "user" not in session:
        return redirect("/")

    student_id = request.form.get("student_id")
    date = request.form.get("date")
    status = request.form.get("status")

    conn = get_db()
    cur = conn.cursor(dictionary=True)


    # 🔒 DUPLICATE CHECK (THIS IS YOUR CODE)
    cur.execute("""
        SELECT id FROM attendance
        WHERE student_id = %s AND date = %s
    """, (student_id, date))

    if cur.fetchone():
        flash("Attendance already marked for today", "warning")
        return redirect("/attendance")

    # ✅ INSERT ONLY IF NOT DUPLICATE
    cur.execute("""
        INSERT INTO attendance (student_id, date, status)
        VALUES (%s, %s, %s)
    """, (student_id, date, status))

    mysql.connection.commit()
    cur.close()
    conn.close()

    flash("Attendance marked successfully", "success")
    return redirect("/attendance")

# --- 9) Bulk attendance with duplicate check ---
@app.route("/attendance/bulk", methods=["POST"])
def bulk_attendance():
    if "user" not in session:
        return redirect("/")

    date = request.form.get("date")
    class_id = request.form.get("class_id")
    student_ids = request.form.getlist("student_ids")

    if not class_id:
        flash("Please select a class", "warning")
        return redirect("/attendance")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    inserted = 0
    updated = 0

    for sid in student_ids:
        status = request.form.get(f"status_{sid}")

        cur.execute("""
            SELECT id FROM attendance
            WHERE student_id=%s AND class_id=%s AND date=%s
        """, (sid, class_id, date))

        if cur.fetchone():
            cur.execute("""
                UPDATE attendance
                SET status=%s
                WHERE student_id=%s AND class_id=%s AND date=%s
            """, (status, sid, class_id, date))
            updated += 1
        else:
            cur.execute("""
                INSERT INTO attendance (student_id, class_id, date, status)
                VALUES (%s, %s, %s, %s)
            """, (sid, class_id, date, status))
            inserted += 1

        from datetime import date

        LOCK_DAYS = 3

        attendance_date = datetime.strptime(date, "%Y-%m-%d").date()
        if (datetime.today().date() - attendance_date).days > LOCK_DAYS:
            flash("Attendance locked for this date", "danger")
            return redirect("/attendance")


    conn.commit()
    cur.close()
    conn.close()

    flash(f"{inserted} added, {updated} updated", "success")
    return redirect("/attendance")

# --- 10) Edit attendance record ---
@app.route("/attendance/edit/<int:id>", methods=["GET", "POST"])
def edit_attendance(id):
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    if request.method == "POST":
        status = request.form.get("status")
        cur.execute("UPDATE attendance SET status=%s WHERE id=%s", (status, id))
        conn.commit()
        cur.close()
        conn.close()
        flash("Attendance updated", "success")
        return redirect("/attendance/history")

    cur.execute("""
        SELECT a.id, s.name, a.status
        FROM attendance a
        JOIN students s ON s.id=a.student_id
        WHERE a.id=%s
    """, (id,))
    record = cur.fetchone()

    cur.close()
    conn.close()

    return render_template("attendance_edit.html", record=record)

@app.route("/parent/attendance")
def parent_attendance():
    if "user" not in session:
        return redirect("/login")

    if session.get("role") != "parent":
        abort(403)

    students = get_parent_students(session["user"])
    if not students:
        flash("No student linked to this parent.")
        return redirect("/parent/dashboard")

    student_ids = [s["id"] for s in students]
    placeholders = ",".join(["%s"] * len(student_ids))

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute(f"""
        SELECT
            a.date,
            a.status,
            s.name AS student_name
        FROM attendance a
        JOIN students s ON s.id = a.student_id
        WHERE a.student_id IN ({placeholders})
        ORDER BY a.date DESC
    """, tuple(student_ids))

    attendance = cur.fetchall()
    cur.close()
    conn.close()

    return render_template(
        "parent_attendance.html",
        attendance=attendance
    )
# -------------------------------------------------------------------------



# ---------- REPORT CARD MODULE ----------
@app.route("/marks/entry", methods=["GET", "POST"])
def marks_entry():
    if "user" not in session:
        return redirect("/login")

    if session.get("role") not in ("admin", "teacher"):
        abort(403)

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # Load classes
    cur.execute("SELECT id, name, section FROM classes ORDER BY name, section")
    classes = cur.fetchall()

    class_id = request.args.get("class_id")
    assignment_id = request.args.get("assignment_id")

    students = []
    assignment = None

    if class_id:
        cur.execute("""
            SELECT id, name
            FROM students
            WHERE class_id=%s
            ORDER BY name
        """, (class_id,))
        students = cur.fetchall()

        cur.execute("""
            SELECT id, title
            FROM assignments
            WHERE class_id=%s
        """, (class_id,))
        assignments = cur.fetchall()
    else:
        assignments = []

    if assignment_id:
        cur.execute("""
            SELECT id, title
            FROM assignments
            WHERE id=%s
        """, (assignment_id,))
        assignment = cur.fetchone()

    # -------- SAVE MARKS --------
    if request.method == "POST":
        assignment_id = request.form.get("assignment_id")

        for key, value in request.form.items():
            if key.startswith("marks_"):
                student_id = key.replace("marks_", "")
                marks = value or None
                remarks = request.form.get(f"remarks_{student_id}", "")

                cur.execute("""
                    INSERT INTO assignment_submissions
                    (assignment_id, student_id, marks, remarks)
                    VALUES (%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                        marks=VALUES(marks),
                        remarks=VALUES(remarks)
                """, (assignment_id, student_id, marks, remarks))

        conn.commit()
        flash("Marks saved successfully ✅")
        return redirect(request.url)

    cur.close()
    conn.close()

    return render_template(
        "marks_entry.html",
        classes=classes,
        assignments=assignments,
        students=students,
        class_id=class_id,
        assignment=assignment
    )

@app.route("/reports")
def reports():
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT s.id, s.name, c.name AS class_name, c.section
        FROM students s
        LEFT JOIN classes c ON c.id = s.class_id
        ORDER BY s.name
    """)
    students = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("reports.html", students=students)

@app.route("/reports/students")
def reports_students():
    if "user" not in session:
        return redirect("/login")

    # Allow admin & teacher
    if session.get("role") not in ("admin", "teacher"):
        abort(403)

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT s.id, s.name, c.name AS class_name, c.section
        FROM students s
        LEFT JOIN classes c ON c.id = s.class_id
        ORDER BY c.name, c.section, s.name
    """)
    students = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "reports_students.html",
        students=students
    )

@app.route("/report-card/full/<int:student_id>")
def report_card_full(student_id):
    if "user" not in session:
        return redirect("/login")

    role = session.get("role")

    # 🔐 SECURITY
    if role == "student" and session.get("student_id") != student_id:
        abort(403)

    if role == "parent":
        students = get_parent_students(session["user"])
        allowed_ids = [s["id"] for s in students]
        if student_id not in allowed_ids:
            abort(403)

    # ✅ TERM / EXAM
    term = request.args.get("term", "Term 1")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # ---------------- STUDENT INFO ----------------
    cur.execute("""
        SELECT s.id, s.name, c.name AS class_name, c.section
        FROM students s
        LEFT JOIN classes c ON c.id = s.class_id
        WHERE s.id = %s
    """, (student_id,))
    student = cur.fetchone()

    if not student:
        cur.close()
        conn.close()
        abort(404)

    # ---------------- MARKS (TERM-WISE) ----------------
    cur.execute("""
        SELECT subject, marks, max_marks
        FROM marks
        WHERE student_id = %s
          AND exam = %s
    """, (student_id, term))
    results = cur.fetchall()

    # ---------------- ATTENDANCE SUMMARY ----------------
    cur.execute("""
        SELECT status, COUNT(*) AS cnt
        FROM attendance
        WHERE student_id = %s
        GROUP BY status
    """, (student_id,))
    attendance = cur.fetchall()

    cur.close()
    conn.close()

    # ---------------- CALCULATIONS ----------------
    total_marks = sum(r["marks"] for r in results if r["marks"] is not None)
    max_marks = sum(r["max_marks"] for r in results if r["max_marks"] is not None)
    percentage = (total_marks / max_marks * 100) if max_marks else 0

    if percentage >= 90:
        grade = "A+"
    elif percentage >= 75:
        grade = "A"
    elif percentage >= 60:
        grade = "B"
    elif percentage >= 40:
        grade = "C"
    else:
        grade = "F"

    # ---------------- PDF ----------------
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    margin = 20 * mm
    x = margin
    y = height - margin

    p.setFont("Helvetica-Bold", 18)
    p.drawCentredString(width / 2, y, "School Report Card")
    y -= 20
    p.setFont("Helvetica", 12)
    p.drawCentredString(width / 2, y, term)
    p.line(margin, y - 10, width - margin, y - 10)

    # Student info
    y -= 40
    p.setFont("Helvetica", 11)
    p.drawString(x, y, f"Name: {student['name']}")
    y -= 15
    p.drawString(x, y, f"Class: {student['class_name']} {student['section']}")

    # Marks
    y -= 30
    p.setFont("Helvetica-Bold", 12)
    p.drawString(x, y, "Academic Performance")
    y -= 18

    p.setFont("Helvetica", 10)
    for r in results:
        p.drawString(x + 10, y, r["subject"])
        p.drawRightString(
            width - margin,
            y,
            f"{r['marks']} / {r['max_marks']}"
        )
        y -= 14

        if y < 120:
            p.showPage()
            y = height - margin

    # Summary
    y -= 20
    p.setFont("Helvetica-Bold", 12)
    p.drawString(x, y, "Result Summary")
    y -= 16
    p.setFont("Helvetica", 10)
    p.drawString(x + 10, y, f"Total Marks: {total_marks} / {max_marks}")
    y -= 14
    p.drawString(x + 10, y, f"Percentage: {percentage:.2f}%")
    y -= 14
    p.drawString(x + 10, y, f"Grade: {grade}")

    p.showPage()
    p.save()
    buffer.seek(0)

    safe_name = student["name"].replace(" ", "_")

    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={
            "Content-Disposition":
            f"attachment; filename=report_card_{safe_name}_{term}.pdf"
        }
    )

@app.route("/reports/<int:student_id>")
def reports_student(student_id):
    return redirect(url_for("report_card_full", student_id=student_id))

@app.route("/marks", methods=["GET", "POST"])
def marks_page():   # 👈 different name
    if "user" not in session or session.get("role") != "teacher":
        abort(403)

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT id, name, section FROM classes ORDER BY name, section")
    classes = cur.fetchall()

    students = []
    class_id = request.args.get("class_id")
    exam = request.args.get("exam", "Term 1")

    if class_id:
        cur.execute("""
            SELECT id, name
            FROM students
            WHERE class_id = %s
            ORDER BY name
        """, (class_id,))
        students = cur.fetchall()

    if request.method == "POST":
        student_id = request.form["student_id"]
        subject = request.form["subject"]
        marks = request.form["marks"]
        max_marks = request.form.get("max_marks", 100)
        exam = request.form["exam"]

        cur.execute("""
            INSERT INTO marks (student_id, subject, marks, max_marks, exam)
            VALUES (%s, %s, %s, %s, %s)
        """, (student_id, subject, marks, max_marks, exam))

        conn.commit()
        flash("Marks saved successfully ✅")

    cur.close()
    conn.close()

    return render_template(
        "marks_entry.html",
        classes=classes,
        students=students,
        class_selected=class_id,
        exam=exam
    )
# -------------------------------------------------------------------------



# ---------- FEES MODULE ----------
# --- 1) fees list with filters ---
@app.route("/fees")
def fees_list():
    if "user" not in session:
        return redirect("/")

    # filters
    class_filter = request.args.get("class", "").strip()
    status_filter = request.args.get("status", "").strip()
    from_date = request.args.get("from", "").strip()
    to_date = request.args.get("to", "").strip()

    where = []
    params = []

    if class_filter:
        where.append("c.id = %s")
        params.append(class_filter)

    if status_filter:
        where.append("f.status = %s")
        params.append(status_filter)

    if from_date:
        where.append("f.created_at >= %s")
        params.append(from_date + " 00:00:00")

    if to_date:
        where.append("f.created_at <= %s")
        params.append(to_date + " 23:59:59")

    sql = """
        SELECT
            f.id,
            f.student_id,
            s.name AS student_name,
            c.name AS class_name,
            c.section,
            f.amount,
            f.status,
            f.paid_on,
            f.note,
            f.created_at
        FROM fees f
        LEFT JOIN students s ON s.id = f.student_id
        LEFT JOIN classes c ON c.id = s.class_id
    """

    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += " ORDER BY f.created_at DESC"

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # class dropdown (from classes table, NOT students)
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, name, section
        FROM classes
        ORDER BY name, section
    """)
    classes = cur.fetchall()
    cur.close()
    conn.close()

    from datetime import date
    return render_template(
        "fees.html",
        fees=rows,
        classes=classes,
        date=date.today(),
        class_filter=class_filter,
        status_filter=status_filter,
        from_date=from_date,
        to_date=to_date
    )

# --- 1) fees dashboard ---
@app.route("/fees/dashboard")
def fees_dashboard():
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT COUNT(DISTINCT student_id) AS total_students FROM fees")
    total_students = cur.fetchone()["total_students"]

    cur.execute("SELECT COALESCE(SUM(amount),0) AS total_collected FROM fees WHERE status='paid'")
    total_collected = cur.fetchone()["total_collected"]

    cur.execute("SELECT COALESCE(SUM(amount),0) AS total_pending FROM fees WHERE status='unpaid'")
    total_pending = cur.fetchone()["total_pending"]

    cur.execute("SELECT COUNT(*) AS pending_records FROM fees WHERE status='unpaid'")
    pending_records = cur.fetchone()["pending_records"]

    cur.close()
    conn.close()

    stats = {
        "total_students": total_students,
        "total_collected": total_collected,
        "total_pending": total_pending,
        "pending_records": pending_records
    }

    return render_template("fees_dashboard.html", stats=stats)

# --- 2) outstanding report: unpaid grouped by class ---
@app.route("/fees/outstanding")
def fees_outstanding():
    if "user" not in session:
        return redirect("/")
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    # group unpaid by class and student
    cur.execute("""
        SELECT s.class as student_class, s.id as student_id, s.name as student_name,
               SUM(f.amount) as total_due, COUNT(f.id) as invoices
        FROM fees f
        JOIN students s ON s.id = f.student_id
        WHERE f.status = 'unpaid'
        GROUP BY s.class, s.id, s.name
        ORDER BY s.class, s.name
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("fees_outstanding.html", rows=rows)

# --- 3) fees due ---
@app.route("/fees/dues")
def fees_dues():
    if "user" not in session:
        return redirect("/")

    cls = request.args.get("class")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    sql = """
        SELECT
            s.id,
            s.name AS student_name,
            c.name AS class_name,
            SUM(f.amount) AS due_amount
        FROM fees f
        JOIN students s ON s.id = f.student_id
        LEFT JOIN classes c ON s.class_id = c.id
        WHERE f.status = 'unpaid'
    """
    params = []

    if cls:
        sql += " AND c.name = %s"
        params.append(cls)

    sql += """
        GROUP BY s.id, s.name, c.name
        HAVING due_amount > 0
        ORDER BY c.name, s.name
    """

    cur.execute(sql, params)
    dues = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("fees_dues.html", dues=dues)

# --- 4) parent fees view ---
@app.route("/parent/fees")
def parent_fees():
    if "user" not in session:
        return redirect("/login")

    if session.get("role") != "parent":
        abort(403)

    # 🔒 derive linked students
    students = get_parent_students(session["user"])
    if not students:
        flash("No student linked to this parent.")
        return redirect("/parent/dashboard")

    student_ids = [s["id"] for s in students]
    placeholders = ",".join(["%s"] * len(student_ids))

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # detailed fee records
    cur.execute(f"""
        SELECT
            s.name AS student_name,
            f.amount,
            f.status,
            f.due_date,
            f.created_at
        FROM fees f
        JOIN students s ON s.id = f.student_id
        WHERE f.student_id IN ({placeholders})
        ORDER BY f.due_date DESC
    """, tuple(student_ids))

    fees = cur.fetchall()

    # summary (total due)
    cur.execute(f"""
        SELECT
            s.name AS student_name,
            SUM(f.amount) AS total_due
        FROM fees f
        JOIN students s ON s.id = f.student_id
        WHERE f.student_id IN ({placeholders})
          AND f.status = 'unpaid'
        GROUP BY s.id
    """, tuple(student_ids))

    dues = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "parent_fees.html",
        fees=fees,
        dues=dues
    )

# --- 5) fees reports ---
@app.route("/fees/reports")
def fees_reports():
    if "user" not in session:
        return redirect("/")

    cls = request.args.get("class")
    month = request.args.get("month")  # YYYY-MM

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    where = "WHERE 1=1"
    params = []

    if cls:
        where += " AND s.class = %s"
        params.append(cls)

    if month:
        where += " AND DATE_FORMAT(f.created_at, '%Y-%m') = %s"
        params.append(month)

    # Records table
    cur.execute("""
        SELECT
            f.id,
            s.name AS student_name,
            c.name AS class_name,
            f.amount,
            f.status,
            f.due_date,
            f.created_at
        FROM fees f
        JOIN students s ON f.student_id = s.id
        LEFT JOIN classes c ON s.class_id = c.id
        ORDER BY f.created_at DESC
    """)

    records = cur.fetchall()

    # Summary
    cur.execute(f"""
        SELECT
            COALESCE(SUM(CASE WHEN f.status='paid' THEN f.amount ELSE 0 END), 0) AS total_paid,
            COALESCE(SUM(CASE WHEN f.status='unpaid' THEN f.amount ELSE 0 END), 0) AS total_unpaid,
            COUNT(*) AS total_records
        FROM fees f
        JOIN students s ON s.id = f.student_id
        {where}
    """, params)

    summary = cur.fetchone()

    cur.close()
    conn.close()

    # SAFETY: summary is ALWAYS defined
    if not summary:
        summary = {
            "total_paid": 0,
            "total_unpaid": 0,
            "total_records": 0
        }

    return render_template(
        "fees_reports.html",
        records=records,
        summary=summary
    )

# --- 6) fees export ---
@app.route("/fees/export")
def fees_export():
    if "user" not in session:
        return redirect("/")

    status = request.args.get("status")

    conn = get_db()
    cur = conn.cursor()

    sql = """
        SELECT s.name, s.class, f.amount, f.status, f.created_at
        FROM fees f
        JOIN students s ON s.id=f.student_id
    """
    params = []

    if status:
        sql += " WHERE f.status=%s"
        params.append(status)

    cur.execute(sql, params)
    rows = cur.fetchall()

    cur.close()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student", "Class", "Amount", "Status", "Date"])
    writer.writerows(rows)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=fees_export.csv"}
    )

# --- 7) PDF receipt for a paid fee ---
@app.route("/fees/receipt/<int:fee_id>")
def fees_receipt(fee_id):
    if "user" not in session:
        return redirect("/")
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT f.id, f.student_id, s.name as student_name, s.class as student_class,
            f.amount, f.status, f.paid_on, f.note, f.created_at
        FROM fees f
        LEFT JOIN students s ON s.id = f.student_id
        # ...

        WHERE f.id = %s
    """, (fee_id,))
    r = cur.fetchone()
    cur.close()
    conn.close()

    if not r:
        flash("Fee not found.")
        return redirect(url_for("fees_list"))
    if r["status"] != "paid":
        flash("Receipt available only for paid fees.")
        return redirect(url_for("fees_list"))

    # require reportlab
    if reportlab is None:
        flash("PDF generation library not installed. Run: pip install reportlab")
        return redirect(url_for("fees_list"))

    # create PDF in memory
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Simple receipt layout
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, height - 80, "School App — Fee Receipt")
    p.setFont("Helvetica", 11)
    p.drawString(50, height - 110, f"Receipt ID: {r['id']}")
    p.drawString(50, height - 130, f"Student: {r.get('student_name') or '-'} (ID: {r.get('student_id') or '-'})")
    p.drawString(50, height - 150, f"Class: {r.get('student_class') or '-'}")
    p.drawString(50, height - 170, f"Amount Paid: {r.get('amount')}")
    p.drawString(50, height - 190, f"Paid On: {r.get('paid_on') or r.get('created_at')}")
    p.drawString(50, height - 210, f"Note: {r.get('note') or ''}")
    p.drawString(50, height - 250, "Thank you for your payment.")
    p.showPage()
    p.save()
    buffer.seek(0)

    filename = f"receipt_fee_{fee_id}.pdf"
    return Response(buffer.getvalue(), mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})

# --- 8) Email reminders (outline + send route) ---
def send_email(to_email: str, subject: str, body: str):
    """
    Simple SMTP sender using environment variables:
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
    For production, use a proper email service and secure storage for credentials.
    """
    SMTP_HOST = os.environ.get("SMTP_HOST")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER")
    SMTP_PASS = os.environ.get("SMTP_PASS")
    SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)

    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        raise RuntimeError("SMTP not configured. Set SMTP_HOST/SMTP_USER/SMTP_PASS env vars.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)

@app.route("/fees/send_reminders", methods=["POST"])
def fees_send_reminders():
    """
    Send unpaid reminders for a class (or all). POST form fields:
      class (optional) — send reminders for this class only
    This will attempt to send one email per student with unpaid fees.
    """
    if "user" not in session:
        return redirect("/")

    cls = request.form.get("class", "").strip()  # optional

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    sql = """
        SELECT s.id as student_id, s.name as student_name, s.email, SUM(f.amount) as total_due
        FROM fees f
        JOIN students s ON s.id = f.student_id
        WHERE f.status = 'unpaid'
    """
    params = []
    if cls:
        sql += " AND s.class = %s"
        params.append(cls)
    sql += " GROUP BY s.id, s.name, s.email HAVING total_due > 0"

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    sent = 0
    failed = []
    for r in rows:
        email = r.get("email")
        if not email:
            failed.append((r.get("student_id"), "no email"))
            continue
        body = f"Dear {r.get('student_name')},\n\nOur records show outstanding fees of {r.get('total_due')}. Please pay at your earliest convenience.\n\nThanks."
        subject = "Fee reminder — outstanding payment"
        try:
            send_email(email, subject, body)
            sent += 1
        except Exception as e:
            failed.append((r.get("student_id"), str(e)))

    flash(f"Reminders sent: {sent}. Failed: {len(failed)}.")
    return redirect(url_for("fees_list"))

# --- 9) fees add ---
@app.route("/fees/add", methods=["GET", "POST"])
def add_fee():
    if "user" not in session:
        return redirect("/")
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    # load students for dropdown
    cur.execute("""
        SELECT 
            s.id,
            s.name,
            c.name AS class_name
        FROM students s
        LEFT JOIN classes c ON s.class_id = c.id
        ORDER BY s.name
    """)

    students = cur.fetchall()

    if request.method == "POST":
        student_id = request.form.get("student_id") or None
        amount_raw = request.form.get("amount", "").strip()
        note = request.form.get("note", "").strip()

        # sanitize common formatting (commas, currency symbols, spaces)
        cleaned = amount_raw.replace(",", "").replace(" ", "").replace("₹", "").replace("$", "")
        if cleaned == "":
            flash("Amount is required.")
            cur.close(); conn.close()
            return redirect(url_for("add_fee"))

        # parse decimal safely
        from decimal import Decimal, InvalidOperation
        try:
            # allow values like "1000" or "1000.50"
            amount = Decimal(cleaned)
            if amount < 0:
                raise InvalidOperation("negative")
            # round to 2 decimal places for DB storage
            amount = amount.quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError) as e:
            flash("Invalid amount format. Enter a positive number, e.g. 1000 or 1000.50")
            cur.close(); conn.close()
            return redirect(url_for("add_fee"))

        status = request.form.get("status", "unpaid")
        paid_on = request.form.get("paid_on") if status == "paid" else None

        cur2 = conn.cursor()
        cur2.execute(
            "INSERT INTO fees (student_id, amount, status, paid_on, note, created_at) VALUES (%s,%s,%s,%s,%s,NOW())",
            (student_id, str(amount), status, paid_on, note)
        )
        conn.commit()
        cur2.close()
        flash("Fee record added.")
        cur.close()
        conn.close()
        return redirect(url_for("fees_list"))

        student_id = request.form.get("student_id") or None
        amount_raw = request.form.get("amount", "0").strip()
        note = request.form.get("note", "").strip()
        try:
            amount = Decimal(amount_raw)
        except Exception:
            flash("Invalid amount.")
            cur.close()
            conn.close()
            return redirect(url_for("add_fee"))

        status = request.form.get("status", "unpaid")
        paid_on = request.form.get("paid_on") if status == "paid" else None

        cur2 = conn.cursor()
        cur2.execute(
            "INSERT INTO fees (student_id, amount, status, paid_on, note, created_at) VALUES (%s,%s,%s,%s,%s,NOW())",
            (student_id, str(amount), status, paid_on, note)
        )
        conn.commit()
        cur2.close()
        flash("Fee record added.")
        cur.close()
        conn.close()
        return redirect(url_for("fees_list"))

    cur.close()
    conn.close()
    return render_template("add_fee.html", students=students)

# --- 10) fees mark_paid ---
@app.route("/fees/mark_paid/<int:fee_id>", methods=["POST"])
def fees_mark_paid(fee_id):
    if "user" not in session:
        return redirect("/")
    paid_on = request.form.get("paid_on", date.today().isoformat())
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE fees SET status=%s, paid_on=%s WHERE id=%s", ("paid", paid_on, fee_id))
        conn.commit()
        flash("Marked as paid.")
    except Exception as e:
        conn.rollback()
        print("fees mark paid error:", repr(e))
        flash("Failed to mark paid.")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("fees_list"))

# --- 11) fees delete ---
@app.route("/fees/delete/<int:fee_id>", methods=["POST"])
def fees_delete(fee_id):
    if "user" not in session:
        return redirect("/")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM fees WHERE id=%s", (fee_id,))
        conn.commit()
        flash("Fee record deleted.")
    except Exception as e:
        conn.rollback()
        print("fees delete error:", repr(e))
        flash("Failed to delete.")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("fees_list"))

# --- 12) fees receipt ---
@app.route("/fees/receipt_full/<int:fee_id>")
def fees_receipt_full(fee_id):
    if "user" not in session:
        return redirect("/")

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT f.id as fee_id, f.student_id, f.amount, f.status, f.paid_on, f.note, f.created_at,
               s.name as student_name, s.parent_name, s.class as student_class, s.id as student_db_id
        FROM fees f
        LEFT JOIN students s ON s.id = f.student_id
        WHERE f.id = %s
    """, (fee_id,))
    fee = cur.fetchone()
    if not fee:
        cur.close(); conn.close()
        flash("Fee record not found.")
        return redirect(url_for("fees_list"))

    student_id = fee["student_id"]

    # totals for this student
    cur.execute("SELECT COALESCE(SUM(amount),0) AS total_paid FROM fees WHERE student_id=%s AND status='paid'", (student_id,))
    tp = cur.fetchone()
    total_paid = float(tp["total_paid"] or 0)

    cur.execute("SELECT COALESCE(SUM(amount),0) AS total_unpaid FROM fees WHERE student_id=%s AND status='unpaid'", (student_id,))
    tu = cur.fetchone()
    total_unpaid = float(tu["total_unpaid"] or 0)

    paid_now = float(fee["amount"] or 0)

    cur.close()
    conn.close()

    # include this payment in display total if needed
    if fee.get("status") == "paid":
        display_total_paid = total_paid
    else:
        display_total_paid = total_paid + paid_now

    remaining_after_payment = max(0.0, total_unpaid - paid_now)

    # PDF
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    margin = 20 * mm
    x = margin
    y = height - margin

    # header: school info
    school_name = os.environ.get("SCHOOL_NAME", "Shree Manas International Public School")
    p.setFont("Helvetica-Bold", 18)
    p.drawString(x, y, school_name)
    p.setFont("Helvetica", 10)
    p.drawString(x, y - 16, "Address: " + os.environ.get(
        "SCHOOL_ADDRESS",
        "118, Sector 8 Main Rd, Sector 8, Raipur, Chhattisgarh 492014"
    ))
    p.drawString(x, y - 30, "Phone: " + os.environ.get("SCHOOL_PHONE", "+91-7000225026"))

    # receipt title + date
    p.setFont("Helvetica-Bold", 14)
    p.drawString(width - margin - 160, y, "                    FEE RECEIPT")
    p.setFont("Helvetica", 10)
    p.drawString(width - margin - 160, y - 16, f"Receipt ID: {fee['fee_id']}")

    paid_on_val = fee.get("paid_on") or fee.get("created_at") or datetime.utcnow().date()
    if isinstance(paid_on_val, datetime):
        paid_on_str = paid_on_val.strftime("%Y-%m-%d")
    else:
        paid_on_str = str(paid_on_val) if paid_on_val else date.today().isoformat()
    p.drawString(width - margin - 160, y - 30, "Date: " + paid_on_str)

    # student details
    y -= 70
    p.setFont("Helvetica-Bold", 12)
    p.drawString(x, y, "Student Details")
    p.setFont("Helvetica", 10)
    y -= 16
    p.drawString(x, y, f"Student: {fee.get('student_name') or '-'} (ID: {fee.get('student_db_id') or '-'})")
    y -= 14
    p.drawString(x, y, f"Parent: {fee.get('parent_name') or '-'}")
    y -= 14
    p.drawString(x, y, f"Class: {fee.get('student_class') or '-'}")

    # payment table
    y -= 28
    p.setFont("Helvetica-Bold", 12)
    p.drawString(x, y, "Payment Details")
    y -= 16

    table_x = x
    table_w = width - 2 * margin
    row_h = 16

    p.setFont("Helvetica-Bold", 10)
    p.drawString(table_x + 4, y, "Particulars")
    p.drawString(table_x + table_w/2, y, "Amount (INR)")
    y -= row_h

    p.setFont("Helvetica", 10)
    p.drawString(table_x + 4, y, "Total paid (all records)")
    p.drawString(table_x + table_w/2, y, f"{total_paid:.2f}")
    y -= row_h

    p.drawString(table_x + 4, y, "Paid now")
    p.drawString(table_x + table_w/2, y, f"{paid_now:.2f}")
    y -= row_h

    p.drawString(table_x + 4, y, "Remaining before payment")
    p.drawString(table_x + table_w/2, y, f"{total_unpaid:.2f}")
    y -= row_h

    p.setFont("Helvetica-Bold", 11)
    p.drawString(table_x + 4, y, "TOTAL PAID (including now)")
    p.drawString(table_x + table_w/2, y, f"{display_total_paid:.2f}")
    y -= (row_h + 6)

    # note
    p.setFont("Helvetica", 9)
    p.drawString(table_x + 4, y, "Note: " + (fee.get("note") or ""))
    y -= (row_h + 10)

    # remaining box
    box_x = table_x
    box_w = 170 * mm
    box_h = 30 * mm
    p.setStrokeColor(colors.gray)
    p.rect(box_x, y - box_h + 8, box_w, box_h, stroke=1, fill=0)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(box_x + 6, y - 12, f"Remaining balance (after this payment): {remaining_after_payment:.2f}")
    p.setFont("Helvetica", 9)
    p.drawString(box_x + 6, y - 26, "Please clear dues at the school office.")

    # signature area
    sig_x = table_x + table_w - 80*mm
    sig_y = y - 6
    p.setFont("Helvetica", 10)
    p.drawString(sig_x, sig_y, "Received by:")
    p.line(sig_x, sig_y - 18, sig_x + 70*mm, sig_y - 18)
    p.drawString(sig_x, sig_y - 30, "Authorized signatory")

    sig_img_path = os.path.join(BASE_DIR, "static", "signature.png")
    if os.path.exists(sig_img_path):
        try:
            p.drawImage(sig_img_path, sig_x, sig_y - 8 - 8,
                        width=50*mm, preserveAspectRatio=True, mask='auto')
        except Exception as e:
            print("signature embed failed:", e)

    # footer
    p.setFont("Helvetica-Oblique", 9)
    p.drawString(margin, 30, "Thank you. This is a computer generated receipt and does not require a physical stamp.")
    p.drawString(margin, 16, f"Issued on: {date.today().isoformat()}")

    p.showPage()
    p.save()
    buffer.seek(0)

    filename = f"receipt_full_fee_{fee_id}.pdf"
    return Response(buffer.getvalue(), mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})

    if "user" not in session:
        return redirect("/")

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT f.id as fee_id, f.student_id, f.amount, f.status, f.paid_on, f.note, f.created_at,
               s.name as student_name, s.parent_name, s.class as student_class, s.id as student_db_id
        FROM fees f
        LEFT JOIN students s ON s.id = f.student_id
        WHERE f.id = %s
    """, (fee_id,))
    fee = cur.fetchone()
    if not fee:
        cur.close(); conn.close()
        flash("Fee record not found.")
        return redirect(url_for("fees_list"))

    student_id = fee["student_id"]

    # totals for this student
    cur.execute("SELECT COALESCE(SUM(amount),0) AS total_paid FROM fees WHERE student_id=%s AND status='paid'", (student_id,))
    tp = cur.fetchone()
    total_paid = float(tp["total_paid"] or 0)

    cur.execute("SELECT COALESCE(SUM(amount),0) AS total_unpaid FROM fees WHERE student_id=%s AND status='unpaid'", (student_id,))
    tu = cur.fetchone()
    total_unpaid = float(tu["total_unpaid"] or 0)

    paid_now = float(fee["amount"] or 0)

    cur.close()
    conn.close()

    # display totals – include this payment if needed
    if fee.get("status") == "paid":
        display_total_paid = total_paid
    else:
        display_total_paid = total_paid + paid_now

    remaining_after_payment = max(0.0, total_unpaid - paid_now)

    # PDF
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    margin = 20 * mm
    x = margin
    y = height - margin

    # header: school info
    school_name = os.environ.get("SCHOOL_NAME", "Shree Manas International Public School")
    p.setFont("Helvetica-Bold", 18)
    p.drawString(x, y, school_name)
    p.setFont("Helvetica", 10)
    p.drawString(x, y - 16, "Address: " + os.environ.get(
        "SCHOOL_ADDRESS",
        "118, Sector 8 Main Rd, Sector 8, Raipur, Chhattisgarh 492014"
    ))
    p.drawString(x, y - 30, "Phone: " + os.environ.get("SCHOOL_PHONE", "+91-7000225026"))

    # receipt title + date
    p.setFont("Helvetica-Bold", 14)
    p.drawString(width - margin - 160, y, "FEE RECEIPT")
    p.setFont("Helvetica", 10)
    p.drawString(width - margin - 160, y - 16, f"Receipt ID: {fee['fee_id']}")

    paid_on_val = fee.get("paid_on") or fee.get("created_at") or datetime.utcnow().date()
    if isinstance(paid_on_val, datetime):
        paid_on_str = paid_on_val.strftime("%Y-%m-%d")
    else:
        paid_on_str = str(paid_on_val) if paid_on_val else date.today().isoformat()
    p.drawString(width - margin - 160, y - 30, "Date: " + paid_on_str)

    # student details
    y -= 70
    p.setFont("Helvetica-Bold", 12)
    p.drawString(x, y, "Student Details")
    p.setFont("Helvetica", 10)
    y -= 16
    p.drawString(x, y, f"Student: {fee.get('student_name') or '-'} (ID: {fee.get('student_db_id') or '-'})")
    y -= 14
    p.drawString(x, y, f"Parent: {fee.get('parent_name') or '-'}")
    y -= 14
    p.drawString(x, y, f"Class: {fee.get('student_class') or '-'}")

    # payment table
    y -= 28
    p.setFont("Helvetica-Bold", 12)
    p.drawString(x, y, "Payment Details")
    y -= 16

    table_x = x
    table_w = width - 2 * margin
    row_h = 16

    p.setFont("Helvetica-Bold", 10)
    p.drawString(table_x + 4, y, "Particulars")
    p.drawString(table_x + table_w/2, y, "Amount (INR)")
    y -= row_h

    p.setFont("Helvetica", 10)
    p.drawString(table_x + 4, y, "Total paid (all records)")
    p.drawString(table_x + table_w/2, y, f"{total_paid:.2f}")
    y -= row_h

    p.drawString(table_x + 4, y, "Paid now")
    p.drawString(table_x + table_w/2, y, f"{paid_now:.2f}")
    y -= row_h

    p.drawString(table_x + 4, y, "Remaining before payment")
    p.drawString(table_x + table_w/2, y, f"{total_unpaid:.2f}")
    y -= row_h

    p.setFont("Helvetica-Bold", 11)
    p.drawString(table_x + 4, y, "TOTAL PAID (including now)")
    p.drawString(table_x + table_w/2, y, f"{display_total_paid:.2f}")
    y -= (row_h + 6)

    # note
    p.setFont("Helvetica", 9)
    p.drawString(table_x + 4, y, "Note: " + (fee.get("note") or ""))
    y -= (row_h + 10)

    # remaining box
    box_x = table_x
    box_w = 120 * mm
    box_h = 30 * mm
    p.setStrokeColor(colors.gray)
    p.rect(box_x, y - box_h + 8, box_w, box_h, stroke=1, fill=0)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(box_x + 6, y - 12, f"Remaining balance (after this payment): {remaining_after_payment:.2f}")
    p.setFont("Helvetica", 9)
    p.drawString(box_x + 6, y - 26, "Please clear dues at the school office.")

    # signature area
    sig_x = table_x + table_w - 8*mm
    sig_y = y - 6
    p.setFont("Helvetica", 10)
    p.drawString(sig_x, sig_y, "Received by:")
    p.line(sig_x, sig_y - 18, sig_x + 70*mm, sig_y - 18)
    p.drawString(sig_x, sig_y - 3, "Authorized signatory")

    sig_img_path = os.path.join(BASE_DIR, "static", "signature.png")
    if os.path.exists(sig_img_path):
        try:
            p.drawImage(sig_img_path, sig_x, sig_y - 18 - 40,
                        width=50*mm, preserveAspectRatio=True, mask='auto')
        except Exception as e:
            print("signature embed failed:", e)

    # footer
    p.setFont("Helvetica-Oblique", 9)
    p.drawString(margin, 30, "Thank you. This is a computer generated receipt and does require a physical stamp.")
    p.drawString(margin, 16, f"Issued on: {date.today().isoformat()}")

    p.showPage()
    p.save()
    buffer.seek(0)

    filename = f"reciept_full_fee_{fee_id}.pdf" 
    return Response(buffer.getvalue(), mimetype="application/pdf",
                    headers = {"content-Disposition" : f"attachment; filename={filename}"})
# -------------------------------------------------------------------------



# ---- Run ----
if __name__ == "__main__":
    # debug=True only for local dev
    app.run(host="127.0.0.1", port=5000, debug=True)