// taj_core.taj_qc.doctype.web_form.visitor.visitor.js
frappe.ready(function() {
    console.log('Visitor form JavaScript loaded successfully');
    
    // تهيئة فورية
    initialize_application();
});

function initialize_application() {
    console.log('Initializing application...');
    
    // 1. إنشاء زر اللغة أولاً
    create_reliable_language_switcher();
    
    // 2. إخفاء العناصر غير المرغوب فيها
    hide_unwanted_elements();
    
    // 3. تعيين اللغة الحالية
    set_current_language();
    
    // 4. إعداد الأنظمة الأخرى
    setup_other_systems();
    
    // 5. إعداد مراقب للتأكد من استمرارية عمل زر اللغة
    setup_language_monitor();
}

function create_reliable_language_switcher() {
    console.log('Creating reliable language switcher...');
    
    // إزالة أي مبدل لغة موجود مسبقاً
    $('.language-switcher').remove();
    
    const saved_lang = localStorage.getItem('visitor_language') || 'En';
    const label_text = saved_lang === 'Ar' ? 'اللغة:' : 'Language:';
    
    const language_switcher = `
        <div class="language-switcher" id="main_language_switcher" style="
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
            border: 2px solid #007bff;
            min-width: 200px;
            text-align: center;
        ">
            <label for="language_select" class="language-label" style="
                display: block;
                font-weight: bold;
                margin-bottom: 8px;
                color: #333;
                font-size: 14px;
            ">${label_text}</label>
            <select id="language_select" class="language-select" style="
                display: block;
                width: 100%;
                padding: 10px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background: white;
                font-size: 14px;
                cursor: pointer;
            ">
                <option value="En" ${saved_lang === 'En' ? 'selected' : ''}>English</option>
                <option value="Ar" ${saved_lang === 'Ar' ? 'selected' : ''}>العربية</option>
            </select>
        </div>
    `;
    
    // إضافة زر اللغة إلى body مباشرة
    $('body').prepend(language_switcher);
    
    // إعداد event handler موثوق
    setup_reliable_language_handler();
}

function setup_reliable_language_handler() {
    console.log('Setting up reliable language handler...');
    
    // طريقة 1: استخدام jQuery event delegation على document
    $(document).off('change', '#language_select').on('change', '#language_select', function(e) {
        console.log('Language select changed via delegation');
        const selected_lang = $(this).val();
        handle_language_change(selected_lang);
    });
    
    // طريقة 2: استخدام event handler مباشر
    $('#language_select').off('change').on('change', function(e) {
        console.log('Language select changed via direct handler');
        const selected_lang = $(this).val();
        handle_language_change(selected_lang);
    });
    
    // طريقة 3: استخدام JavaScript vanilla
    document.getElementById('language_select')?.addEventListener('change', function(e) {
        console.log('Language select changed via vanilla JS');
        const selected_lang = e.target.value;
        handle_language_change(selected_lang);
    });
    
    // طريقة 4: إضافة click event كنسخة احتياطية
    $('#language_select').off('click').on('click', function(e) {
        console.log('Language select clicked');
        // لا نوقف الحدث، فقط للتتبع
    });
}

function handle_language_change(selected_lang) {
    console.log('Handling language change to:', selected_lang);
    
    // 1. تحديث localStorage فوراً
    localStorage.setItem('visitor_language', selected_lang);
    console.log('Language saved to localStorage:', selected_lang);
    
    // 2. تحديث تسمية زر اللغة
    $('.language-label').text(selected_lang === 'Ar' ? 'اللغة:' : 'Language:');
    
    // 3. تحديث حقل اللغة في النموذج
    update_language_field(selected_lang);
    
    // 4. تحديث واجهة المستخدم
    update_entire_interface(selected_lang);
    
    // 5. إظهار تأكيد
    show_language_change_confirmation(selected_lang);
}

