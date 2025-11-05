from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
import csv
import io
import os
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config
import math
from firebase_admin import auth as firebase_auth
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Firebase imports
from firebase_models import (
    FirebaseEmployee,
    FirebaseAdmin,
    FirebaseAttendance,
    FirebaseTimesheet,
    FirebaseWFHApproval,
)
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
        # Employee must check WFH box AND admin must have approved WFH
        work_from_home_checkbox = request.form.get('work_from_home') == '1'
        confirm_office = request.form.get('confirm_office') == '1'  # Confirmation flag
        today_str = datetime.now().strftime('%Y-%m-%d')
        admin_approved_wfh = FirebaseWFHApproval.is_approved_for_date(employee_id, today_str)
        
        # WFH only if: checkbox is checked AND admin approved
        work_from_home = work_from_home_checkbox and admin_approved_wfh
        
        # Scenario 2: Admin approved but checkbox not checked - need confirmation
        if admin_approved_wfh and not work_from_home_checkbox and not confirm_office:
            flash('Admin has approved WFH, but you did not check the WFH box. Please confirm you want to sign in from office.', 'warning')
            return render_template('employee_signin.html',
                                 office_locations=Config.OFFICE_LOCATIONS,
                                 office_lat=Config.OFFICE_LATITUDE,
                                 office_lng=Config.OFFICE_LONGITUDE,
                                 office_radius=Config.OFFICE_RADIUS_METERS,
                                 admin_approved_wfh=admin_approved_wfh,
                                 show_office_confirm=True,
                                 confirm_message="Admin has approved WFH, but you're signing in from office. Continue?")
        
        # Scenario 3: Checkbox checked but admin not approved - need confirmation
        if work_from_home_checkbox and not admin_approved_wfh and not confirm_office:
            flash('WFH not approved by admin for today. Please confirm you want to sign in from office.', 'warning')
            return render_template('employee_signin.html',
                                 office_locations=Config.OFFICE_LOCATIONS,
                                 office_lat=Config.OFFICE_LATITUDE,
                                 office_lng=Config.OFFICE_LONGITUDE,
                                 office_radius=Config.OFFICE_RADIUS_METERS,
                                 admin_approved_wfh=admin_approved_wfh,
                                 show_office_confirm=True,
                                 confirm_message="WFH is not approved. You're signing in from office. Continue?")
        print(f"DEBUG Route: /employee/signin POST lat={lat} lon={lon} work_from_home={work_from_home}")
        
        # Enforce geofence for sign-in - only if not working from home
        if not work_from_home:
            # Geofence check for office workers
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
                'total_hours': None,
                'work_location': 'home' if work_from_home else 'office',
                'wfh_approved': work_from_home
            })
        else:
            attendance = existing_attendance
            attendance.sign_in_time = datetime.now()
            attendance.work_location = 'home' if work_from_home else 'office'
            attendance.wfh_approved = work_from_home
        
        print(f"DEBUG: Attempting to save attendance for {employee_id} on {today}")
        if attendance.save():
            print(f"DEBUG: Successfully saved attendance record")
            flash(f'Welcome {current_user.name}! You have successfully signed in at {datetime.now().strftime("%H:%M:%S")}', 'success')
        else:
            print(f"DEBUG: Failed to save attendance record")
            flash('Error recording sign-in. Please try again.', 'error')
        
        return redirect(url_for('employee_dashboard'))
    
    # Check if admin has approved WFH for today
    today_str = datetime.now().strftime('%Y-%m-%d')
    admin_approved_wfh = FirebaseWFHApproval.is_approved_for_date(current_user.employee_id, today_str)
    
    return render_template('employee_signin.html', 
                         office_locations=Config.OFFICE_LOCATIONS,
                         office_lat=Config.OFFICE_LATITUDE, 
                         office_lng=Config.OFFICE_LONGITUDE, 
                         office_radius=Config.OFFICE_RADIUS_METERS,
                         admin_approved_wfh=admin_approved_wfh)

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

    employee_id = current_user.employee_id
    today = datetime.now().date()
    attendance = FirebaseAttendance.find_by_employee_and_date(employee_id, today)
    
    # Get work location from attendance record
    today_str = today.strftime('%Y-%m-%d')
    work_from_home = (attendance.work_location == 'home' if attendance else False) or (
        FirebaseWFHApproval.is_approved_for_date(employee_id, today_str)
    )
    print(f"DEBUG: Work from home status: {work_from_home}")
    
    # Enforce geofence for sign-out - only if not working from home
    if not work_from_home:
        # Geofence check for office workers
        if not is_within_office_geofence(lat, lon):
            flash('Sign-out denied: You are not within any office location.', 'error')
            return redirect(url_for('employee_dashboard'))

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
    
    # Get recent timesheets instead of recent attendance (last 10 days)
    recent_timesheets = FirebaseTimesheet.get_by_employee(current_user.employee_id, limit=10)
    print(f"DEBUG: Employee {current_user.employee_id} ({current_user.name}) has {len(recent_timesheets)} timesheet records")
    
    for i, record in enumerate(recent_timesheets):
        print(f"DEBUG: Timesheet Record {i}: {record.to_dict()}")
    
    return render_template('employee_dashboard.html',
                         today_attendance=today_attendance,
                         recent_timesheets=recent_timesheets,
                         datetime=datetime)

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

