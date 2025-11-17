import re
import mimetypes
from werkzeug.utils import secure_filename

# File validation constants
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB per file
MAX_TOTAL_SIZE = 50 * 1024 * 1024  # 50MB total
ALLOWED_EXTENSIONS = {
    'pdf', 'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff',
    'xlsx', 'xls', 'csv', 'doc', 'docx', 'txt'
}
ALLOWED_MIMETYPES = {
    'application/pdf',
    'image/png', 'image/jpeg', 'image/gif', 'image/bmp', 'image/tiff',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel',
    'text/csv',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'text/plain'
}

# Text validation constants
MAX_NAME_LENGTH = 100
MAX_EMAIL_LENGTH = 255
MAX_TEXT_FIELD_LENGTH = 500
MAX_COMMENTS_LENGTH = 2000

def sanitize_html(text):
    """Remove HTML tags and dangerous characters from text input"""
    if not text:
        return text
    
    # Remove HTML tags
    text = re.sub(r'<[^>]*>', '', str(text))
    
    # Remove common XSS patterns
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'on\w+\s*=', '', text, flags=re.IGNORECASE)
    
    # Normalize whitespace
    text = ' '.join(text.split())
    
    return text.strip()

def validate_email(email):
    """Validate email format"""
    if not email or len(email) > MAX_EMAIL_LENGTH:
        return False
    
    # Basic email regex - not perfect but catches most invalid formats
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_pattern, email) is not None

def validate_decimal(value, field_name="amount"):
    """Validate that a value is a valid decimal number"""
    if not value:
        return False, f"{field_name} is required"
    
    try:
        decimal_val = float(value)
        if decimal_val < 0:
            return False, f"{field_name} cannot be negative"
        if decimal_val > 1000000:  # Sanity check: no single expense over $1M
            return False, f"{field_name} exceeds maximum allowed value"
        return True, decimal_val
    except (ValueError, TypeError):
        return False, f"{field_name} must be a valid number"

def validate_text_field(text, field_name, max_length=MAX_TEXT_FIELD_LENGTH, required=True):
    """Validate and sanitize text fields"""
    if not text or not text.strip():
        if required:
            return False, f"{field_name} is required"
        return True, ""
    
    sanitized = sanitize_html(text)
    
    if len(sanitized) > max_length:
        return False, f"{field_name} exceeds maximum length of {max_length} characters"
    
    return True, sanitized

def get_file_extension(filename):
    """Safely extract file extension"""
    if '.' not in filename:
        return None
    return filename.rsplit('.', 1)[1].lower()

def sanitize_filename(filename):
    """Sanitize filename to prevent path traversal and other issues"""
    # Use werkzeug's secure_filename as base
    safe_name = secure_filename(filename)
    
    # Additional checks
    if not safe_name or safe_name == '':
        return None
    
    # Limit filename length (keeping extension)
    name_part, ext = safe_name.rsplit('.', 1) if '.' in safe_name else (safe_name, '')
    if len(name_part) > 200:
        name_part = name_part[:200]
    
    return f"{name_part}.{ext}" if ext else name_part

def validate_file(file_data, filename):
    """
    Validate uploaded file for size, type, and content
    Returns: (success: bool, error_message: str, sanitized_filename: str)
    """
    # Check if file exists
    if not file_data or not filename:
        return False, "No file provided", None
    
    # Sanitize filename
    safe_filename = sanitize_filename(filename)
    if not safe_filename:
        return False, f"Invalid filename: {filename}", None
    
    # Check file extension
    extension = get_file_extension(safe_filename)
    if not extension or extension not in ALLOWED_EXTENSIONS:
        return False, f"File type not allowed: .{extension}. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}", None
    
    # Check MIME type (from Content-Type header)
    content_type = file_data.content_type
    if content_type not in ALLOWED_MIMETYPES:
        # Try to guess from filename as fallback
        guessed_type, _ = mimetypes.guess_type(safe_filename)
        if not guessed_type or guessed_type not in ALLOWED_MIMETYPES:
            return False, f"File MIME type not allowed: {content_type}", None
    
    # Check file size
    file_data.seek(0, 2)  # Seek to end
    file_size = file_data.tell()
    file_data.seek(0)  # Reset to beginning
    
    if file_size > MAX_FILE_SIZE:
        return False, f"File too large: {filename} ({file_size / 1024 / 1024:.1f}MB). Maximum size is {MAX_FILE_SIZE / 1024 / 1024}MB per file", None
    
    if file_size == 0:
        return False, f"File is empty: {filename}", None
    
    return True, "", safe_filename

