from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
import os
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config
import math

# Firebase imports
from firebase_models import FirebaseEmployee, FirebaseAdmin, FirebaseAttendance, FirebaseTimesheet
from firebase_service import get_firebase_service

app = Flask(__name__)
app.config.from_object(Config)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin_login'

# Initialize Firebase service
try:
    firebase_service = get_firebase_service()
    print("✅ Firebase service initialized")
except Exception as e:
    print(f"⚠️ Firebase service failed to initialize: {e}")
    print("🔄 App will continue without Firebase")
    firebase_service = None



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

@app.route('/employee/login', methods=['GET', 'POST'])
def employee_login():
    """Employee login functionality"""
    if request.method == 'POST':
        employee_id = request.form.get('employee_id')
        password = request.form.get('password')
        lat = request.form.get('latitude')
        lon = request.form.get('longitude')
        work_from_home = request.form.get('work_from_home') == '1'
        print(f"DEBUG Route: /employee/login POST lat={lat} lon={lon} work_from_home={work_from_home}")
        
        # Enforce geofence for employee login - only if not working from home
        if not work_from_home:
            # Geofence check for office workers - TEMPORARILY DISABLED
            # if not is_within_office_geofence(lat, lon):
            #     flash('Access denied: You are not within any office location.', 'error')
            #     return render_template('employee_login.html', 
            #                          office_locations=Config.OFFICE_LOCATIONS,
            #                          office_lat=Config.OFFICE_LATITUDE, 
            #                          office_lng=Config.OFFICE_LONGITUDE, 
            #                          office_radius=Config.OFFICE_RADIUS_METERS)
            pass
        
        employee = FirebaseEmployee.find_by_employee_id(employee_id)
        
        if not employee or not employee.is_active or not employee.check_password(password):
            flash('Invalid Employee ID or Password. Please check your credentials and try again.', 'error')
            return render_template('employee_login.html', 
                                 office_locations=Config.OFFICE_LOCATIONS,
                                 office_lat=Config.OFFICE_LATITUDE, 
                                 office_lng=Config.OFFICE_LONGITUDE, 
                                 office_radius=Config.OFFICE_RADIUS_METERS)

        # Login the employee
        login_user(employee)
        
        # Store work location preference in session
        session['work_from_home'] = work_from_home
        
        location_msg = "from home" if work_from_home else "from office"
        flash(f'Welcome {employee.name}! You have successfully logged in {location_msg}.', 'success')
        return redirect(url_for('employee_dashboard'))
    
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
        work_from_home = session.get('work_from_home', False)
        print(f"DEBUG Route: /employee/signin POST lat={lat} lon={lon} work_from_home={work_from_home}")
        
        # Enforce geofence for sign-in - only if not working from home
        if not work_from_home:
            # Geofence check for office workers - TEMPORARILY DISABLED
            # if not is_within_office_geofence(lat, lon):
            #     flash('Sign-in denied: You are not within any office location.', 'error')
            #     return redirect(url_for('employee_dashboard'))
            pass
        
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
                'total_hours': None,
                'work_location': 'home' if work_from_home else 'office'
            })
        else:
            attendance = existing_attendance
            attendance.sign_in_time = datetime.now()
            attendance.work_location = 'home' if work_from_home else 'office'
        
        print(f"DEBUG: Attempting to save attendance for {employee_id} on {today}")
        if attendance.save():
            print(f"DEBUG: Successfully saved attendance record")
            flash(f'Welcome {current_user.name}! You have successfully signed in at {datetime.now().strftime("%H:%M:%S")}', 'success')
        else:
            print(f"DEBUG: Failed to save attendance record")
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
    work_from_home = session.get('work_from_home', False)
    print(f"DEBUG Route: /employee/signout POST lat={lat} lon={lon} work_from_home={work_from_home}")
    
    # Enforce geofence for sign-out - only if not working from home
    if not work_from_home:
        # Geofence check for office workers - TEMPORARILY DISABLED
        # if not is_within_office_geofence(lat, lon):
        #     flash('Sign-out denied: You are not within any office location.', 'error')
        #     return redirect(url_for('employee_dashboard'))
        pass

    employee_id = current_user.employee_id
    today = datetime.now().date()
    attendance = FirebaseAttendance.find_by_employee_and_date(employee_id, today)

    if not attendance or not attendance.sign_in_time:
        flash('You have not signed in today!', 'error')
        return redirect(url_for('employee_dashboard'))

    if attendance.sign_out_time:
        flash('You have already signed out today!', 'error')
        return redirect(url_for('employee_dashboard'))

    # Check if timesheet is required for sign-out
    if Config.REQUIRE_TIMESHEET_FOR_SIGNOUT:
        existing_timesheet = FirebaseTimesheet.find_by_employee_and_date(employee_id, today)
        if not existing_timesheet:
            flash('You must submit your daily timesheet before signing out.', 'error')
            return render_template(
                'employee_signout.html',
                office_locations=Config.OFFICE_LOCATIONS,
                office_lat=Config.OFFICE_LATITUDE,
                office_lng=Config.OFFICE_LONGITUDE,
                office_radius=Config.OFFICE_RADIUS_METERS,
                show_timesheet_requirement=True
            )

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
    print(f"DEBUG: Today attendance query for {current_user.employee_id} on {today}: {today_attendance.to_dict() if today_attendance else 'None'}")
    
    # Get recent attendance records (last 10 days)
    recent_attendance = FirebaseAttendance.get_by_employee(current_user.employee_id, limit=10)
    print(f"DEBUG: Employee {current_user.employee_id} ({current_user.name}) has {len(recent_attendance)} attendance records")
    
    # If today's attendance exists but not in recent attendance, add it manually
    if today_attendance and not any(r.date == today_attendance.date for r in recent_attendance):
        print(f"DEBUG: Today's attendance exists but not in recent list - adding it manually")
        recent_attendance.insert(0, today_attendance)
    
    for i, record in enumerate(recent_attendance):
        print(f"DEBUG: Record {i}: {record.to_dict()}")
    
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
    print(f"DEBUG: Date filter received: {date_filter}")
    
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            print(f"DEBUG: Parsed filter date: {filter_date}")
            attendance_records = [FirebaseAttendance.find_by_employee_and_date(current_user.employee_id, filter_date)]
            attendance_records = [record for record in attendance_records if record is not None]
            print(f"DEBUG: Found {len(attendance_records)} records for filtered date {filter_date}")
            if len(attendance_records) == 0:
                print(f"DEBUG: No attendance records found for {current_user.employee_id} on {filter_date}")
        except ValueError as e:
            print(f"DEBUG: Error parsing date filter: {e}")
            attendance_records = FirebaseAttendance.get_by_employee(current_user.employee_id, limit=50)
    else:
        print(f"DEBUG: No date filter, getting all records")
        attendance_records = FirebaseAttendance.get_by_employee(current_user.employee_id, limit=50)
    
    print(f"DEBUG: Employee attendance view - {current_user.employee_id} has {len(attendance_records)} total records")
    
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

