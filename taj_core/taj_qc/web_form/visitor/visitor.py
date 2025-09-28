# taj_core.taj_qc.doctype.web_form.visitor.visitor.py
import frappe
from frappe import _
from datetime import datetime
import json
import re

def get_context(context):
    """Get context for web form"""
    user_language = detect_user_language()
    context.current_language = user_language
    context.default_date = datetime.now().strftime('%Y-%m-%d')
    context.current_year = datetime.now().year
    
    # Add debug info
    context.debug_info = {
        'detected_language': user_language,
        'browser_language': frappe.local.request.headers.get('Accept-Language', '')
    }
    
    return context

def detect_user_language():
    """Detect user language from multiple sources"""
    # 1. Check URL parameter first
    lang = frappe.local.request.args.get('lang')
    if lang in ['ar', 'en']:
        return 'Ar' if lang == 'ar' else 'En'
    
    # 2. Check browser accept-language header
    accept_language = frappe.local.request.headers.get('Accept-Language', '')
    if accept_language:
        first_lang = accept_language.split(',')[0].split('-')[0].lower()
        if first_lang == 'ar':
            return 'Ar'
    
    # 3. Default to English
    return 'En'

@frappe.whitelist(allow_guest=True)
def save_visitor_draft(form_data):
    """Save visitor form as draft"""
    try:
        if isinstance(form_data, str):
            form_data = json.loads(form_data)
        
        # Validate required fields
        if not form_data.get('full_name'):
            return {'success': False, 'error': 'Full name is required'}
        
        # Validate email format if provided
        email = form_data.get('email')
        if email and not is_valid_email(email):
            return {'success': False, 'error': 'Invalid email format'}
        
        # Create or update visitor document
        visitor_name = form_data.get('name')
        if visitor_name and frappe.db.exists('Visitor', visitor_name):
            visitor = frappe.get_doc('Visitor', visitor_name)
            visitor.update(form_data)
        else:
            visitor = frappe.new_doc('Visitor')
            visitor.update(form_data)
        
        visitor.flags.ignore_permissions = True
        visitor.flags.ignore_mandatory = True
        
        if visitor_name:
            visitor.save()
        else:
            visitor.insert()
        
        return {'success': True, 'name': visitor.name}
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), 'Visitor Draft Save Error')
        return {'success': False, 'error': str(e)}

@frappe.whitelist(allow_guest=True)
def validate_visitor_data(form_data):
    """Validate visitor data before submission"""
    try:
        if isinstance(form_data, str):
            form_data = json.loads(form_data)
        
        errors = []
        
        # Validate required fields
        if not form_data.get('full_name'):
            errors.append('Full name is required')
        
        # Validate email format
        email = form_data.get('email')
        if email and not is_valid_email(email):
            errors.append('Please enter a valid email address')
        
        # Validate health questions logic
        if form_data.get('abroad') and not form_data.get('ill'):
            errors.append('Please specify if you were ill during your travel abroad')
        
        if errors:
            return {'valid': False, 'errors': errors}
        else:
            return {'valid': True}
            
    except Exception as e:
        return {'valid': False, 'errors': [str(e)]}

def is_valid_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

@frappe.whitelist(allow_guest=True)
def record_language_preference(visitor_name, language):
    """Record language preference for statistics"""
    try:
        visitor = frappe.get_doc('Visitor', visitor_name)
        visitor.language_preference = language
        visitor.flags.ignore_permissions = True
        visitor.save()
        return True
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), 'Language Preference Error')
        return False