def validate_total_file_size(files):
    """Validate total size of all uploaded files"""
    total_size = 0
    
    for key in files:
        file_data = files[key]
        if file_data.filename:
            file_data.seek(0, 2)
            total_size += file_data.tell()
            file_data.seek(0)
    
    if total_size > MAX_TOTAL_SIZE:
        return False, f"Total file size too large ({total_size / 1024 / 1024:.1f}MB). Maximum total size is {MAX_TOTAL_SIZE / 1024 / 1024}MB"
    
    return True, ""

def validate_form_data(endpoint, data):
    """
    Validate and sanitize all form data
    Returns: (success: bool, error_message: str, sanitized_data: dict)
    """
    sanitized = {}
    
    # Validate and sanitize firstName
    valid, result = validate_text_field(data.get('firstName'), 'First name', MAX_NAME_LENGTH)
    if not valid:
        return False, result, None
    sanitized['firstName'] = result
    
    # Validate and sanitize lastName
    valid, result = validate_text_field(data.get('lastName'), 'Last name', MAX_NAME_LENGTH)
    if not valid:
        return False, result, None
    sanitized['lastName'] = result
    
    # Validate email
    email = data.get('email', '').strip()
    if not validate_email(email):
        return False, 'Invalid email address', None
    sanitized['email'] = email
    
    # Validate and sanitize comments (optional field)
    valid, result = validate_text_field(data.get('comments', ''), 'Comments', MAX_COMMENTS_LENGTH, required=False)
    if not valid:
        return False, result, None
    sanitized['comments'] = result
    
    # Validate expenses
    expenses = data.get('expenses', [])
    if not expenses or not isinstance(expenses, list):
        return False, 'At least one expense is required', None
    
    sanitized_expenses = []
    for i, expense in enumerate(expenses, 1):
        sanitized_expense = {}
        
        # Validate vendor
        valid, result = validate_text_field(expense.get('vendor'), f'Vendor (expense {i})', MAX_TEXT_FIELD_LENGTH)
        if not valid:
            return False, result, None
        sanitized_expense['vendor'] = result
        
        # Validate description
        valid, result = validate_text_field(expense.get('description'), f'Description (expense {i})', MAX_TEXT_FIELD_LENGTH)
        if not valid:
            return False, result, None
        sanitized_expense['description'] = result
        
        # Validate amount
        valid, result = validate_decimal(expense.get('amount'), f'Amount (expense {i})')
        if not valid:
            return False, result, None
        sanitized_expense['amount'] = str(result)  # Store as string for consistency
        
        # Endpoint-specific fields
        if endpoint == "Reimbursement Request":
            # Validate approval field
            valid, result = validate_text_field(expense.get('approval'), f'Approval/Project (expense {i})', MAX_TEXT_FIELD_LENGTH)
            if not valid:
                return False, result, None
            sanitized_expense['approval'] = result
            
            # Validate HST
            hst_value = expense.get('hst', '')
            valid_hst_options = [
                'HST included in amount',
                'HST excluded from amount',
                'HST not charged'
            ]
            if hst_value not in valid_hst_options:
                return False, f'Invalid HST value (expense {i})', None
            sanitized_expense['hst'] = hst_value
        
        sanitized_expenses.append(sanitized_expense)
    
    sanitized['expenses'] = sanitized_expenses
    
    return True, "", sanitized