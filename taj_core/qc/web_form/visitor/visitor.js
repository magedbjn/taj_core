// /home/erpnext/frappe-bench/apps/taj_core/taj_core/qc/doctype/web_form/visitor/visitor.js

frappe.ready(function() {
    console.log('Visitor form loaded');
    
    // الانتظار قليلاً لتحميل DOM
    setTimeout(() => {
        const lang = localStorage.getItem('visitor_language') || (navigator.language && navigator.language.startsWith('ar') ? 'Ar' : 'En');
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
            'job _title': 'Job Title',
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
        'Please answer to the following questions:': 'Please answer to the following questions:',
        'InvalidEmail':'Invalid Email',
        'InvalidEmailMsg':'Please enter a valid email address.',
        'SuccessMsg':'✅ The form has been submitted successfully. Thank you for registering.',
        'SubmitAnotherResponse': 'Submit another response',
        'ErrorRequired':'is required',

        // نص القواعد للعرض فقط (بدون حقول)
        'Rules & Regulations': 'Rules & Regulations',
        rules_html: `
          <h3 style="margin-top:0;">Rules & Regulations</h3>
          <ol>
            <li>Please remove watch and any loose jewellery.</li>
            <li>Please do not use handphone or take any photographs in the production area without permission.</li>
            <li>Please wear the Personal Protective Equipment (PPE) provided during active production or as per instructed.</li>
            <li>Please do not handle food, touch any equipment, unless invited to do so.</li>
            <li>Please do not change any equipment settings.</li>
            <li>Eating, chewing, smoking or drinking in the production area is prohibited.</li>
            <li>Please do not spit, blow your nose, sneeze or cough over the food.</li>
            <li>Please wash and sanitize your hands each time you enter the work areas.</li>
            <li>Please sign/acknowledge below to confirm that you have read and understood the above rules.</li>
          </ol>
        `
    },
    'Ar': {
        fields: {
            'full_name': 'الاسم الكامل',
            'company': 'الشركة',
            'purpose_of_visit': 'الغرض من الزيارة',
            'email': 'البريد الإلكتروني',
            'job _title': 'المسمى الوظيفي',
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
        'Please answer to the following questions:': 'الرجاء الإجابة على الأسئلة التالية:',
        'InvalidEmail':'خطأ في البريد الإلكتروني',
        'InvalidEmailMsg':'يرجى إدخال بريد إلكتروني صحيح.',
        'SuccessMsg':'✅ تم حفظ النموذج بنجاح. شكراً لتسجيلك.',
        'SubmitAnotherResponse': 'تسجيل إدخال آخر',
        'ErrorRequired':'مطلوب',

        // نص القواعد للعرض فقط (بدون حقول)
        'Rules & Regulations': 'القواعد والأنظمة',
        rules_html: `
          <h3 style="margin-top:0;">القواعد والأنظمة</h3>
          <ol>
            <li>يرجى إزالة الساعة وأي مجوهرات فضفاضة.</li>
            <li>يرجى عدم استخدام الهاتف أو التقاط الصور في منطقة الإنتاج دون إذن.</li>
            <li>يرجى ارتداء معدات الحماية الشخصية (PPE) المقدمة أثناء الإنتاج أو حسب التعليمات.</li>
            <li>يرجى عدم التعامل مع الطعام أو لمس أي معدات إلا إذا طُلب منك ذلك.</li>
            <li>يرجى عدم تغيير إعدادات أي جهاز.</li>
            <li>يُمنع الأكل أو المضغ أو التدخين أو الشرب في منطقة الإنتاج.</li>
            <li>يرجى عدم البصق أو مسح/نفخ الأنف أو العطس أو السعال فوق الطعام.</li>
            <li>يرجى غسل وتعقيم اليدين في كل مرة تدخل فيها مناطق العمل.</li>
            <li>يرجى التوقيع/الإقرار أدناه للتأكيد على قراءة البنود وفهمها.</li>
          </ol>
        `
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
    if (!dict.options) return;
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

// ===== حقن نص القواعد (بدون أي حقول) =====
function render_rules_block(lang) {
    const dict = translations[lang] || translations['En'];

    // ابحث عن Section Break الخاص بالأسئلة الصحية (sb2) لنضع بعده البلوك
    const $sb2 = $('[data-fieldname="sb2"]');

    // أنشئ الحاوية إن لم تكن موجودة
    let $container = $('#rules_container');
    if (!$container.length) {
        $container = $('<div id="rules_container" class="rules-wrapper"></div>');
        if ($sb2.length) {
            $sb2.after($container);
        } else {
            // في حال لم نجد sb2 لأي سبب، أضِف في نهاية النموذج
            const $formArea = $('.web-form, .web-form-page, form').first();
            if ($formArea.length) {
                $formArea.append($container);
            } else {
                $('body').append($container); // حل أخير
            }
        }
    }

    // حقن المحتوى حسب اللغة
    $container.html(dict.rules_html);
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
    $('.section-head').first().text(dict['Basic Visitor Info']);
    
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

    // --- عرض القواعد كنص فقط ---
    render_rules_block(lang);

    // ترجمة رسائل الخطأ (بدون أي حقول للقواعد الآن)
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
            const key = field_map[label];
            if (dict.fields && dict.fields[key]) {
                const re = new RegExp(`Error: Value missing for Visitor: ${label}`, 'g');
                html = html.replace(re, `${dict.fields[key]} ${dict['ErrorRequired']}`);
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
