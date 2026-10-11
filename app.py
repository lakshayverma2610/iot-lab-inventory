import csv
import io
import os
from datetime import date

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    abort,
    Response,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select, or_, CheckConstraint
from sqlalchemy.exc import IntegrityError


# ==========================================
# APPLICATION CONFIGURATION
# ==========================================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "development-key-change-before-deployment",
)

os.makedirs(app.instance_path, exist_ok=True)

app.config["SQLALCHEMY_DATABASE_URI"] = (
    "sqlite:///"
    + os.path.join(app.instance_path, "lab.db")
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ==========================================
# DATABASE MODELS
# ==========================================

class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    device_code = db.Column(
        db.String(50),
        unique=True,
        nullable=False,
    )

    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(80), nullable=False)

    total_quantity = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

    available_quantity = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

    location = db.Column(
        db.String(120),
        default="IoT Lab",
    )

    __table_args__ = (
        CheckConstraint("total_quantity >= 0"),
        CheckConstraint("available_quantity >= 0"),
        CheckConstraint(
            "available_quantity <= total_quantity"
        ),
    )


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(
        db.String(50),
        unique=True,
        nullable=False,
    )

    name = db.Column(db.String(120), nullable=False)

    department = db.Column(
        db.String(100),
        nullable=False,
    )

    semester = db.Column(
        db.String(30),
        nullable=False,
    )


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(
        db.Integer,
        db.ForeignKey("student.id"),
        nullable=False,
    )

    device_id = db.Column(
        db.Integer,
        db.ForeignKey("device.id"),
        nullable=False,
    )

    quantity = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )

    issue_date = db.Column(
        db.Date,
        nullable=False,
        default=date.today,
    )

    due_date = db.Column(
        db.Date,
        nullable=False,
    )

    return_date = db.Column(
        db.Date,
        nullable=True,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="Issued",
    )

    student = db.relationship("Student")
    device = db.relationship("Device")

    __table_args__ = (
        CheckConstraint("quantity > 0"),
    )


# ==========================================
# DASHBOARD
# ==========================================

@app.route("/")
def dashboard():
    devices = db.session.scalars(
        select(Device)
    ).all()

    total_devices = sum(
        device.total_quantity for device in devices
    )

    available_devices = sum(
        device.available_quantity for device in devices
    )

    issued_devices = (
        total_devices - available_devices
    )

    active_transactions = db.session.scalars(
        select(Transaction).where(
            Transaction.status == "Issued"
        )
    ).all()

    overdue_transactions = [
        transaction
        for transaction in active_transactions
        if transaction.due_date < date.today()
    ]

    low_stock_devices = [
        device
        for device in devices
        if device.available_quantity <= 2
    ]

    recent_transactions = db.session.scalars(
        select(Transaction)
        .order_by(Transaction.id.desc())
        .limit(8)
    ).all()

    return render_template(
        "dashboard.html",
        total_devices=total_devices,
        available_devices=available_devices,
        issued_devices=issued_devices,
        overdue_count=len(overdue_transactions),
        recent_transactions=recent_transactions,
        low_stock_devices=low_stock_devices,
        catalog_count=len(devices),
        active_loans_count=len(active_transactions),
        today=date.today(),
    )


# ==========================================
# DEVICE INVENTORY
# ==========================================