@app.route('/employee/timesheet', methods=['GET', 'POST'])
@login_required
def employee_timesheet():
    """Employee timesheet - daily report submission"""
    if not isinstance(current_user, FirebaseEmployee):
        return redirect(url_for('employee_portal'))
    
    today = datetime.now().date()
    today_date = today.strftime('%Y-%m-%d')
    
    # Get existing timesheet for today
    existing_timesheet = FirebaseTimesheet.find_by_employee_and_date(current_user.employee_id, today)
    
    if request.method == 'POST':
        # Get form data
        daily_report = request.form.get('daily_report', '').strip()
        
        # Validate required fields
        if not daily_report:
            flash('Daily report is required!', 'error')
            return render_template('employee_timesheet.html',
                                 today_date=today_date,
                                 existing_timesheet=existing_timesheet,
                                 recent_timesheets=[])
        
        # Create or update timesheet
        if existing_timesheet:
            # Update existing timesheet
            existing_timesheet.tasks_completed = daily_report
            existing_timesheet.challenges_faced = ''
            existing_timesheet.achievements = ''
            existing_timesheet.tomorrow_plans = ''
            existing_timesheet.additional_notes = ''
            timesheet = existing_timesheet
        else:
            # Create new timesheet
            timesheet = FirebaseTimesheet({
                'employee_id': current_user.employee_id,
                'date': today_date,
                'tasks_completed': daily_report,
                'challenges_faced': '',
                'achievements': '',
                'tomorrow_plans': '',
                'additional_notes': ''
            })
        
        # Save timesheet
        if timesheet.save():
            action = "updated" if existing_timesheet else "submitted"
            flash(f'Your timesheet has been {action} successfully!', 'success')
            return redirect(url_for('employee_dashboard'))
        else:
            flash('Error saving timesheet. Please try again.', 'error')
    
    # Get recent timesheets for display (excluding today's)
    recent_timesheets = FirebaseTimesheet.get_by_employee(current_user.employee_id, limit=10)
    recent_timesheets = [ts for ts in recent_timesheets if ts.date != today_date][:5]  # Show last 5 excluding today
    
    return render_template('employee_timesheet.html',
                         today_date=today_date,
                         existing_timesheet=existing_timesheet,
                         recent_timesheets=recent_timesheets)

