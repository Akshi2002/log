from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
import os
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config
import math
from firebase_admin import auth as firebase_auth

# Firebase imports
from firebase_models import FirebaseEmployee, FirebaseAdmin, FirebaseAttendance
from firebase_service import get_firebase_service

app = Flask(__name__)
app.config.from_object(Config)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin_login'

# Initialize Firebase service
firebase_service = get_firebase_service()

@login_manager.user_loader
def load_user(user_id):
    """Load user for Flask-Login"""
    if user_id.startswith("admin-"):
        doc_id = user_id.split("-")[1]
        return FirebaseAdmin.find_by_doc_id(doc_id)
    elif user_id.startswith("employee-"):
        doc_id = user_id.split("-")[1]
        return FirebaseEmployee.find_by_doc_id(doc_id)
    return None

# Geofence functions (same as before)
def haversine_distance_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def is_within_office_geofence(lat, lon):
    if lat is None or lon is None:
        print(f"DEBUG Geofence: Missing coordinates lat={lat}, lon={lon}")
        return False
    try:
        user_lat = float(lat)
        user_lon = float(lon)
        
        # Use the new multi-location system
        is_within, office_name = Config.is_within_office_location(user_lat, user_lon)
        
        if is_within:
            print(f"DEBUG Geofence: user=({user_lat}, {user_lon}) is within {office_name}")
        else:
            print(f"DEBUG Geofence: user=({user_lat}, {user_lon}) is not within any office location")
            # Debug: show distances to all offices
            for office in Config.OFFICE_LOCATIONS:
                distance = haversine_distance_m(user_lat, user_lon, office['latitude'], office['longitude'])
                print(f"  - Distance to {office['name']}: {distance:.2f}m (radius: {office['radius_meters']}m)")
        
        return is_within
    except Exception as e:
        print(f"DEBUG Geofence error: {e} with lat={lat} lon={lon}")
        return False

# Routes
@app.route('/')
def index():
    """Main page - redirects to appropriate login"""
    return render_template('index.html')

@app.route('/employee')
def employee_portal():
    """Employee portal"""
    return render_template('employee_portal.html', 
                         office_locations=Config.OFFICE_LOCATIONS,
                         office_lat=Config.OFFICE_LATITUDE, 
                         office_lng=Config.OFFICE_LONGITUDE, 
                         office_radius=Config.OFFICE_RADIUS_METERS)

@app.route('/employee/login', methods=['GET'])
def employee_login():
    """Employee login functionality"""
    return render_template('employee_login.html', 
                         office_locations=Config.OFFICE_LOCATIONS,
                         office_lat=Config.OFFICE_LATITUDE, 
                         office_lng=Config.OFFICE_LONGITUDE, 
                         office_radius=Config.OFFICE_RADIUS_METERS)

@app.route('/employee/signin', methods=['GET', 'POST'])
@login_required
def employee_signin():
    """Employee sign-in functionality - requires login first"""
    if not isinstance(current_user, FirebaseEmployee):
        return redirect(url_for('employee_login'))
    
    if request.method == 'POST':
        employee_id = current_user.employee_id
        lat = request.form.get('latitude')
        lon = request.form.get('longitude')
        print(f"DEBUG Route: /employee/signin POST lat={lat} lon={lon}")
        
        # Enforce geofence for sign-in
        if not is_within_office_geofence(lat, lon):
            flash('Sign-in denied: You are not within any office location.', 'error')
            return redirect(url_for('employee_dashboard'))
        
        today = datetime.now().date()
        existing_attendance = FirebaseAttendance.find_by_employee_and_date(employee_id, today)
        
        if existing_attendance and existing_attendance.sign_in_time:
            flash('You have already signed in today!', 'error')
            return redirect(url_for('employee_dashboard'))
        
        # Create new attendance record
        if not existing_attendance:
            attendance = FirebaseAttendance({
                'employee_id': employee_id,
                'date': today.strftime('%Y-%m-%d'),
                'sign_in_time': datetime.now(),
                'sign_out_time': None,
                'total_hours': None
            })
        else:
            attendance = existing_attendance
            attendance.sign_in_time = datetime.now()
        
        if attendance.save():
            flash(f'Welcome {current_user.name}! You have successfully signed in at {datetime.now().strftime("%H:%M:%S")}', 'success')
        else:
            flash('Error recording sign-in. Please try again.', 'error')
        
        return redirect(url_for('employee_dashboard'))
    
    return render_template('employee_signin.html', 
                         office_locations=Config.OFFICE_LOCATIONS,
                         office_lat=Config.OFFICE_LATITUDE, 
                         office_lng=Config.OFFICE_LONGITUDE, 
                         office_radius=Config.OFFICE_RADIUS_METERS)