@app.route("/devices", methods=["GET", "POST"])
def devices():
    if request.method == "POST":
        device_code = request.form.get(
            "device_code", ""
        ).strip()

        name = request.form.get(
            "name", ""
        ).strip()

        category = request.form.get(
            "category", ""
        ).strip()

        location = request.form.get(
            "location", "IoT Lab"
        ).strip()

        try:
            quantity = int(
                request.form.get("quantity", "1")
            )
        except ValueError:
            flash(
                "Quantity must be a whole number.",
                "error",
            )
            return redirect(url_for("devices"))

        if not all([device_code, name, category]):
            flash(
                "Please complete all required fields.",
                "error",
            )
            return redirect(url_for("devices"))

        if quantity < 1:
            flash(
                "Quantity must be at least 1.",
                "error",
            )
            return redirect(url_for("devices"))

        device = Device(
            device_code=device_code,
            name=name,
            category=category,
            total_quantity=quantity,
            available_quantity=quantity,
            location=location or "IoT Lab",
        )

        db.session.add(device)

        try:
            db.session.commit()
            flash(
                "Device added successfully!",
                "success",
            )

        except IntegrityError:
            db.session.rollback()
            flash(
                "That device code already exists.",
                "error",
            )

        return redirect(url_for("devices"))

    search = request.args.get(
        "search", ""
    ).strip()

    query = select(Device).order_by(Device.name)

    if search:
        query = query.where(
            or_(
                Device.name.ilike(f"%{search}%"),
                Device.device_code.ilike(
                    f"%{search}%"
                ),
                Device.category.ilike(
                    f"%{search}%"
                ),
            )
        )

    device_list = db.session.scalars(
        query
    ).all()

    return render_template(
        "devices.html",
        devices=device_list,
        search=search,
    )


# ==========================================
# STUDENT REGISTRATION
# ==========================================

@app.route("/students", methods=["GET", "POST"])
def students():
    if request.method == "POST":
        student_id = request.form.get(
            "student_id", ""
        ).strip()

        name = request.form.get(
            "name", ""
        ).strip()

        department = request.form.get(
            "department", ""
        ).strip()

        semester = request.form.get(
            "semester", ""
        ).strip()

        if not all(
            [student_id, name, department, semester]
        ):
            flash(
                "Please complete all student fields.",
                "error",
            )
            return redirect(url_for("students"))

        student = Student(
            student_id=student_id,
            name=name,
            department=department,
            semester=semester,
        )

        db.session.add(student)

        try:
            db.session.commit()
            flash(
                "Student registered successfully!",
                "success",
            )

        except IntegrityError:
            db.session.rollback()
            flash(
                "That student ID already exists.",
                "error",
            )

        return redirect(url_for("students"))

    search = request.args.get(
        "search", ""
    ).strip()

    query = select(Student).order_by(Student.name)

    if search:
        query = query.where(
            or_(
                Student.name.ilike(f"%{search}%"),
                Student.student_id.ilike(
                    f"%{search}%"
                ),
            )
        )

    student_list = db.session.scalars(
        query
    ).all()

    return render_template(
        "students.html",
        students=student_list,
        search=search,
    )


# ==========================================
# ISSUE EQUIPMENT
# ==========================================

@app.route("/issue", methods=["GET", "POST"])
def issue():
    if request.method == "POST":
        try:
            student_id = int(
                request.form.get("student_id", "")
            )

            device_id = int(
                request.form.get("device_id", "")
            )

            quantity = int(
                request.form.get("quantity", "1")
            )

            due_date = date.fromisoformat(
                request.form.get("due_date", "")
            )

        except (ValueError, TypeError):
            flash(
                "Please enter valid transaction details.",
                "error",
            )
            return redirect(url_for("issue"))

        if quantity < 1:
            flash(
                "Quantity must be at least 1.",
                "error",
            )
            return redirect(url_for("issue"))

        if due_date < date.today():
            flash(
                "Due date cannot be in the past.",
                "error",
            )
            return redirect(url_for("issue"))

        student = db.session.get(
            Student, student_id
        )

        device = db.session.get(
            Device, device_id
        )

        if student is None or device is None:
            flash(
                "Please select a valid student and device.",
                "error",
            )
            return redirect(url_for("issue"))

        if device.available_quantity < quantity:
            flash(
                "Not enough equipment is available.",
                "error",
            )
            return redirect(url_for("issue"))

        try:
            device.available_quantity -= quantity

            transaction = Transaction(
                student_id=student.id,
                device_id=device.id,
                quantity=quantity,
                due_date=due_date,
            )

            db.session.add(transaction)
            db.session.commit()

            flash(
                "Equipment issued successfully!",
                "success",
            )

        except Exception:
            db.session.rollback()

            app.logger.exception(
                "Issue transaction failed"
            )

            flash(
                "Could not save the transaction.",
                "error",
            )

        return redirect(url_for("transactions"))

    student_list = db.session.scalars(
        select(Student).order_by(Student.name)
    ).all()

    device_list = db.session.scalars(
        select(Device)
        .where(Device.available_quantity > 0)
        .order_by(Device.name)
    ).all()

    return render_template(
        "issue.html",
        students=student_list,
        devices=device_list,
        today=date.today().isoformat(),
    )


