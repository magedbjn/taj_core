// /home/erpnext/frappe-bench/apps/taj_core/taj_core/qc/doctype/web_form/visitor/visitor.js

frappe.ready(function() {
    console.log('Visitor form loaded');
    
    // الانتظار قليلاً لتحميل DOM
    setTimeout(() => {
        const lang = localStorage.getItem('visitor_language') || (navigator.language.startsWith('ar') ? 'Ar' : 'En');
        create_language_switcher(lang);
        set_interface_language(lang);
        hide_unwanted_elements();
        console.log('Language switcher initialized with:', lang);
    }, 500);
});

// ===== قاموس الترجمة =====
const translations = {
    'En': {
        fields: {
            'full_name': 'Full Name',
            'company': 'Company',
            'purpose_of_visit': 'Purpose of Visit',
            'email': 'Email',
            'typhoid_or_paratyphoid': 'Typhoid / Paratyphoid last 3 months',
            'vomiting': 'Vomiting / Diarrhea last 7 days',
            'abroad': 'Been abroad last 3 weeks',
            'ill': 'If abroad, were you ill',
            'burnes': 'Suffering from',
            'skin_or_gastrointestinal': 'Chronic disorder',
            'answered_yes': 'Additional info if answered YES'
        },
        options: {
            'burnes': {
                'None': 'None',
                'Skin trouble affecting hands, arms or face': 'Skin trouble affecting hands, arms or face',
                'Burnes or wounds': 'Burnes or wounds',
                'Discharge from eye, ear or gums/mouth': 'Discharge from eye, ear or gums/mouth'
            },
            'skin_or_gastrointestinal': {
                'None': 'None',
                'A chronic skin or ear trouble': 'A chronic skin or ear trouble',
                'A chronic gastrointestinal disorder': 'A chronic gastrointestinal disorder'
            }
        },
        'Visitor Registration':'Visitor Registration',
        'Please fill in your information below to register.':'Please fill in your information below to register.',
        'Submit':'Submit',
        'Discard':'Discard',
        'Basic Visitor Info': 'Basic Visitor Info',
        'InvalidEmail':'Invalid Email',
        'InvalidEmailMsg':'Please enter a valid email address.',
        'SuccessMsg':'✅ The form has been submitted successfully. Thank you for registering.',
        'SubmitAnotherResponse': 'Submit another response',
        'ErrorRequired':'is required'
    },
    'Ar': {
        fields: {
            'full_name': 'الاسم الكامل',
            'company': 'الشركة',
            'purpose_of_visit': 'الغرض من الزيارة',
            'email': 'البريد الإلكتروني',
            'typhoid_or_paratyphoid': 'التيفوئيد / البارايبوئيد آخر 3 أشهر',
            'vomiting': 'قيء / إسهال آخر 7 أيام',
            'abroad': 'تم السفر إلى الخارج آخر 3 أسابيع',
            'ill': 'إذا كنت في الخارج، هل كنت مريضاً',
            'burnes': 'يعاني من',
            'skin_or_gastrointestinal': 'اضطراب مزمن',
            'answered_yes': 'معلومات إضافية إذا تم الإجابة بنعم'
        },
        options: {
            'burnes': {
                'None': 'لا شيء',
                'Skin trouble affecting hands, arms or face': 'مشاكل جلدية تؤثر على اليدين أو الذراعين أو الوجه',
                'Burnes or wounds': 'حروق أو جروح',
                'Discharge from eye, ear or gums/mouth': 'إفراز من العين أو الأذن أو اللثة/الفم'
            },
            'skin_or_gastrointestinal': {
                'None': 'لا شيء',
                'A chronic skin or ear trouble': 'مشاكل جلدية أو أذن مزمنة',
                'A chronic gastrointestinal disorder': 'اضطراب معدي معوي مزمن'
            }
        },
        'Visitor Registration':'تسجيل الزائر',
        'Please fill in your information below to register.':'يرجى ملء المعلومات أدناه للتسجيل.',
        'Submit':'إعتماد',
        'Discard':'تجاهل',
        'Basic Visitor Info': 'معلومات أساسية عن الزائر',
        'InvalidEmail':'خطأ في البريد الإلكتروني',
        'InvalidEmailMsg':'يرجى إدخال بريد إلكتروني صحيح.',
        'SuccessMsg':'✅ تم حفظ النموذج بنجاح. شكراً لتسجيلك.',
        'SubmitAnotherResponse': 'تسجيل إدخال آخر',
        'ErrorRequired':'مطلوب'
    }
};