@app.route('/employee/wfh')
@login_required
def employee_wfh():
    """Show admin-approved WFH dates for the logged-in employee"""
    if not isinstance(current_user, FirebaseEmployee):
        return redirect(url_for('employee_portal'))
    approvals = get_firebase_service().get_all_wfh_approvals()
    my_approvals = [ap for ap in approvals if ap.get('employee_id') == current_user.employee_id]
    return render_template('employee_wfh.html', approvals=my_approvals)

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
    # Password changes are managed in Firebase Authentication (not in-app)
    flash('Password changes are disabled. Use "Forgot password" on the login page.', 'error')
    return redirect(url_for('employee_dashboard'))

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

        if not id_token or not user_type:
            return jsonify({'success': False, 'message': 'Missing idToken or userType'}), 400

        decoded = firebase_auth.verify_id_token(id_token)
        email = decoded.get('email')
        if not email:
            return jsonify({'success': False, 'message': 'No email on Firebase user'}), 400

        if user_type == 'employee':
            service = get_firebase_service()
            emp_data = service.get_employee_by_email(email)
            if not emp_data:
                return jsonify({'success': False, 'message': 'No employee mapped to this email'}), 404
            employee = FirebaseEmployee(emp_data)
            if not employee.is_active:
                return jsonify({'success': False, 'message': 'Employee is inactive'}), 403
            login_user(employee)
            return jsonify({'success': True, 'redirect': url_for('employee_dashboard')})

        if user_type == 'admin':
            admin = FirebaseAdmin.find_by_username(email)
            if not admin:
                return jsonify({'success': False, 'message': 'No admin mapped to this email'}), 404
            login_user(admin)
            return jsonify({'success': True, 'redirect': url_for('admin_dashboard')})

        return jsonify({'success': False, 'message': 'Invalid userType'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/auth/employee_precheck', methods=['POST'])
def auth_employee_precheck():
    """Check if an employee exists for the provided email (admin must have added them)."""
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip()
        if not email:
            return jsonify({'success': False, 'message': 'Email is required'}), 400
        service = get_firebase_service()
        emp = service.get_employee_by_email(email)
        if not emp:
            return jsonify({'success': False, 'message': 'No employee found for this email. Contact admin.'}), 404
        if not emp.get('is_active', True):
            return jsonify({'success': False, 'message': 'Employee is inactive. Contact admin.'}), 403
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

def send_otp_email(email: str, otp: str) -> bool:
    """Send OTP email to user"""
    try:
        smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        smtp_user = os.environ.get('SMTP_USER', '')
        smtp_password = os.environ.get('SMTP_PASSWORD', '')
        from_email = os.environ.get('FROM_EMAIL', smtp_user)
        smtp_security = os.environ.get('SMTP_SECURITY', 'STARTTLS').upper()  # STARTTLS, TLS, SSL, or NONE
        
        if not smtp_user or not smtp_password:
            print("⚠️ SMTP not configured. OTP:", otp)
            return False
        
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = email
        msg['Subject'] = 'Employee Account Verification OTP'
        
        body = f"""
Hello,

You have requested to create an account for the Employee Attendance System.

Your verification OTP is: {otp}

This OTP is valid for 15 minutes.

If you did not request this, please ignore this email.

Best regards,
Attendance System Team
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Connect based on security mode
        if smtp_security == 'SSL':
            # SSL mode (usually port 465)
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        elif smtp_security == 'TLS':
            # TLS mode (usually port 587)
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
        elif smtp_security == 'STARTTLS':
            # STARTTLS mode (usually port 587)
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
        else:
            # No security (not recommended, usually port 25)
            server = smtplib.SMTP(smtp_server, smtp_port)
        
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        
        print(f"✅ OTP email sent to {email}")
        return True
    except Exception as e:
        print(f"❌ Error sending OTP email: {e}")
        return False

@app.route('/auth/send_signup_otp', methods=['POST'])
def auth_send_signup_otp():
    """Generate and send OTP for employee signup"""
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip()
        if not email:
            return jsonify({'success': False, 'message': 'Email is required'}), 400
        
        # Check if employee exists
        service = get_firebase_service()
        emp = service.get_employee_by_email(email)
        if not emp:
            return jsonify({'success': False, 'message': 'No employee found for this email. Contact admin.'}), 404
        if not emp.get('is_active', True):
            return jsonify({'success': False, 'message': 'Employee is inactive. Contact admin.'}), 403
        
        # Check if Firebase Auth user already exists
        try:
            firebase_auth.get_user_by_email(email)
            return jsonify({'success': False, 'message': 'An account already exists for this email. Please login instead.'}), 409
        except firebase_auth.UserNotFoundError:
            pass  # User doesn't exist, continue with OTP
        
        # Generate and send OTP
        otp = service.generate_otp(email)
        email_sent = send_otp_email(email, otp)
        
        if not email_sent:
            # If email failed, still return success but log OTP (for development)
            print(f"⚠️ Email send failed. OTP for {email}: {otp}")
            return jsonify({
                'success': True, 
                'message': 'OTP generated. Check console for OTP (email not configured).',
                'otp': otp if os.environ.get('DEBUG_OTP', 'false').lower() == 'true' else None
            })
        
        return jsonify({'success': True, 'message': 'OTP sent to your email'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/auth/verify_signup_otp', methods=['POST'])
def auth_verify_signup_otp():
    """Verify OTP for employee signup"""
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip()
        otp = (data.get('otp') or '').strip()
        
        if not email or not otp:
            return jsonify({'success': False, 'message': 'Email and OTP are required'}), 400
        
        service = get_firebase_service()
        if service.verify_otp(email, otp):
            return jsonify({'success': True, 'message': 'OTP verified successfully'})
        else:
            return jsonify({'success': False, 'message': 'Invalid or expired OTP'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/auth/employee_signup', methods=['POST'])
def auth_employee_signup():
    """Finalize signup: verify token, ensure employee exists by email, then log them in."""
    try:
        data = request.get_json() or {}
        id_token = data.get('idToken')
        if not id_token:
            return jsonify({'success': False, 'message': 'Missing idToken'}), 400

        decoded = firebase_auth.verify_id_token(id_token)
        email = decoded.get('email')
        if not email:
            return jsonify({'success': False, 'message': 'No email on Firebase user'}), 400

        service = get_firebase_service()
        emp_data = service.get_employee_by_email(email)
        if not emp_data:
            return jsonify({'success': False, 'message': 'No employee found for this email. Contact admin.'}), 404
        employee = FirebaseEmployee(emp_data)
        if not employee.is_active:
            return jsonify({'success': False, 'message': 'Employee is inactive. Contact admin.'}), 403

        login_user(employee)
        return jsonify({'success': True, 'redirect': url_for('employee_dashboard')})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/auth/password_reset_link', methods=['POST'])
def auth_password_reset_link():
    """Generate a password reset link for the given email (server-side fallback)."""
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip()
        continue_url = (data.get('continueUrl') or url_for('employee_login', _external=True))
        if not email:
            return jsonify({'success': False, 'message': 'Email is required'}), 400

        action_settings = firebase_auth.ActionCodeSettings(
            url=continue_url,
            handle_code_in_app=False,
        )
        link = firebase_auth.generate_password_reset_link(email, action_settings)
        return jsonify({'success': True, 'link': link})
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
    # Count all who signed in today (even if they already signed out)
    signed_in_today = len([a for a in today_attendance if a.sign_in_time])
    signed_out_today = len([a for a in today_attendance if a.sign_out_time])
    
    # Recent timesheets for dashboard preview
    recent_timesheets = FirebaseTimesheet.get_recent(limit=5)
    employees_dict = {emp.employee_id: emp for emp in employees}

    return render_template('admin_dashboard.html',
                         employees=employees,
                         today_attendance=today_attendance,
                         total_employees=total_employees,
                         signed_in_today=signed_in_today,
                         signed_out_today=signed_out_today,
                         recent_timesheets=recent_timesheets,
                         employees_dict=employees_dict,
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
        # Get all form data
        employee_id = request.form.get('employee_id')
        name = request.form.get('name')
        email = request.form.get('email')
        mobile = request.form.get('mobile')
        department = request.form.get('department')
        position = request.form.get('position')
        hire_date = request.form.get('hire_date')
        address = request.form.get('address')
        emergency_contact = request.form.get('emergency_contact')
        emergency_contact_phone = request.form.get('emergency_contact_phone')
        # Validate required fields
        required_fields = [employee_id, name, email, mobile, department, position, hire_date, address, emergency_contact, emergency_contact_phone]
        if not all(required_fields):
            flash('All fields are required!', 'error')
            return render_template('admin_add_employee.html')

        # Check if employee ID already exists
        existing_employee = FirebaseEmployee.find_by_employee_id(employee_id)
        if existing_employee:
            flash('Employee ID already exists!', 'error')
            return render_template('admin_add_employee.html')

        # Check if email already exists
        all_employees = FirebaseEmployee.get_all()
        for emp in all_employees:
            if emp.email.lower() == email.lower():
                flash('Email address already exists!', 'error')
                return render_template('admin_add_employee.html')

        # Handle profile image upload
        profile_image_path = ''
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and file.filename:
                # Save the image (you might want to use a more secure method here)
                import os
                import uuid
                uploads_dir = os.path.join(app.root_path, 'static', 'uploads', 'employee_images')
                os.makedirs(uploads_dir, exist_ok=True)
                
                # Generate unique filename
                file_extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                filename = f"{employee_id}_{uuid.uuid4().hex}.{file_extension}"
                file_path = os.path.join(uploads_dir, filename)
                
                try:
                    file.save(file_path)
                    profile_image_path = f"uploads/employee_images/{filename}"
                except Exception as e:
                    print(f"Error saving image: {e}")
                    flash('Error uploading profile image. Please try again.', 'error')
                    return render_template('admin_add_employee.html')

        # Create new employee
        new_employee = FirebaseEmployee({
            'employee_id': employee_id,
            'name': name,
            'email': email,
            'mobile': mobile,
            'department': department,
            'position': position,
            'hire_date': hire_date,
            'address': address,
            'emergency_contact': emergency_contact,
            'emergency_contact_phone': emergency_contact_phone,
            'profile_image': profile_image_path,
            'password_hash': '',
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
        mobile = request.form.get('mobile')
        department = request.form.get('department')
        position = request.form.get('position')
        hire_date = request.form.get('hire_date')
        blood_group = request.form.get('blood_group', '')
        address = request.form.get('address')
        emergency_contact = request.form.get('emergency_contact')
        emergency_contact_phone = request.form.get('emergency_contact_phone')
        password = request.form.get('password')
        remove_profile_image = request.form.get('remove_profile_image')
        
        # Validate required fields
        if not all([name, email, mobile, department, position, hire_date, address, emergency_contact, emergency_contact_phone]):
            flash('All fields are required!', 'error')
            return render_template('admin_edit_employee.html', employee=employee)
        
        # Update employee
        employee.name = name
        employee.email = email
        employee.mobile = mobile
        employee.department = department
        employee.position = position
        employee.hire_date = hire_date
        employee.address = address
        employee.blood_group = blood_group
        employee.emergency_contact = emergency_contact
        employee.emergency_contact_phone = emergency_contact_phone
        
        # Password updates are disabled; managed via Firebase Auth

        # Handle profile image upload/removal
        import os
        import uuid
        existing_image = employee.profile_image or ''
        upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'employee_images')
        os.makedirs(upload_dir, exist_ok=True)

        file = request.files.get('profile_image')
        try:
            if remove_profile_image == '1':
                # Delete existing file if present
                if existing_image:
                    try:
                        os.remove(os.path.join(app.root_path, 'static', existing_image))
                    except Exception:
                        pass
                employee.profile_image = ''
            elif file and file.filename:
                # Save new file
                file_extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                filename = f"{employee.employee_id}_{uuid.uuid4().hex}.{file_extension}"
                file_path = os.path.join(upload_dir, filename)
                file.save(file_path)
                # Remove old file
                if existing_image:
                    try:
                        os.remove(os.path.join(app.root_path, 'static', existing_image))
                    except Exception:
                        pass
                employee.profile_image = f"uploads/employee_images/{filename}"
        except Exception as e:
            print(f"Error handling profile image: {e}")
            flash('Error updating profile image. Please try again.', 'error')
            return render_template('admin_edit_employee.html', employee=employee)
        
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

@app.route('/admin/manage-team')
@login_required
def admin_manage_team():
    """Manage the Team page - filters + table UI"""
    if not isinstance(current_user, FirebaseAdmin):
        return redirect(url_for('admin_login'))

    employees = FirebaseEmployee.get_all()
    total_employees = len(employees)
    # online: employees with a sign-in but no sign-out today
    today = datetime.now().date()
    today_attendance = FirebaseAttendance.get_by_date(today)
    online_ids = {a.employee_id for a in today_attendance if a.sign_in_time and not a.sign_out_time}
    online_count = len(online_ids)

    approvals = get_firebase_service().get_all_wfh_approvals()
    return render_template(
        'admin_manage_team.html',
        employees=employees,
        total_employees=total_employees,
        online_count=online_count,
        wfh_approvals=approvals,
        datetime=datetime
    )

@app.route('/admin/wfh/approve', methods=['POST'])
@login_required
def admin_wfh_approve():
    if not isinstance(current_user, FirebaseAdmin):
        return redirect(url_for('admin_login'))
    employee_id = request.form.get('employee_id')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    if not (employee_id and start_date and end_date):
        flash('Employee, start date, and end date are required.', 'error')
        return redirect(url_for('admin_manage_team'))
    ok = FirebaseWFHApproval.approve(employee_id, start_date, end_date, approved_by=current_user.username)
    if ok:
        flash('WFH approved successfully.', 'success')
    else:
        flash('Failed to approve WFH. Please try again.', 'error')
    return redirect(url_for('admin_manage_team'))


# -------------------- Payroll helpers removed --------------------
def _calculate_monthly_hours(employee_id: str, year: int, month: int):
    """Aggregate attendance hours for an employee within yyyy-mm."""
    # Get up to ~62 records to cover month; filtering client-side as attendance query lacks date range
    records = FirebaseAttendance.get_by_employee(employee_id, limit=200)
    target_prefix = f"{year:04d}-{month:02d}-"
    month_records = [r for r in records if isinstance(r.date, str) and r.date.startswith(target_prefix)]
    total_hours = sum([float(r.total_hours or 0) for r in month_records])
    return total_hours, month_records

def _calculate_employee_month_stats(employee_id: str, year: int, month: int):
    """Return stats for a given employee and month: total_hours, worked_days, absent_days, overtime_hours."""
    import calendar
    total_hours, month_records = _calculate_monthly_hours(employee_id, year, month)
    # Unique days with any sign-in
    worked_days = len({r.date for r in month_records if r.sign_in_time})
    days_in_month = calendar.monthrange(year, month)[1]
    absent_days = max(0, days_in_month - worked_days)
    # Derive overtime using config defaults and (if set) employee settings
    # Payroll-specific settings removed; keep attendance stats helper minimal
    std_hours_per_day = Config.WORKING_HOURS_END - Config.WORKING_HOURS_START
    working_days = Config.PAYROLL_WORKING_DAYS_PER_MONTH
    standard_month_hours = std_hours_per_day * working_days
    overtime_hours = max(0.0, total_hours - standard_month_hours)
    return {
        'total_hours': round(total_hours, 2),
        'worked_days': worked_days,
        'absent_days': absent_days,
        'overtime_hours': round(overtime_hours, 2),
        'days_in_month': days_in_month,
    }

def _calculate_payslip_preview(*args, **kwargs):
    return {}
def _generate_payslip_for_employee(*args, **kwargs):
    return None

    

    

    

    


@app.route('/admin/timesheets/download')
@login_required
def admin_timesheets_download():
    """Download filtered timesheets as CSV. Requires at least one filter."""
    if not isinstance(current_user, FirebaseAdmin):
        return redirect(url_for('admin_login'))

    date_filter = request.args.get('date')
    employee_filter = request.args.get('employee_id')
    if not (date_filter or employee_filter):
        flash('Please apply a filter (date and/or employee) before downloading.', 'error')
        return redirect(url_for('admin_timesheets'))

    # Get filtered timesheets
    if date_filter and employee_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            timesheet_records = [FirebaseTimesheet.find_by_employee_and_date(employee_filter, filter_date)]
            timesheet_records = [record for record in timesheet_records if record is not None]
        except ValueError:
            timesheet_records = []
    elif date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            timesheet_records = FirebaseTimesheet.get_by_date(filter_date)
        except ValueError:
            timesheet_records = []
    else:
        timesheet_records = FirebaseTimesheet.get_by_employee(employee_filter, limit=1000)

    employees = FirebaseEmployee.get_all()
    employees_dict = {emp.employee_id: emp for emp in employees}

    output = io.StringIO()
    writer = csv.writer(output)
    # Restore main columns, and compress all text fields into a single Time Sheet column
    writer.writerow(['Date','Employee ID','Employee Name','Department','Submitted At','Time Sheet'])
    for ts in timesheet_records:
        emp = employees_dict.get(ts.employee_id)
        # Combine all available text fields into one block
        parts = [p for p in [ts.tasks_completed, ts.challenges_faced, ts.achievements, ts.tomorrow_plans, ts.additional_notes] if p]
        timesheet_text = "\n\n".join(parts)
        writer.writerow([
            ts.date,
            ts.employee_id,
            (emp.name if emp else ''),
            (emp.department if emp else ''),
            (ts.submitted_at[:19] if ts.submitted_at else ''),
            timesheet_text
        ])

    csv_bytes = io.BytesIO(output.getvalue().encode('utf-8-sig'))
    filename_parts = ['timesheets']
    if date_filter:
        filename_parts.append(date_filter)
    if employee_filter:
        filename_parts.append(employee_filter)
    filename = '_'.join(filename_parts) + '.csv'

    return send_file(csv_bytes, as_attachment=True, download_name=filename, mimetype='text/csv')

    

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