# ==========================================
# TRANSACTION HISTORY
# ==========================================

@app.route("/transactions")
def transactions():
    search = request.args.get(
        "search", ""
    ).strip()

    query = (
        select(Transaction)
        .join(Transaction.student)
        .join(Transaction.device)
        .order_by(Transaction.id.desc())
    )

    if search:
        query = query.where(
            or_(
                Student.name.ilike(
                    f"%{search}%"
                ),
                Student.student_id.ilike(
                    f"%{search}%"
                ),
                Device.name.ilike(
                    f"%{search}%"
                ),
                Device.device_code.ilike(
                    f"%{search}%"
                ),
            )
        )

    transaction_list = db.session.scalars(
        query
    ).all()

    return render_template(
        "transactions.html",
        transactions=transaction_list,
        search=search,
        today=date.today(),
    )


# ==========================================
# RETURN EQUIPMENT
# ==========================================

@app.route(
    "/return/<int:transaction_id>",
    methods=["POST"],
)
def return_device(transaction_id):
    transaction = db.session.get(
        Transaction, transaction_id
    )

    if transaction is None:
        abort(404)

    if transaction.status != "Issued":
        flash(
            "This equipment has already been returned.",
            "error",
        )
        return redirect(url_for("transactions"))

    device = db.session.get(
        Device, transaction.device_id
    )

    if device is None:
        flash(
            "Associated device not found.",
            "error",
        )
        return redirect(url_for("transactions"))

    if (
        device.available_quantity
        + transaction.quantity
        > device.total_quantity
    ):
        flash(
            "The recorded stock is inconsistent. "
            "Contact the administrator.",
            "error",
        )
        return redirect(url_for("transactions"))

    try:
        device.available_quantity += (
            transaction.quantity
        )

        transaction.status = "Returned"
        transaction.return_date = date.today()

        db.session.commit()

        flash(
            "Equipment returned successfully!",
            "success",
        )

    except Exception:
        db.session.rollback()

        app.logger.exception(
            "Return transaction failed"
        )

        flash(
            "Could not save the return.",
            "error",
        )

    return redirect(url_for("transactions"))


# ==========================================
# STUDENT PORTAL & SELF-SERVICE
# ==========================================

@app.route("/student-portal")
def student_portal():
    student_id_param = request.args.get("student_id", "").strip()
    category_param = request.args.get("category", "").strip()
    search = request.args.get("search", "").strip()

    all_students = db.session.scalars(
        select(Student).order_by(Student.name)
    ).all()

    # Hardware devices catalog query
    query = select(Device).order_by(Device.name)
    if category_param:
        query = query.where(Device.category == category_param)
    if search:
        query = query.where(
            or_(
                Device.name.ilike(f"%{search}%"),
                Device.device_code.ilike(f"%{search}%"),
                Device.category.ilike(f"%{search}%"),
            )
        )
    devices = db.session.scalars(query).all()

    # Distinct categories for filter tabs
    all_devices = db.session.scalars(select(Device)).all()
    categories = sorted(list({d.category for d in all_devices}))

    # If student is selected, retrieve their active loans
    selected_student = None
    student_active_loans = []
    if student_id_param:
        try:
            s_id = int(student_id_param)
            selected_student = db.session.get(Student, s_id)
            if selected_student:
                student_active_loans = db.session.scalars(
                    select(Transaction)
                    .join(Transaction.device)
                    .where(
                        Transaction.student_id == selected_student.id,
                        Transaction.status == "Issued",
                    )
                    .order_by(Transaction.due_date.asc())
                ).all()
        except (ValueError, TypeError):
            pass

    return render_template(
        "student_portal.html",
        devices=devices,
        categories=categories,
        current_category=category_param,
        search=search,
        all_students=all_students,
        selected_student=selected_student,
        student_active_loans=student_active_loans,
        today=date.today(),
    )