@frappe.whitelist(allow_guest=True)
def send_confirmation_email(visitor_name):
    """Send confirmation email to visitor"""
    try:
        visitor = frappe.get_doc('Visitor', visitor_name)
        
        if visitor.email:
            # Determine email language
            language = visitor.language_preference or 'En'
            
            if language == 'Ar':
                subject = 'تأكيد تسجيل الزائر'
                message = f"""
                السيد/ة {visitor.full_name}،
                
                نشكرك على التسجيل كزائر. تم تسجيل معلوماتك بنجاح.
                
                تفاصيل التسجيل:
                - الاسم: {visitor.full_name}
                - الشركة: {visitor.company or 'غير محدد'}
                - الغرض: {visitor.purpose_of_visit or 'غير محدد'}
                - التاريخ: {visitor.post_date}
                - رقم التسجيل: {visitor.name}
                
                مع أطيب التحيات،
                نظام إدارة الزوار
                """
            else:
                subject = 'Visitor Registration Confirmation'
                message = f"""
                Dear {visitor.full_name},
                
                Thank you for registering as a visitor. Your information has been recorded.
                
                Registration Details:
                - Name: {visitor.full_name}
                - Company: {visitor.company or 'N/A'}
                - Purpose: {visitor.purpose_of_visit or 'N/A'}
                - Date: {visitor.post_date}
                - Registration ID: {visitor.name}
                
                Best regards,
                Visitor Management System
                """
            
            frappe.sendmail(
                recipients=[visitor.email],
                subject=subject,
                message=message,
                now=True
            )
            
            return {'success': True, 'message': 'Confirmation email sent'}
        else:
            return {'success': False, 'message': 'No email address provided'}
            
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), 'Visitor Email Error')
        return {'success': False, 'error': str(e)}

@frappe.whitelist()
def get_visitor_statistics():
    """Get statistics for visitors (admin use only)"""
    if not frappe.has_permission('Visitor', 'read'):
        frappe.throw(_('Not permitted'), frappe.PermissionError)
    
    today = datetime.now().strftime('%Y-%m-%d')
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    statistics = {
        'total_visitors': frappe.db.count('Visitor'),
        'today_visitors': frappe.db.count('Visitor', {'post_date': today}),
        'last_7_days': frappe.db.count('Visitor', {
            'post_date': ['>=', week_ago]
        }),
        'with_health_issues': frappe.db.count('Visitor', {
            'typhoid_or_paratyphoid': 1
        }),
        'international_visitors': frappe.db.count('Visitor', {
            'abroad': 1
        }),
        'arabic_speaking': frappe.db.count('Visitor', {
            'language_preference': 'Ar'
        }),
        'english_speaking': frappe.db.count('Visitor', {
            'language_preference': 'En'
        })
    }
    
    return statistics

@frappe.whitelist()
def generate_visitor_pass(visitor_name):
    """Generate PDF visitor pass"""
    try:
        from frappe.utils.pdf import get_pdf
        
        visitor = frappe.get_doc('Visitor', visitor_name)
        
        # Determine pass language
        language = visitor.language_preference or 'En'
        
        context = {
            'visitor': visitor,
            'language': language,
            'generated_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'company_logo': '/assets/frappe/images/frappe-framework-logo.png'
        }
        
        html = frappe.render_template('taj_core/templates/visitor_pass.html', context)
        pdf = get_pdf(html)
        
        return {
            'pdf_content': pdf,
            'visitor_name': visitor.name,
            'file_name': f'visitor_pass_{visitor.name}.pdf'
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), 'Visitor Pass Generation Error')
        return {'error': str(e)}

@frappe.whitelist(allow_guest=True)
def get_translation_strings(language='En'):
    """API endpoint to get translation strings for frontend"""
    translations = {
        'En': {
            'validation_errors': {
                'required_field': 'This field is required',
                'invalid_email': 'Please enter a valid email address',
                'health_question_required': 'Please answer all health questions'
            },
            'success_messages': {
                'registration_success': 'Registration completed successfully',
                'draft_saved': 'Draft saved successfully'
            },
            'labels': {
                'visitor_id': 'Visitor ID',
                'registration_date': 'Registration Date'
            }
        },
        'Ar': {
            'validation_errors': {
                'required_field': 'هذا الحقل مطلوب',
                'invalid_email': 'يرجى إدخال بريد إلكتروني صحيح',
                'health_question_required': 'يرجى الإجابة على جميع الأسئلة الصحية'
            },
            'success_messages': {
                'registration_success': 'تم التسجيل بنجاح',
                'draft_saved': 'تم حفظ المسودة بنجاح'
            },
            'labels': {
                'visitor_id': 'رقم الزائر',
                'registration_date': 'تاريخ التسجيل'
            }
        }
    }
    return translations.get(language, translations['En'])