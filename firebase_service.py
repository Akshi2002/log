import firebase_admin
from firebase_admin import credentials, firestore
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

class FirebaseService:
    """Firebase Firestore service for attendance system"""
    
    def __init__(self):
        self.db = None
        self.initialize_firebase()
    
    def initialize_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            # Check if Firebase is already initialized
            firebase_admin.get_app()
        except ValueError:
            # Firebase not initialized, so initialize it
            
            # Option 1: Use environment variable (for production deployment)
            firebase_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
            if firebase_json:
                import json
                try:
                    service_account_info = json.loads(firebase_json)
                    cred = credentials.Certificate(service_account_info)
                    firebase_admin.initialize_app(cred)
                    print("✅ Firebase initialized with environment variable")
                except Exception as e:
                    print(f"❌ Failed to initialize Firebase with environment variable: {e}")
                    print("⚠️ Continuing without Firebase - app will use SQLite fallback")
                    return
            
            # Option 2: Use service account key file (for local development)
            service_account_path = os.path.join(os.path.dirname(__file__), 'firebase-service-account.json')
            
            if os.path.exists(service_account_path):
                # Use service account file
                cred = credentials.Certificate(service_account_path)
                firebase_admin.initialize_app(cred)
                print("✅ Firebase initialized with service account")
            else:
                # Option 2: Use environment variables (for local development)
                try:
                    # Create credentials from environment variables
                    firebase_config = {
                        "type": "service_account",
                        "project_id": "duty-login",
                        "private_key_id": os.environ.get('FIREBASE_PRIVATE_KEY_ID'),
                        "private_key": os.environ.get('FIREBASE_PRIVATE_KEY', '').replace('\\n', '\n'),
                        "client_email": os.environ.get('FIREBASE_CLIENT_EMAIL'),
                        "client_id": os.environ.get('FIREBASE_CLIENT_ID'),
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                        "client_x509_cert_url": os.environ.get('FIREBASE_CLIENT_CERT_URL')
                    }
                    
                    if firebase_config['private_key']:
                        cred = credentials.Certificate(firebase_config)
                        firebase_admin.initialize_app(cred)
                        print("✅ Firebase initialized with environment variables")
                    else:
                        # Option 3: Use Application Default Credentials (for Google Cloud)
                        cred = credentials.ApplicationDefault()
                        firebase_admin.initialize_app(cred, {
                            'projectId': 'duty-login',
                        })
                        print("✅ Firebase initialized with Application Default Credentials")
                
                except Exception as e:
                    print(f"❌ Firebase initialization failed: {e}")
                    print("Please set up Firebase credentials (see README)")
                    print("🔧 Attempting simplified setup...")
                    # Try with just project ID
                    try:
                        cred = credentials.ApplicationDefault()
                        firebase_admin.initialize_app(cred, {
                            'projectId': 'duty-login',
                        })
                        print("✅ Firebase initialized with minimal credentials")
                    except Exception as e2:
                        print(f"❌ Simplified setup also failed: {e2}")
                        raise
        
        # Get Firestore client only if Firebase is properly initialized
        try:
            self.db = firestore.client()
            print(f"🔥 Connected to Firestore database: duty-login")
        except Exception as e:
            print(f"❌ Failed to connect to Firestore: {e}")
            print("⚠️ Firebase will not be available - app will use SQLite fallback")
            self.db = None
    
    # Employee CRUD Operations
    def create_employee(self, employee_data: Dict[str, Any]) -> str:
        """Create a new employee in Firestore"""
        if not self.db:
            raise Exception("Firebase not available - use SQLite fallback")
        try:
            doc_ref = self.db.collection('employees').document()
            employee_data['created_at'] = firestore.SERVER_TIMESTAMP
            employee_data['updated_at'] = firestore.SERVER_TIMESTAMP
            doc_ref.set(employee_data)
            print(f"✅ Employee created with ID: {doc_ref.id}")
            return doc_ref.id
        except Exception as e:
            print(f"❌ Error creating employee: {e}")
            raise
    
    def get_employee_by_id(self, employee_id: str) -> Optional[Dict[str, Any]]:
        """Get employee by employee_id field"""
        try:
            employees = self.db.collection('employees').where('employee_id', '==', employee_id).get()
            for employee in employees:
                employee_data = employee.to_dict()
                employee_data['id'] = employee.id
                return employee_data
            return None
        except Exception as e:
            print(f"❌ Error getting employee: {e}")
            return None
    
    def get_employee_by_doc_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get employee by Firestore document ID"""
        try:
            doc = self.db.collection('employees').document(doc_id).get()
            if doc.exists:
                employee_data = doc.to_dict()
                employee_data['id'] = doc.id
                return employee_data
            return None
        except Exception as e:
            print(f"❌ Error getting employee by doc ID: {e}")
            return None
    
    def get_all_employees(self) -> List[Dict[str, Any]]:
        """Get all employees"""
        try:
            employees = []
            docs = self.db.collection('employees').get()
            for doc in docs:
                employee_data = doc.to_dict()
                employee_data['id'] = doc.id
                employees.append(employee_data)
            return employees
        except Exception as e:
            print(f"❌ Error getting all employees: {e}")
            return []
    
    def update_employee(self, doc_id: str, update_data: Dict[str, Any]) -> bool:
        """Update employee data"""
        try:
            update_data['updated_at'] = firestore.SERVER_TIMESTAMP
            self.db.collection('employees').document(doc_id).update(update_data)
            print(f"✅ Employee {doc_id} updated successfully")
            return True
        except Exception as e:
            print(f"❌ Error updating employee: {e}")
            return False
    
    def delete_employee(self, doc_id: str) -> bool:
        """Delete employee and all their attendance records"""
        try:
            # Get employee data first
            employee = self.get_employee_by_doc_id(doc_id)
            if not employee:
                print(f"❌ Employee {doc_id} not found")
                return False
            
            employee_id = employee.get('employee_id')
            
            # Delete all attendance records for this employee
            attendance_docs = self.db.collection('attendance').where('employee_id', '==', employee_id).get()
            for doc in attendance_docs:
                doc.reference.delete()
            
            # Delete the employee
            self.db.collection('employees').document(doc_id).delete()
            print(f"✅ Employee {doc_id} and their attendance records deleted")
            return True
        except Exception as e:
            print(f"❌ Error deleting employee: {e}")
            return False
    
    # Admin CRUD Operations
    def create_admin(self, admin_data: Dict[str, Any]) -> str:
        """Create a new admin in Firestore"""
        try:
            doc_ref = self.db.collection('admins').document()
            admin_data['created_at'] = firestore.SERVER_TIMESTAMP
            admin_data['updated_at'] = firestore.SERVER_TIMESTAMP
            doc_ref.set(admin_data)
            print(f"✅ Admin created with ID: {doc_ref.id}")
            return doc_ref.id
        except Exception as e:
            print(f"❌ Error creating admin: {e}")
            raise
    
    def get_admin_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get admin by username"""
        try:
            admins = self.db.collection('admins').where('username', '==', username).get()
            for admin in admins:
                admin_data = admin.to_dict()
                admin_data['id'] = admin.id
                return admin_data
            return None
        except Exception as e:
            print(f"❌ Error getting admin: {e}")
            return None
    
    def get_admin_by_doc_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get admin by Firestore document ID"""
        try:
            doc = self.db.collection('admins').document(doc_id).get()
            if doc.exists:
                admin_data = doc.to_dict()
                admin_data['id'] = doc.id
                return admin_data
            return None
        except Exception as e:
            print(f"❌ Error getting admin by doc ID: {e}")
            return None
    
    # Attendance CRUD Operations
    def create_attendance(self, attendance_data: Dict[str, Any]) -> str:
        """Create attendance record"""
        try:
            doc_ref = self.db.collection('attendance').document()
            attendance_data['created_at'] = firestore.SERVER_TIMESTAMP
            doc_ref.set(attendance_data)
            print(f"✅ Attendance record created with ID: {doc_ref.id}")
            return doc_ref.id
        except Exception as e:
            print(f"❌ Error creating attendance: {e}")
            raise
    
    def get_attendance_by_employee_and_date(self, employee_id: str, date_str: str) -> Optional[Dict[str, Any]]:
        """Get attendance record for specific employee and date"""
        try:
            attendance_docs = (self.db.collection('attendance')
                             .where('employee_id', '==', employee_id)
                             .where('date', '==', date_str)
                             .get())
            
            for doc in attendance_docs:
                attendance_data = doc.to_dict()
                attendance_data['id'] = doc.id
                return attendance_data
            return None
        except Exception as e:
            print(f"❌ Error getting attendance: {e}")
            return None
    
    def get_attendance_by_employee(self, employee_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get attendance records for an employee"""
        try:
            print(f"DEBUG: Querying attendance for employee_id: {employee_id}")
            attendance_records = []
            
            # Try without ordering first to see if records exist
            docs = (self.db.collection('attendance')
                   .where('employee_id', '==', employee_id)
                   .limit(limit)
                   .get())
            
            print(f"DEBUG: Found {len(docs)} documents (without ordering)")
            
            for doc in docs:
                attendance_data = doc.to_dict()
                attendance_data['id'] = doc.id
                attendance_records.append(attendance_data)
                print(f"DEBUG: Document data: {attendance_data}")
            
            # Sort by date in Python if we have records
            if attendance_records:
                attendance_records.sort(key=lambda x: x.get('date', ''), reverse=True)
                print(f"DEBUG: Sorted records by date")
            
            print(f"DEBUG: Returning {len(attendance_records)} attendance records")
            return attendance_records
        except Exception as e:
            print(f"❌ Error getting employee attendance: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_attendance_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        """Get all attendance records for a specific date"""
        try:
            attendance_records = []
            docs = self.db.collection('attendance').where('date', '==', date_str).get()
            
            for doc in docs:
                attendance_data = doc.to_dict()
                attendance_data['id'] = doc.id
                attendance_records.append(attendance_data)
            
            return attendance_records
        except Exception as e:
            print(f"❌ Error getting attendance by date: {e}")
            return []
    
    def get_recent_attendance(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent attendance records"""
        try:
            attendance_records = []
            docs = (self.db.collection('attendance')
                   .order_by('date', direction=firestore.Query.DESCENDING)
                   .limit(limit)
                   .get())
            
            for doc in docs:
                attendance_data = doc.to_dict()
                attendance_data['id'] = doc.id
                attendance_records.append(attendance_data)
            
            return attendance_records
        except Exception as e:
            print(f"❌ Error getting recent attendance: {e}")
            return []
    
    def update_attendance(self, doc_id: str, update_data: Dict[str, Any]) -> bool:
        """Update attendance record"""
        try:
            self.db.collection('attendance').document(doc_id).update(update_data)
            print(f"✅ Attendance {doc_id} updated successfully")
            return True
        except Exception as e:
            print(f"❌ Error updating attendance: {e}")
            return False
    
    # Timesheet CRUD Operations
    def create_timesheet(self, timesheet_data: Dict[str, Any]) -> str:
        """Create timesheet record"""
        try:
            doc_ref = self.db.collection('timesheets').document()
            timesheet_data['created_at'] = firestore.SERVER_TIMESTAMP
            timesheet_data['updated_at'] = firestore.SERVER_TIMESTAMP
            doc_ref.set(timesheet_data)
            print(f"✅ Timesheet record created with ID: {doc_ref.id}")
            return doc_ref.id
        except Exception as e:
            print(f"❌ Error creating timesheet: {e}")
            raise
    
    def get_timesheet_by_employee_and_date(self, employee_id: str, date_str: str) -> Optional[Dict[str, Any]]:
        """Get timesheet record for specific employee and date"""
        try:
            timesheet_docs = (self.db.collection('timesheets')
                            .where('employee_id', '==', employee_id)
                            .where('date', '==', date_str)
                            .get())
            
            for doc in timesheet_docs:
                timesheet_data = doc.to_dict()
                timesheet_data['id'] = doc.id
                return timesheet_data
            return None
        except Exception as e:
            print(f"❌ Error getting timesheet: {e}")
            return None
    
    def get_timesheets_by_employee(self, employee_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get timesheet records for an employee"""
        try:
            print(f"DEBUG: Querying timesheets for employee_id: {employee_id}")
            timesheet_records = []
            
            docs = (self.db.collection('timesheets')
                   .where('employee_id', '==', employee_id)
                   .limit(limit)
                   .get())
            
            print(f"DEBUG: Found {len(docs)} timesheet documents")
            
            for doc in docs:
                timesheet_data = doc.to_dict()
                timesheet_data['id'] = doc.id
                timesheet_records.append(timesheet_data)
            
            # Sort by date in Python
            if timesheet_records:
                timesheet_records.sort(key=lambda x: x.get('date', ''), reverse=True)
            
            print(f"DEBUG: Returning {len(timesheet_records)} timesheet records")
            return timesheet_records
        except Exception as e:
            print(f"❌ Error getting employee timesheets: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_timesheets_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        """Get all timesheet records for a specific date"""
        try:
            timesheet_records = []
            docs = self.db.collection('timesheets').where('date', '==', date_str).get()
            
            for doc in docs:
                timesheet_data = doc.to_dict()
                timesheet_data['id'] = doc.id
                timesheet_records.append(timesheet_data)
            
            return timesheet_records
        except Exception as e:
            print(f"❌ Error getting timesheets by date: {e}")
            return []
    
    def get_recent_timesheets(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent timesheet records"""
        try:
            timesheet_records = []
            docs = (self.db.collection('timesheets')
                   .order_by('date', direction=firestore.Query.DESCENDING)
                   .limit(limit)
                   .get())
            
            for doc in docs:
                timesheet_data = doc.to_dict()
                timesheet_data['id'] = doc.id
                timesheet_records.append(timesheet_data)
            
            return timesheet_records
        except Exception as e:
            print(f"❌ Error getting recent timesheets: {e}")
            return []
    
    def update_timesheet(self, doc_id: str, update_data: Dict[str, Any]) -> bool:
        """Update timesheet record"""
        try:
            update_data['updated_at'] = firestore.SERVER_TIMESTAMP
            self.db.collection('timesheets').document(doc_id).update(update_data)
            print(f"✅ Timesheet {doc_id} updated successfully")
            return True
        except Exception as e:
            print(f"❌ Error updating timesheet: {e}")
            return False

    # WFH Approvals
    def create_wfh_approval(self, approval_data: Dict[str, Any]) -> str:
        try:
            doc_ref = self.db.collection('wfh_approvals').document()
            approval_data['created_at'] = firestore.SERVER_TIMESTAMP
            doc_ref.set(approval_data)
            print(f"✅ WFH approval created with ID: {doc_ref.id}")
            return doc_ref.id
        except Exception as e:
            print(f"❌ Error creating WFH approval: {e}")
            raise

    def get_wfh_approvals_by_employee(self, employee_id: str) -> List[Dict[str, Any]]:
        try:
            docs = (self.db.collection('wfh_approvals')
                    .where('employee_id', '==', employee_id)
                    .get())
            approvals = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                approvals.append(data)
            return approvals
        except Exception as e:
            print(f"❌ Error fetching WFH approvals: {e}")
            return []

    def get_all_wfh_approvals(self) -> List[Dict[str, Any]]:
        """Return all WFH approvals (unsorted)"""
        try:
            docs = self.db.collection('wfh_approvals').get()
            approvals = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                approvals.append(data)
            # Sort by start_date desc if present
            approvals.sort(key=lambda x: x.get('start_date', ''), reverse=True)
            return approvals
        except Exception as e:
            print(f"❌ Error fetching all WFH approvals: {e}")
            return []

# -------------------- Payroll Collections --------------------
    # Payroll features removed

# Global Firebase service instance
firebase_service = None

def get_firebase_service():
    """Get or create Firebase service instance"""
    global firebase_service
    if firebase_service is None:
        firebase_service = FirebaseService()
    return firebase_service

