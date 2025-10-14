from flask_login import UserMixin
from datetime import datetime
from firebase_service import get_firebase_service
from werkzeug.security import check_password_hash
from typing import Optional, List, Dict, Any

class FirebaseEmployee(UserMixin):
    """Firebase Employee model for Flask-Login"""
    
    def __init__(self, employee_data: Dict[str, Any]):
        self.id = employee_data.get('id')  # Firestore document ID
        self.employee_id = employee_data.get('employee_id')
        self.name = employee_data.get('name')
        self.email = employee_data.get('email')
        self.department = employee_data.get('department')
        self.password_hash = employee_data.get('password_hash')
        self._is_active = employee_data.get('is_active', True)
        self.mobile = employee_data.get('mobile', '')
        self.profile_image = employee_data.get('profile_image', '')
        self.position = employee_data.get('position', '')
        self.hire_date = employee_data.get('hire_date', '')
        self.address = employee_data.get('address', '')
        self.emergency_contact = employee_data.get('emergency_contact', '')
        self.emergency_contact_phone = employee_data.get('emergency_contact_phone', '')
        self.blood_group = employee_data.get('blood_group', '')
        self.created_at = employee_data.get('created_at')
        self.updated_at = employee_data.get('updated_at')
    
    @property
    def is_active(self):
        return self._is_active
    
    @is_active.setter
    def is_active(self, value):
        self._is_active = value
    
    def get_id(self):
        """Required by Flask-Login"""
        return f"employee-{self.id}"
    
    def check_password(self, password: str) -> bool:
        """Check if provided password matches"""
        return check_password_hash(self.password_hash, password)
    
    @staticmethod
    def find_by_employee_id(employee_id: str) -> Optional['FirebaseEmployee']:
        """Find employee by employee_id"""
        firebase_service = get_firebase_service()
        employee_data = firebase_service.get_employee_by_id(employee_id)
        if employee_data:
            return FirebaseEmployee(employee_data)
        return None
    
    @staticmethod
    def find_by_doc_id(doc_id: str) -> Optional['FirebaseEmployee']:
        """Find employee by Firestore document ID"""
        firebase_service = get_firebase_service()
        employee_data = firebase_service.get_employee_by_doc_id(doc_id)
        if employee_data:
            return FirebaseEmployee(employee_data)
        return None
    
    @staticmethod
    def get_all() -> List['FirebaseEmployee']:
        """Get all employees"""
        firebase_service = get_firebase_service()
        employees_data = firebase_service.get_all_employees()
        return [FirebaseEmployee(emp_data) for emp_data in employees_data]
    
    @staticmethod
    def get_active() -> List['FirebaseEmployee']:
        """Get all active employees"""
        all_employees = FirebaseEmployee.get_all()
        return [emp for emp in all_employees if emp._is_active]
    
    def save(self) -> bool:
        """Save employee to Firebase"""
        firebase_service = get_firebase_service()
        employee_data = {
            'employee_id': self.employee_id,
            'name': self.name,
            'email': self.email,
            'department': self.department,
            'password_hash': self.password_hash,
            'is_active': self._is_active,
            'mobile': self.mobile,
            'profile_image': self.profile_image,
            'position': self.position,
            'hire_date': self.hire_date,
            'address': self.address,
            'emergency_contact': self.emergency_contact,
            'emergency_contact_phone': self.emergency_contact_phone,
            'blood_group': self.blood_group
        }
        
        if self.id:
            # Update existing employee
            return firebase_service.update_employee(self.id, employee_data)
        else:
            # Create new employee
            try:
                doc_id = firebase_service.create_employee(employee_data)
                self.id = doc_id
                return True
            except Exception:
                return False
    
    def delete(self) -> bool:
        """Delete employee from Firebase"""
        if not self.id:
            return False
        firebase_service = get_firebase_service()
        return firebase_service.delete_employee(self.id)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'employee_id': self.employee_id,
            'name': self.name,
            'email': self.email,
            'department': self.department,
            'is_active': self._is_active,
            'mobile': self.mobile,
            'profile_image': self.profile_image,
            'position': self.position,
            'hire_date': self.hire_date,
            'address': self.address,
            'emergency_contact': self.emergency_contact,
            'emergency_contact_phone': self.emergency_contact_phone,
            'blood_group': self.blood_group,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