# ==========================================
# LEGAL & COMPLIANCE
# ==========================================

@app.route("/privacy")
def privacy_policy():
    return render_template("privacy.html")


@app.route("/terms")
def terms_conditions():
    return render_template("terms.html")


# ==========================================
# AUDIT & DATA EXPORT (CSV)
# ==========================================

@app.route("/export/csv/<export_type>")
def export_csv(export_type):
    output = io.StringIO()
    writer = csv.writer(output)

    if export_type == "inventory":
        devices = db.session.scalars(
            select(Device).order_by(Device.name)
        ).all()
        filename = f"iot_lab_inventory_{date.today().isoformat()}.csv"
        writer.writerow([
            "Asset Code",
            "Component Name",
            "Category",
            "Total Quantity",
            "Available Quantity",
            "Issued Quantity",
            "Bench / Storage Location",
        ])
        for d in devices:
            writer.writerow([
                d.device_code,
                d.name,
                d.category,
                d.total_quantity,
                d.available_quantity,
                d.total_quantity - d.available_quantity,
                d.location,
            ])

    elif export_type == "active_loans":
        transactions = db.session.scalars(
            select(Transaction)
            .join(Transaction.student)
            .join(Transaction.device)
            .where(Transaction.status == "Issued")
            .order_by(Transaction.due_date.asc())
        ).all()
        filename = f"iot_lab_active_loans_{date.today().isoformat()}.csv"
        writer.writerow([
            "Ledger ID",
            "Student Roll No",
            "Student Name",
            "Department",
            "Component Code",
            "Component Name",
            "Quantity",
            "Issue Date",
            "Due Date",
            "Is Overdue",
        ])
        for t in transactions:
            is_overdue = "YES" if t.due_date < date.today() else "NO"
            writer.writerow([
                f"TX-{t.id}",
                t.student.student_id,
                t.student.name,
                t.student.department,
                t.device.device_code,
                t.device.name,
                t.quantity,
                t.issue_date.isoformat(),
                t.due_date.isoformat(),
                is_overdue,
            ])

    elif export_type == "all_transactions":
        transactions = db.session.scalars(
            select(Transaction)
            .join(Transaction.student)
            .join(Transaction.device)
            .order_by(Transaction.id.desc())
        ).all()
        filename = f"iot_lab_custody_ledger_{date.today().isoformat()}.csv"
        writer.writerow([
            "Ledger ID",
            "Student Roll No",
            "Student Name",
            "Component Code",
            "Component Name",
            "Quantity",
            "Issue Date",
            "Due Date",
            "Return Date",
            "Status",
        ])
        for t in transactions:
            writer.writerow([
                f"TX-{t.id}",
                t.student.student_id,
                t.student.name,
                t.device.device_code,
                t.device.name,
                t.quantity,
                t.issue_date.isoformat(),
                t.due_date.isoformat(),
                t.return_date.isoformat() if t.return_date else "N/A",
                t.status,
            ])

    else:
        abort(404)

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8",
        },
    )



# ==========================================
# INITIALIZE DATABASE
# ==========================================

with app.app_context():
    db.create_all()


# ==========================================
# START APPLICATION
# ==========================================

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)