function update_language_field(selected_lang) {
    // محاولة تحديث حقل اللغة في النموذج بعدة طرق
    try {
        // الطريقة 1: استخدام Frappe web_form
        const language_field = frappe.web_form.get_field('language');
        if (language_field) {
            language_field.set_value(selected_lang);
            console.log('Language field updated via Frappe');
        }
        
        // الطريقة 2: تحديث مباشر للعنصر
        $('[data-fieldname="language"] input').val(selected_lang);
        console.log('Language field updated via direct DOM');
        
        // الطريقة 3: trigger event للتحديث
        $('[data-fieldname="language"] input').trigger('change');
        
    } catch (error) {
        console.log('Error updating language field:', error);
    }
}

function update_entire_interface(selected_lang) {
    console.log('Updating entire interface for language:', selected_lang);
    
    const lang_dict = translations[selected_lang];
    
    // 1. تحديث عنوان الصفحة
    document.title = lang_dict['Visitor Registration'];
    
    // 2. تحديث العنوان الرئيسي
    $('.web-form-title h1, h1').each(function() {
        const $el = $(this);
        const current_text = $el.text().trim();
        if (current_text.includes('Visitor Registration') || current_text.includes('تسجيل الزائر')) {
            $el.text(lang_dict['Visitor Registration']);
        }
    });
    
    // 3. تحديث الوصف
    $('.web-form-introduction .ql-editor p, .introduction-text, .web-form-description').each(function() {
        const $el = $(this);
        const current_text = $el.text().trim();
        if (current_text.includes('Please fill in your information below to register') || 
            current_text.includes('يرجى ملء المعلومات أدناه للتسجيل')) {
            $el.text(lang_dict['Please fill in your information below to register.']);
        }
    });
    
    // 4. تحديث تسميات الحقول
    update_all_field_labels(lang_dict);
    
    // 5. تحديث عناوين الأقسام
    update_all_sections(lang_dict);
    
    // 6. تحديث الأزرار
    update_all_buttons(lang_dict);
    
    // 7. تحديث اتجاه الصفحة
    update_page_direction(selected_lang);
    
    // 8. تحديث خيارات Select
    update_select_fields(selected_lang);
    
    console.log('Interface update completed');
}

function update_all_field_labels(lang_dict) {
    console.log('Updating all field labels...');
    
    const field_map = {
        'language': 'Language',
        'post_date': 'Post Date',
        'full_name': 'Full Name',
        'company': 'Company',
        'purpose_of_visit': 'Purpose of Visit',
        'email': 'Email',
        'typhoid_or_paratyphoid': 'Typhoid / Paratyphoid last 3 month',
        'vomiting': 'Vomiting / Diarrhea last 7 days',
        'abroad': 'Been abroad last 3 weeks',
        'ill': 'If abroad, were you ill',
        'burnes': 'Suffering from',
        'skin_or_gastrointestinal': 'Chronic disorder',
        'answered_yes': 'Additional info if answered YES'
    };
    
    Object.keys(field_map).forEach(field_name => {
        const english_text = field_map[field_name];
        const translated_text = lang_dict[english_text];
        
        if (translated_text) {
            // تحديث جميع العناصر المحتملة لهذا الحقل
            const selectors = [
                `[data-fieldname="${field_name}"] .control-label`,
                `[data-fieldname="${field_name}"] .label-area`,
                `label[for="${field_name}"]`,
                `[data-fieldname="${field_name}"] .ellipsis`
            ];
            
            selectors.forEach(selector => {
                $(selector).each(function() {
                    $(this).text(translated_text);
                });
            });
        }
    });
}

function update_all_sections(lang_dict) {
    console.log('Updating all sections...');
    
    // تحديث أقسام النموذج
    $('.section-head, legend, .section-title, .form-section').each(function() {
        const $section = $(this);
        const current_text = $section.text().trim();
        
        if (current_text === 'Basic Visitor Info' || current_text === 'المعلومات الأساسية للزائر') {
            $section.text(lang_dict['Basic Visitor Info']);
        }
        else if (current_text === 'Health Questions' || current_text === 'الأسئلة الصحية') {
            $section.text(lang_dict['Health Questions']);
        }
    });
}