@app.route('/employee/signout', methods=['GET', 'POST'])
@login_required
def employee_signout():
    """Employee sign-out functionality - requires login first"""
    if not isinstance(current_user, FirebaseEmployee):
        return redirect(url_for('employee_login'))
    
    if request.method == 'GET':
        return render_template(
            'employee_signout.html',
            office_locations=Config.OFFICE_LOCATIONS,
            office_lat=Config.OFFICE_LATITUDE,
            office_lng=Config.OFFICE_LONGITUDE,
            office_radius=Config.OFFICE_RADIUS_METERS,
        )

    # POST: perform geofence check and complete sign-out
    lat = request.form.get('latitude')
    lon = request.form.get('longitude')
    print(f"DEBUG Route: /employee/signout POST lat={lat} lon={lon}")
    
    if not is_within_office_geofence(lat, lon):
        flash('Sign-out denied: You are not within any office location.', 'error')
        return redirect(url_for('employee_dashboard'))

    employee_id = current_user.employee_id
    today = datetime.now().date()
    attendance = FirebaseAttendance.find_by_employee_and_date(employee_id, today)

    if not attendance or not attendance.sign_in_time:
        flash('You have not signed in today!', 'error')
        return redirect(url_for('employee_dashboard'))

    if attendance.sign_out_time:
        flash('You have already signed out today!', 'error')
        return redirect(url_for('employee_dashboard'))

    # Calculate working hours
    sign_out_time = datetime.now()
    attendance.sign_out_time = sign_out_time

    sign_in_datetime = attendance.get_sign_in_datetime()
    if sign_in_datetime:
        time_diff = sign_out_time - sign_in_datetime
        total_hours = time_diff.total_seconds() / 3600
        attendance.total_hours = round(total_hours, 2)

        hours = int(total_hours)
        minutes = int((total_hours - hours) * 60)

        if attendance.save():
            flash(f'Goodbye {current_user.name}! You have worked for {hours} hours and {minutes} minutes today.', 'success')
        else:
            flash('Error recording sign-out. Please try again.', 'error')
    else:
        flash('Error calculating working hours. Please contact admin.', 'error')
    
    return redirect(url_for('employee_dashboard'))

@app.route('/employee/dashboard')
@login_required
def employee_dashboard():
    """Employee dashboard - shows personal attendance info"""
    if not isinstance(current_user, FirebaseEmployee):
        return redirect(url_for('employee_portal'))
    
    # Get today's attendance for this employee
    today = datetime.now().date()
    today_attendance = FirebaseAttendance.find_by_employee_and_date(current_user.employee_id, today)
    
    # Get recent attendance records (last 10 days)
    recent_attendance = FirebaseAttendance.get_by_employee(current_user.employee_id, limit=10)
    
    return render_template('employee_dashboard.html',
                         today_attendance=today_attendance,
                         recent_attendance=recent_attendance)