class FirebaseAdmin(UserMixin):
    """Firebase Admin model for Flask-Login"""
    
    def __init__(self, admin_data: Dict[str, Any]):
        self.id = admin_data.get('id')  # Firestore document ID
        self.username = admin_data.get('username')
        self.password_hash = admin_data.get('password_hash')
        self.name = admin_data.get('name')
        self.created_at = admin_data.get('created_at')
        self.updated_at = admin_data.get('updated_at')
    
    def get_id(self):
        """Required by Flask-Login"""
        return f"admin-{self.id}"
    
    def check_password(self, password: str) -> bool:
        """Check if provided password matches"""
        return check_password_hash(self.password_hash, password)
    
    @staticmethod
    def find_by_username(username: str) -> Optional['FirebaseAdmin']:
        """Find admin by username"""
        firebase_service = get_firebase_service()
        admin_data = firebase_service.get_admin_by_username(username)
        if admin_data:
            return FirebaseAdmin(admin_data)
        return None
    
    @staticmethod
    def find_by_doc_id(doc_id: str) -> Optional['FirebaseAdmin']:
        """Find admin by Firestore document ID"""
        firebase_service = get_firebase_service()
        admin_data = firebase_service.get_admin_by_doc_id(doc_id)
        if admin_data:
            return FirebaseAdmin(admin_data)
        return None
    
    def save(self) -> bool:
        """Save admin to Firebase"""
        firebase_service = get_firebase_service()
        admin_data = {
            'username': self.username,
            'password_hash': self.password_hash,
            'name': self.name
        }
        
        try:
            if self.id:
                # Update existing admin
                return firebase_service.update_admin(self.id, admin_data)
            else:
                # Create new admin
                doc_id = firebase_service.create_admin(admin_data)
                self.id = doc_id
                return True
        except Exception:
            return False