function update_all_buttons(lang_dict) {
    console.log('Updating all buttons...');
    
    // تحديث أزرار الحفظ والإلغاء
    $('button, .btn, .form-footer button').each(function() {
        const $button = $(this);
        const button_text = $button.text().trim();
        
        if (button_text === 'Save' || button_text === 'حفظ') {
            $button.text(lang_dict['Save']);
        }
        else if (button_text === 'Discard' || button_text === 'تجاهل') {
            $button.text(lang_dict['Discard']);
        }
    });
}

function update_page_direction(language) {
    if (language === 'Ar') {
        $('html').attr('dir', 'rtl');
        $('body').addClass('rtl-mode');
        $('.web-form-container, .form-container').addClass('text-right');
    } else {
        $('html').attr('dir', 'ltr');
        $('body').removeClass('rtl-mode');
        $('.web-form-container, .form-container').removeClass('text-right');
    }
}

function update_select_fields(language) {
    console.log('Updating select fields for language:', language);
    
    // تحديث بعد فترة قصيرة لضمان تحميل الحقول
    setTimeout(() => {
        const burnes_options = {
            'En': "None\nSkin trouble affecting hands, arms or face\nBurnes or wounds\nDischarge from eye, ear or gums/mouth",
            'Ar': "لا شيء\nمشاكل جلدية تؤثر على اليدين أو الذراعين أو الوجه\nحروق أو جروح\nإفرازات من العين أو الأذن أو اللثة/الفم"
        };
        
        const skin_options = {
            'En': "None\nA chronic skin or ear trouble\nA chronic gastrointestinal disorder",
            'Ar': "لا شيء\nمشكلة جلدية أو أذنية مزمنة\nاضطراب معوي مزمن"
        };
        
        try {
            const burnes_field = frappe.web_form.get_field('burnes');
            const skin_field = frappe.web_form.get_field('skin_or_gastrointestinal');
            
            if (burnes_field) {
                burnes_field.df.options = burnes_options[language];
                burnes_field.refresh();
            }
            
            if (skin_field) {
                skin_field.df.options = skin_options[language];
                skin_field.refresh();
            }
        } catch (error) {
            console.log('Error updating select fields:', error);
        }
    }, 300);
}

function show_language_change_confirmation(language) {
    // إظهار رسالة تأكيد بسيطة
    const message = language === 'Ar' ? 'تم تغيير اللغة إلى العربية' : 'Language changed to English';
    
    // إنشاء عنصر تأكيد مؤقت
    const confirmation = $(`
        <div style="
            position: fixed;
            top: 80px;
            right: 20px;
            z-index: 10001;
            background: #28a745;
            color: white;
            padding: 10px 15px;
            border-radius: 4px;
            font-size: 14px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        ">${message}</div>
    `);
    
    $('body').append(confirmation);
    
    // إزالة الرسالة بعد 2 ثانية
    setTimeout(() => {
        confirmation.fadeOut(300, function() {
            $(this).remove();
        });
    }, 2000);
}

function set_current_language() {
    const saved_lang = localStorage.getItem('visitor_language');
    const browser_lang = navigator.language.startsWith('ar') ? 'Ar' : 'En';
    const current_lang = saved_lang || browser_lang || 'En';
    
    console.log('Setting current language:', current_lang);
    
    // تحديث الواجهة باللغة الحالية
    update_entire_interface(current_lang);
    
    // تحديث زر اللغة
    $('#language_select').val(current_lang);
    $('.language-label').text(current_lang === 'Ar' ? 'اللغة:' : 'Language:');
}

function hide_unwanted_elements() {
    console.log('Hiding unwanted elements...');
    
    const unwanted = [
        '.navbar', 'header', '.header', '.web-footer', 'footer',
        '.btn-login-area', '#navbarSupportedContent', '.sidebar',
        '.breadcrumb', '.page-head'
    ];
    
    unwanted.forEach(selector => {
        $(selector).hide().remove();
    });
    
    // تحسين التخطيط
    $('body').css({
        'padding-top': '0',
        'background-color': '#f5f7fa'
    });
    
    $('.web-page-content').css({
        'margin-top': '0',
        'padding-top': '80px'
    });
}