@app.route('/employee/attendance')
@login_required
def employee_attendance():
    """Employee attendance records - read-only view"""
    if not isinstance(current_user, FirebaseEmployee):
        return redirect(url_for('employee_portal'))
    
    # Get date filter
    date_filter = request.args.get('date')
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            attendance_records = [FirebaseAttendance.find_by_employee_and_date(current_user.employee_id, filter_date)]
            attendance_records = [record for record in attendance_records if record is not None]
        except ValueError:
            attendance_records = FirebaseAttendance.get_by_employee(current_user.employee_id, limit=50)
    else:
        attendance_records = FirebaseAttendance.get_by_employee(current_user.employee_id, limit=50)
    
    # Calculate statistics
    total_days = len(attendance_records)
    total_hours = sum([r.total_hours or 0 for r in attendance_records])
    complete_days = len([r for r in attendance_records if r.sign_in_time and r.sign_out_time])
    
    # Calculate average hours per day
    avg_hours_per_day = total_hours / total_days if total_days > 0 else 0
    
    # Calculate average sign-in and sign-out times
    signin_times = []
    signout_times = []
    
    for record in attendance_records:
        signin_dt = record.get_sign_in_datetime()
        signout_dt = record.get_sign_out_datetime()
        if signin_dt:
            signin_times.append(signin_dt)
        if signout_dt:
            signout_times.append(signout_dt)
    
    avg_signin_time = "09:00"  # Default
    avg_signout_time = "17:00"  # Default
    
    if signin_times:
        avg_hour = sum([t.hour for t in signin_times]) / len(signin_times)
        avg_minute = sum([t.minute for t in signin_times]) / len(signin_times)
        avg_signin_time = f"{int(avg_hour):02d}:{int(avg_minute):02d}"
    
    if signout_times:
        avg_hour = sum([t.hour for t in signout_times]) / len(signout_times)
        avg_minute = sum([t.minute for t in signout_times]) / len(signout_times)
        avg_signout_time = f"{int(avg_hour):02d}:{int(avg_minute):02d}"
    
    stats = {
        'total_days': total_days,
        'total_hours': total_hours,
        'complete_days': complete_days,
        'avg_hours_per_day': avg_hours_per_day,
        'avg_signin_time': avg_signin_time,
        'avg_signout_time': avg_signout_time
    }
    
    return render_template('employee_attendance_view.html',
                         attendance_records=attendance_records,
                         stats=stats)

@app.route('/employee/logout')
@login_required
def employee_logout():
    """Employee logout"""
    if not isinstance(current_user, FirebaseEmployee):
        return redirect(url_for('employee_portal'))
    
    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('index'))

@app.route('/employee/change_password', methods=['GET', 'POST'])
@login_required
def employee_change_password():
    """Allow an employee to change their own password"""
    if not isinstance(current_user, FirebaseEmployee):
        return redirect(url_for('employee_portal'))

    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validate inputs
        if not current_password or not new_password or not confirm_password:
            flash('Please fill in all password fields.', 'error')
            return render_template('employee_change_password.html')

        if not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'error')
            return render_template('employee_change_password.html')

        if new_password != confirm_password:
            flash('New password and confirmation do not match.', 'error')
            return render_template('employee_change_password.html')

        if len(new_password) < 6:
            flash('New password must be at least 6 characters long.', 'error')
            return render_template('employee_change_password.html')

        # Update password
        current_user.password_hash = generate_password_hash(new_password)
        if current_user.save():
            flash('Your password has been changed successfully.', 'success')
            return redirect(url_for('employee_dashboard'))
        else:
            flash('Error updating password. Please try again.', 'error')
            return render_template('employee_change_password.html')

    return render_template('employee_change_password.html')

# Admin routes
@app.route('/admin/login', methods=['GET'])
def admin_login():
    """Admin login page"""
    return render_template('admin_login.html')