# Admin routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        admin = FirebaseAdmin.find_by_username(username)
        
        if admin and admin.check_password(password):
            login_user(admin)
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('admin_login.html')

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
    
    # Get filters
    date_filter = request.args.get('date')
    status_filter = request.args.get('status')
    
    # Get base attendance records
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            attendance_records = FirebaseAttendance.get_by_date(filter_date)
        except ValueError:
            attendance_records = FirebaseAttendance.get_recent(limit=100)
    else:
        attendance_records = FirebaseAttendance.get_recent(limit=100)
    
    # Apply status filter
    if status_filter == 'incomplete_sessions':
        # Filter for employees who signed in but didn't sign out
        attendance_records = [record for record in attendance_records 
                            if record.sign_in_time and not record.sign_out_time]
    elif status_filter == 'completed_sessions':
        # Filter for employees who completed their day
        attendance_records = [record for record in attendance_records 
                            if record.sign_in_time and record.sign_out_time]
    
    employees = FirebaseEmployee.get_all()
    return render_template('admin_attendance.html', 
                         attendance_records=attendance_records, 
                         employees=employees,
                         status_filter=status_filter)

@app.route('/admin/timesheets')
@login_required
def admin_timesheets():
    """Admin timesheet records"""
    if not isinstance(current_user, FirebaseAdmin):
        return redirect(url_for('admin_login'))
    
    # Get filters
    date_filter = request.args.get('date')
    employee_filter = request.args.get('employee_id')
    
    # Get timesheet records based on filters
    if date_filter and employee_filter:
        # Filter by both date and employee
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            timesheet_records = [FirebaseTimesheet.find_by_employee_and_date(employee_filter, filter_date)]
            timesheet_records = [record for record in timesheet_records if record is not None]
        except ValueError:
            timesheet_records = []
    elif date_filter:
        # Filter by date only
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            timesheet_records = FirebaseTimesheet.get_by_date(filter_date)
        except ValueError:
            timesheet_records = FirebaseTimesheet.get_recent(limit=100)
    elif employee_filter:
        # Filter by employee only
        timesheet_records = FirebaseTimesheet.get_by_employee(employee_filter, limit=100)
    else:
        # No filters - get recent records
        timesheet_records = FirebaseTimesheet.get_recent(limit=100)
    
    # Get all employees for dropdown and employee lookup
    employees = FirebaseEmployee.get_all()
    employees_dict = {emp.employee_id: emp for emp in employees}
    
    return render_template('admin_timesheets.html', 
                         timesheet_records=timesheet_records, 
                         employees=employees,
                         employees_dict=employees_dict)



@app.route('/admin/logout')
@login_required
def admin_logout():
    """Admin logout"""
    logout_user()
    return redirect(url_for('index'))

@app.route('/debug/create_test_attendance/<employee_id>')
def create_test_attendance(employee_id):
    """Debug route to create test attendance data"""
    try:
        from datetime import datetime
        print(f"DEBUG: Creating test attendance for {employee_id}")
        
        test_attendance = FirebaseAttendance({
            'employee_id': employee_id,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'sign_in_time': datetime.now().replace(hour=9, minute=0).isoformat(),
            'sign_out_time': datetime.now().replace(hour=17, minute=30).isoformat(),
            'total_hours': 8.5
        })
        
        print(f"DEBUG: Test attendance object created: {test_attendance.to_dict()}")
        
        if test_attendance.save():
            print(f"DEBUG: Successfully saved test attendance")
            return f"✅ Test attendance created for {employee_id} on {datetime.now().strftime('%Y-%m-%d')}"
        else:
            print(f"DEBUG: Failed to save test attendance")
            return f"❌ Failed to create test attendance for {employee_id}"
    except Exception as e:
        print(f"DEBUG: Exception in create_test_attendance: {e}")
        return f"❌ Error: {e}"

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
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