class FirebaseAttendance:
    """Firebase Attendance model"""
    
    def __init__(self, attendance_data: Dict[str, Any]):
        self.id = attendance_data.get('id')  # Firestore document ID
        self.employee_id = attendance_data.get('employee_id')
        self.date = attendance_data.get('date')  # String format: YYYY-MM-DD
        self.sign_in_time = attendance_data.get('sign_in_time')  # ISO string or datetime
        self.sign_out_time = attendance_data.get('sign_out_time')  # ISO string or datetime
        self.total_hours = attendance_data.get('total_hours')
        self.work_location = attendance_data.get('work_location', 'office')  # 'office' or 'home'
        self.wfh_approved = attendance_data.get('wfh_approved', False)
        self.created_at = attendance_data.get('created_at')
    
    @staticmethod
    def find_by_employee_and_date(employee_id: str, date: datetime) -> Optional['FirebaseAttendance']:
        """Find attendance record by employee and date"""
        firebase_service = get_firebase_service()
        date_str = date.strftime('%Y-%m-%d')
        attendance_data = firebase_service.get_attendance_by_employee_and_date(employee_id, date_str)
        if attendance_data:
            return FirebaseAttendance(attendance_data)
        return None
    
    @staticmethod
    def get_by_employee(employee_id: str, limit: int = 50) -> List['FirebaseAttendance']:
        """Get attendance records for an employee"""
        firebase_service = get_firebase_service()
        attendance_data_list = firebase_service.get_attendance_by_employee(employee_id, limit)
        return [FirebaseAttendance(data) for data in attendance_data_list]
    
    @staticmethod
    def get_by_date(date: datetime) -> List['FirebaseAttendance']:
        """Get all attendance records for a specific date"""
        firebase_service = get_firebase_service()
        date_str = date.strftime('%Y-%m-%d')
        attendance_data_list = firebase_service.get_attendance_by_date(date_str)
        return [FirebaseAttendance(data) for data in attendance_data_list]
    
    @staticmethod
    def get_recent(limit: int = 100) -> List['FirebaseAttendance']:
        """Get recent attendance records"""
        firebase_service = get_firebase_service()
        attendance_data_list = firebase_service.get_recent_attendance(limit)
        return [FirebaseAttendance(data) for data in attendance_data_list]
    
    def save(self) -> bool:
        """Save attendance to Firebase"""
        firebase_service = get_firebase_service()
        
        # Convert datetime objects to ISO strings for Firebase
        sign_in_time_str = None
        sign_out_time_str = None
        
        if isinstance(self.sign_in_time, datetime):
            sign_in_time_str = self.sign_in_time.isoformat()
        elif self.sign_in_time:
            sign_in_time_str = self.sign_in_time
            
        if isinstance(self.sign_out_time, datetime):
            sign_out_time_str = self.sign_out_time.isoformat()
        elif self.sign_out_time:
            sign_out_time_str = self.sign_out_time
        
        attendance_data = {
            'employee_id': self.employee_id,
            'date': self.date,
            'sign_in_time': sign_in_time_str,
            'sign_out_time': sign_out_time_str,
            'total_hours': self.total_hours,
            'work_location': self.work_location,
            'wfh_approved': self.wfh_approved
        }
        
        try:
            if self.id:
                # Update existing attendance
                return firebase_service.update_attendance(self.id, attendance_data)
            else:
                # Create new attendance
                doc_id = firebase_service.create_attendance(attendance_data)
                self.id = doc_id
                return True
        except Exception as e:
            print(f"❌ Error saving attendance: {e}")
            return False
    
    def get_sign_in_datetime(self) -> Optional[datetime]:
        """Get sign_in_time as datetime object"""
        if isinstance(self.sign_in_time, datetime):
            return self.sign_in_time
        elif isinstance(self.sign_in_time, str):
            try:
                return datetime.fromisoformat(self.sign_in_time.replace('Z', '+00:00'))
            except:
                return None
        return None
    
    def get_sign_out_datetime(self) -> Optional[datetime]:
        """Get sign_out_time as datetime object"""
        if isinstance(self.sign_out_time, datetime):
            return self.sign_out_time
        elif isinstance(self.sign_out_time, str):
            try:
                return datetime.fromisoformat(self.sign_out_time.replace('Z', '+00:00'))
            except:
                return None
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'employee_id': self.employee_id,
            'date': self.date,
            'sign_in_time': self.sign_in_time,
            'sign_out_time': self.sign_out_time,
            'total_hours': self.total_hours,
            'work_location': self.work_location,
            'wfh_approved': self.wfh_approved,
            'created_at': self.created_at
        }