@app.route('/auth/session_login', methods=['POST'])
def auth_session_login():
    """Verify Firebase ID token and create Flask session for employee/admin"""
    try:
        data = request.get_json() or {}
        id_token = data.get('idToken')
        user_type = data.get('userType')  # 'employee' | 'admin'
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        if not id_token or not user_type:
            return jsonify({'success': False, 'message': 'Missing idToken or userType'}), 400

        decoded = firebase_auth.verify_id_token(id_token)
        email = decoded.get('email')
        uid = decoded.get('uid')

        if not email:
            return jsonify({'success': False, 'message': 'No email on Firebase user'}), 400

        # Employees: enforce geofence check on login
        if user_type == 'employee':
            if not is_within_office_geofence(latitude, longitude):
                return jsonify({'success': False, 'message': 'Access denied: outside office geofence'}), 403

            # Map Firebase user to employee by email
            service = get_firebase_service()
            emp_data = service.get_employee_by_email(email)
            if not emp_data:
                return jsonify({'success': False, 'message': 'No employee mapped to this email'}), 404

            employee = FirebaseEmployee(emp_data)
            if not employee.is_active:
                return jsonify({'success': False, 'message': 'Employee is inactive'}), 403

            login_user(employee)
            return jsonify({'success': True, 'redirect': url_for('employee_dashboard')})

        # Admins: look up admin by username matching email
        if user_type == 'admin':
            admin = FirebaseAdmin.find_by_username(email)
            if not admin:
                return jsonify({'success': False, 'message': 'No admin mapped to this email'}), 404
            login_user(admin)
            return jsonify({'success': True, 'redirect': url_for('admin_dashboard')})

        return jsonify({'success': False, 'message': 'Invalid userType'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    """Admin dashboard"""
    if not isinstance(current_user, FirebaseAdmin):
        return redirect(url_for('admin_login'))
    
    # Get today's attendance
    today = datetime.now().date()
    today_attendance = FirebaseAttendance.get_by_date(today)
    
    # Get all employees
    employees = FirebaseEmployee.get_active()
    
    # Get attendance statistics
    total_employees = len(employees)
    signed_in_today = len([a for a in today_attendance if a.sign_in_time and not a.sign_out_time])
    signed_out_today = len([a for a in today_attendance if a.sign_out_time])
    
    return render_template('admin_dashboard.html',
                         employees=employees,
                         today_attendance=today_attendance,
                         total_employees=total_employees,
                         signed_in_today=signed_in_today,
                         signed_out_today=signed_out_today,
                         datetime=datetime)

@app.route('/admin/employees')
@login_required
def admin_employees():
    """Admin employee management"""
    if not isinstance(current_user, FirebaseAdmin):
        return redirect(url_for('admin_login'))
    
    employees = FirebaseEmployee.get_all()
    return render_template('admin_employees.html', employees=employees)

@app.route('/admin/employees/add', methods=['GET', 'POST'])
@login_required
def admin_add_employee():
    """Add new employee"""
    if not isinstance(current_user, FirebaseAdmin):
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        employee_id = request.form.get('employee_id')
        name = request.form.get('name')
        email = request.form.get('email')
        department = request.form.get('department')
        password = request.form.get('password')

        # Validate required fields
        if not all([employee_id, name, email, department, password]):
            flash('All fields are required, including password!', 'error')
            return render_template('admin_add_employee.html')

        # Check if employee ID already exists
        existing_employee = FirebaseEmployee.find_by_employee_id(employee_id)
        if existing_employee:
            flash('Employee ID already exists!', 'error')
            return render_template('admin_add_employee.html')

        # Hash the password
        password_hash = generate_password_hash(password)

        # Create new employee
        new_employee = FirebaseEmployee({
            'employee_id': employee_id,
            'name': name,
            'email': email,
            'department': department,
            'password_hash': password_hash,
            'is_active': True
        })

        if new_employee.save():
            flash(f'Employee {name} (ID: {employee_id}) has been added successfully!', 'success')
            return redirect(url_for('admin_employees'))
        else:
            flash('Error adding employee. Please try again.', 'error')
            return render_template('admin_add_employee.html')

    return render_template('admin_add_employee.html')

@app.route('/admin/employees/<employee_doc_id>/toggle_status', methods=['POST'])
@login_required
def admin_toggle_employee_status(employee_doc_id):
    """Toggle employee active/inactive status"""
    if not isinstance(current_user, FirebaseAdmin):
        return redirect(url_for('admin_login'))
    
    employee = FirebaseEmployee.find_by_doc_id(employee_doc_id)
    if not employee:
        flash('Employee not found!', 'error')
        return redirect(url_for('admin_employees'))
    
    employee.is_active = not employee.is_active
    
    if employee.save():
        status = "activated" if employee.is_active else "deactivated"
        flash(f'Employee {employee.name} has been {status} successfully!', 'success')
    else:
        flash('Error updating employee status. Please try again.', 'error')
    
    return redirect(url_for('admin_employees'))

@app.route('/admin/employees/<employee_doc_id>/delete', methods=['POST'])
@login_required
def admin_delete_employee(employee_doc_id):
    """Permanently delete an employee and their attendance records"""
    if not isinstance(current_user, FirebaseAdmin):
        return redirect(url_for('admin_login'))

    employee = FirebaseEmployee.find_by_doc_id(employee_doc_id)
    if not employee:
        flash('Employee not found!', 'error')
        return redirect(url_for('admin_employees'))

    employee_name = employee.name
    if employee.delete():
        flash(f'Employee {employee_name} and their attendance records have been deleted.', 'success')
    else:
        flash('Error deleting employee. Please try again.', 'error')

    return redirect(url_for('admin_employees'))

@app.route('/admin/employees/<employee_doc_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_employee(employee_doc_id):
    """Edit existing employee"""
    if not isinstance(current_user, FirebaseAdmin):
        return redirect(url_for('admin_login'))
    
    employee = FirebaseEmployee.find_by_doc_id(employee_doc_id)
    if not employee:
        flash('Employee not found!', 'error')
        return redirect(url_for('admin_employees'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        department = request.form.get('department')
        password = request.form.get('password')
        
        # Validate required fields
        if not all([name, email, department]):
            flash('All fields are required!', 'error')
            return render_template('admin_edit_employee.html', employee=employee)
        
        # Update employee
        employee.name = name
        employee.email = email
        employee.department = department
        
        # Update password if provided
        if password:
            employee.password_hash = generate_password_hash(password)
        
        if employee.save():
            if password:
                flash(f'Employee {employee.name} has been updated successfully (password changed).', 'success')
            else:
                flash(f'Employee {employee.name} has been updated successfully!', 'success')
            return redirect(url_for('admin_employees'))
        else:
            flash('Error updating employee. Please try again.', 'error')
            return render_template('admin_edit_employee.html', employee=employee)
    
    return render_template('admin_edit_employee.html', employee=employee)

@app.route('/admin/attendance')
@login_required
def admin_attendance():
    """Admin attendance records"""
    if not isinstance(current_user, FirebaseAdmin):
        return redirect(url_for('admin_login'))
    
    # Get date filter
    date_filter = request.args.get('date')
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            attendance_records = FirebaseAttendance.get_by_date(filter_date)
        except ValueError:
            attendance_records = FirebaseAttendance.get_recent(limit=100)
    else:
        attendance_records = FirebaseAttendance.get_recent(limit=100)
    
    employees = FirebaseEmployee.get_all()
    return render_template('admin_attendance.html', attendance_records=attendance_records, employees=employees)

@app.route('/admin/logout')
@login_required
def admin_logout():
    """Admin logout"""
    logout_user()
    return redirect(url_for('index'))

def create_sample_data():
    """Create sample data for testing"""
    print("🔥 Initializing Firebase database...")
    
    # Create default admin if none exists
    admin = FirebaseAdmin.find_by_username(Config.DEFAULT_ADMIN_USERNAME)
    if not admin:
        admin = FirebaseAdmin({
            'username': Config.DEFAULT_ADMIN_USERNAME,
            'password_hash': generate_password_hash(Config.DEFAULT_ADMIN_PASSWORD),
            'name': Config.DEFAULT_ADMIN_NAME
        })
        if admin.save():
            print(f"✅ Default admin created: {Config.DEFAULT_ADMIN_USERNAME}")
        else:
            print("❌ Failed to create default admin")
    
    if Config.SEED_SAMPLE_DATA:
        print("🌱 Seeding sample employees...")
        # Create sample employees
        for emp_data in Config.SAMPLE_EMPLOYEES:
            existing_employee = FirebaseEmployee.find_by_employee_id(emp_data['employee_id'])
            if not existing_employee:
                emp_copy = dict(emp_data)
                # Hash the password before creating employee
                password = emp_copy.pop('password')
                emp_copy['password_hash'] = generate_password_hash(password)
                employee = FirebaseEmployee(emp_copy)
                if employee.save():
                    print(f"✅ Sample employee created: {emp_data['employee_id']}")
                else:
                    print(f"❌ Failed to create sample employee: {emp_data['employee_id']}")

if __name__ == '__main__':
    create_sample_data()
    app.run(debug=True, host='0.0.0.0', port=5000)