function setup_other_systems() {
    // إعداد التاريخ الافتراضي
    setTimeout(() => {
        const today = new Date().toISOString().split('T')[0];
        const post_date_field = frappe.web_form.get_field('post_date');
        if (post_date_field && !post_date_field.value) {
            post_date_field.set_value(today);
        }
    }, 500);
    
    // إعداد المنطق الشرطي
    setTimeout(() => {
        const abroad_field = frappe.web_form.get_field('abroad');
        const ill_field = frappe.web_form.get_field('ill');
        
        if (abroad_field && ill_field) {
            abroad_field.df.onchange = () => toggle_illness_field();
            toggle_illness_field();
        }
    }, 1000);
}

function toggle_illness_field() {
    const abroad_field = frappe.web_form.get_field('abroad');
    const ill_field = frappe.web_form.get_field('ill');
    
    if (abroad_field && ill_field) {
        if (abroad_field.value) {
            ill_field.df.reqd = 1;
            ill_field.$wrapper.show();
        } else {
            ill_field.df.reqd = 0;
            ill_field.value = '';
            ill_field.$wrapper.hide();
        }
        ill_field.refresh();
    }
}

function setup_language_monitor() {
    // مراقبة مستمرة لضمان عمل زر اللغة
    setInterval(() => {
        // التأكد من وجود زر اللغة
        if ($('.language-switcher').length === 0) {
            console.log('Language switcher missing, recreating...');
            create_reliable_language_switcher();
        }
        
        // التأكد من ظهور زر اللغة
        $('.language-switcher').show().css({
            'display': 'block !important',
            'visibility': 'visible !important',
            'opacity': '1 !important'
        });
        
    }, 2000);
}

// قاموس الترجمة (نفس المحتوى السابق)
const translations = {
    'En': {
        'Visitor Registration': 'Visitor Registration',
        'Please fill in your information below to register.': 'Please fill in your information below to register.',
        'Save': 'Save',
        'Discard': 'Discard',
        'Basic Visitor Info': 'Basic Visitor Info',
        'Health Questions': 'Health Questions',
        'Language': 'Language',
        'Post Date': 'Post Date',
        'Full Name': 'Full Name',
        'Company': 'Company',
        'Purpose of Visit': 'Purpose of Visit',
        'Email': 'Email',
        'Typhoid / Paratyphoid last 3 month': 'Typhoid / Paratyphoid last 3 month',
        'Vomiting / Diarrhea last 7 days': 'Vomiting / Diarrhea last 7 days',
        'Been abroad last 3 weeks': 'Been abroad last 3 weeks',
        'If abroad, were you ill': 'If abroad, were you ill',
        'Suffering from': 'Suffering from',
        'Chronic disorder': 'Chronic disorder',
        'Additional info if answered YES': 'Additional info if answered YES',
        'Not Saved': 'Not Saved'
    },
    'Ar': {
        'Visitor Registration': 'تسجيل الزائر',
        'Please fill in your information below to register.': 'يرجى ملء المعلومات أدناه للتسجيل.',
        'Save': 'حفظ',
        'Discard': 'تجاهل',
        'Basic Visitor Info': 'المعلومات الأساسية للزائر',
        'Health Questions': 'الأسئلة الصحية',
        'Language': 'اللغة',
        'Post Date': 'تاريخ التسجيل',
        'Full Name': 'الاسم الكامل',
        'Company': 'الشركة',
        'Purpose of Visit': 'الغرض من الزيارة',
        'Email': 'البريد الإلكتروني',
        'Typhoid / Paratyphoid last 3 month': 'حمى التيفوئيد / نظيرة التيفوئيد خلال آخر 3 أشهر',
        'Vomiting / Diarrhea last 7 days': 'قيء / إسهال خلال آخر 7 أيام',
        'Been abroad last 3 weeks': 'السفر إلى الخارج خلال آخر 3 أسابيع',
        'If abroad, were you ill': 'في حالة السفر، هل كنت مريضاً',
        'Suffering from': 'تعاني من',
        'Chronic disorder': 'اضطراب مزمن',
        'Additional info if answered YES': 'معلومات إضافية في حالة الإجابة بنعم',
        'Not Saved': 'غير محفوظ'
    }
};

// بدء التطبيق
$(document).ready(function() {
    console.log('Document ready, starting application...');
});