class FirebaseTimesheet:
    """Firebase Timesheet model for daily reports"""
    
    def __init__(self, timesheet_data: Dict[str, Any]):
        self.id = timesheet_data.get('id')  # Firestore document ID
        self.employee_id = timesheet_data.get('employee_id')
        self.date = timesheet_data.get('date')  # String format: YYYY-MM-DD
        self.tasks_completed = timesheet_data.get('tasks_completed', '')
        self.challenges_faced = timesheet_data.get('challenges_faced', '')
        self.achievements = timesheet_data.get('achievements', '')
        self.tomorrow_plans = timesheet_data.get('tomorrow_plans', '')
        self.additional_notes = timesheet_data.get('additional_notes', '')
        self.submitted_at = timesheet_data.get('submitted_at')
        self.created_at = timesheet_data.get('created_at')
        self.updated_at = timesheet_data.get('updated_at')
    
    @staticmethod
    def find_by_employee_and_date(employee_id: str, date: datetime) -> Optional['FirebaseTimesheet']:
        """Find timesheet by employee and date"""
        firebase_service = get_firebase_service()
        date_str = date.strftime('%Y-%m-%d')
        timesheet_data = firebase_service.get_timesheet_by_employee_and_date(employee_id, date_str)
        if timesheet_data:
            return FirebaseTimesheet(timesheet_data)
        return None
    
    @staticmethod
    def get_by_employee(employee_id: str, limit: int = 50) -> List['FirebaseTimesheet']:
        """Get timesheet records for an employee"""
        firebase_service = get_firebase_service()
        timesheet_data_list = firebase_service.get_timesheets_by_employee(employee_id, limit)
        return [FirebaseTimesheet(data) for data in timesheet_data_list]
    
    @staticmethod
    def get_by_date(date: datetime) -> List['FirebaseTimesheet']:
        """Get all timesheet records for a specific date"""
        firebase_service = get_firebase_service()
        date_str = date.strftime('%Y-%m-%d')
        timesheet_data_list = firebase_service.get_timesheets_by_date(date_str)
        return [FirebaseTimesheet(data) for data in timesheet_data_list]
    
    @staticmethod
    def get_recent(limit: int = 100) -> List['FirebaseTimesheet']:
        """Get recent timesheet records"""
        firebase_service = get_firebase_service()
        timesheet_data_list = firebase_service.get_recent_timesheets(limit)
        return [FirebaseTimesheet(data) for data in timesheet_data_list]
    
    def save(self) -> bool:
        """Save timesheet to Firebase"""
        firebase_service = get_firebase_service()
        
        timesheet_data = {
            'employee_id': self.employee_id,
            'date': self.date,
            'tasks_completed': self.tasks_completed,
            'challenges_faced': self.challenges_faced,
            'achievements': self.achievements,
            'tomorrow_plans': self.tomorrow_plans,
            'additional_notes': self.additional_notes,
            'submitted_at': datetime.now().isoformat()
        }
        
        try:
            if self.id:
                # Update existing timesheet
                return firebase_service.update_timesheet(self.id, timesheet_data)
            else:
                # Create new timesheet
                doc_id = firebase_service.create_timesheet(timesheet_data)
                self.id = doc_id
                return True
        except Exception as e:
            print(f"❌ Error saving timesheet: {e}")
            return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'employee_id': self.employee_id,
            'date': self.date,
            'tasks_completed': self.tasks_completed,
            'challenges_faced': self.challenges_faced,
            'achievements': self.achievements,
            'tomorrow_plans': self.tomorrow_plans,
            'additional_notes': self.additional_notes,
            'submitted_at': self.submitted_at,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


# -------------------- Payroll Models --------------------
# Payroll models removed

class FirebaseWFHApproval:
    """Admin-approved Work-From-Home ranges"""
    def __init__(self, data: Dict[str, Any]):
        self.id = data.get('id')
        self.employee_id = data.get('employee_id')
        self.start_date = data.get('start_date')  # YYYY-MM-DD
        self.end_date = data.get('end_date')      # YYYY-MM-DD
        self.approved_by = data.get('approved_by')
        self.created_at = data.get('created_at')

    @staticmethod
    def approve(employee_id: str, start_date: str, end_date: str, approved_by: str) -> bool:
        service = get_firebase_service()
        try:
            doc_id = service.create_wfh_approval({
                'employee_id': employee_id,
                'start_date': start_date,
                'end_date': end_date,
                'approved_by': approved_by
            })
            return bool(doc_id)
        except Exception:
            return False

    @staticmethod
    def is_approved_for_date(employee_id: str, date_str: str) -> bool:
        service = get_firebase_service()
        approvals = service.get_wfh_approvals_by_employee(employee_id)
        for ap in approvals:
            s = ap.get('start_date')
            e = ap.get('end_date')
            if s and e and s <= date_str <= e:
                return True
        return False