// ===== ترجمة الحقول =====
function translate_fields(lang) {
    const dict = translations[lang] || translations['En'];
    $('.frappe-control').each(function() {
        const fieldname = $(this).data('fieldname');
        if (fieldname && dict.fields && dict.fields[fieldname]) {
            $(this).find('label.control-label, .label-area').text(dict.fields[fieldname]);
        }
    });
}

// ===== ترجمة خيارات Select =====
function translate_select_options(lang) {
    const dict = translations[lang] || translations['En'];
    Object.keys(dict.options).forEach(fieldname => {
        const select = $(`[data-fieldname="${fieldname}"]`);
        if (select.length) {
            select.find('option').each(function() {
                const val = $(this).val();
                if (dict.options[fieldname][val]) {
                    $(this).text(dict.options[fieldname][val]);
                    $(this).attr('title', dict.options[fieldname][val]); // tooltip
                }
            });
        }
    });
}

// ===== زر اللغة =====
function create_language_switcher(currentLang){
    $('.language-switcher').remove();
    
    const label_text = currentLang === 'Ar' ? 'اللغة' : 'Language';
    
    const switcher_html = `
        <div class="language-switcher" style="
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
            <label class="language-label" style="
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
                <option value="En" ${currentLang==='En'?'selected':''}>English</option>
                <option value="Ar" ${currentLang==='Ar'?'selected':''}>العربية</option>
            </select>
        </div>
    `;
    
    $('body').prepend(switcher_html);
    
    $('#language_select').off('change').on('change', function(){
        const lang = $(this).val();
        localStorage.setItem('visitor_language', lang);
        set_interface_language(lang);
        $('.language-label').text(lang === 'Ar' ? 'اللغة' : 'Language');
    });
}

// ===== ضبط اللغة =====
function set_interface_language(lang){
    const dict = translations[lang] || translations['En'];
    
    // اتجاه الصفحة
    $('html').attr('dir', lang==='Ar'?'rtl':'ltr');
    $('body').toggleClass('rtl-mode', lang==='Ar');

    // ترجمة العنوان والنص
    $('.web-form-title h1, h1').text(dict['Visitor Registration']);
    $('.web-form-introduction p, .introduction-text, .web-form-description').text(dict['Please fill in your information below to register.']);
    $('.section-head').text(dict['Basic Visitor Info']);
    
    // ترجمة الأزرار
    $('button, .btn').each(function(){
        const t = $(this).text().trim();
        if(t==='Submit'||t==='إعتماد') $(this).text(dict['Submit']);
        if(t==='Discard'||t==='تجاهل') $(this).text(dict['Discard']);
    });

    translate_fields(lang);
    translate_select_options(lang);

    // ترجمة رسالة النجاح
    $('.web-form-message').text(dict['SuccessMsg']);
    $('.success-page .success-title').text(dict['Visitor Registration']);
    $('.success-page .success-message').text(dict['SuccessMsg']);
    $('.success-page .new-btn').text(dict['SubmitAnotherResponse']);

    // ترجمة رسائل الخطأ
    translate_error_modal(lang);
}

// ===== ترجمة رسائل الخطأ =====
function translate_error_modal(lang){
    const dict = translations[lang] || translations['En'];
    const field_map = {
        'Full Name': 'full_name',
        'Company': 'company',
        'Email': 'email',
        'Purpose of Visit': 'purpose_of_visit',
        'Suffering from': 'burnes',
        'Chronic disorder': 'skin_or_gastrointestinal'
    };

    $('.modal-body .msgprint').each(function(){
        let html = $(this).html();
        Object.keys(field_map).forEach(label => {
            if(dict.fields[field_map[label]]) {
                const re = new RegExp(`Error: Value missing for Visitor: ${label}`, 'g');
                html = html.replace(re, `${dict.fields[field_map[label]]} ${dict['ErrorRequired']}`);
            }
        });
        $(this).html(html);
    });
}

// ===== إخفاء العناصر غير المرغوب فيها =====
function hide_unwanted_elements(){
    const selectors = [
        '.navbar', 'header', '.web-footer', 'footer', 
        '.btn-login-area', '.sidebar', '.breadcrumb', '.page-head'
    ];
    selectors.forEach(selector => $(selector).hide());
    
    $('body').css({'padding-top':'0','background-color':'#f5f7fa'});

    $('.language-switcher').show().css({
        'display': 'block !important',
        'visibility': 'visible !important',
        'opacity': '1 !important'
    });
}
