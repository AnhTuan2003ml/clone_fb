// Facebook Auto Click - Tự động click "Luôn xác nhận đó là tôi"
(function() {
    'use strict';

    const LOG_PREFIX = '[FB Auto Click]';
    
    // Các text cần tìm
    const TARGET_TEXTS = [
        'Luôn xác nhận đó là tôi',
        'Always confirm this is me',
        'Tin cậy thiết bị này',
        'Trust this device'
    ];

    function log(message) {
        console.log(`${LOG_PREFIX} ${message}`);
    }

    function showNotification(text) {
        const div = document.createElement('div');
        div.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #00c853;
            color: white;
            padding: 16px 24px;
            border-radius: 8px;
            font-family: system-ui, -apple-system, sans-serif;
            font-size: 14px;
            font-weight: 500;
            z-index: 999999;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            animation: slideIn 0.3s ease;
        `;
        div.textContent = `✓ Đã click: "${text}"`;
        
        // Thêm CSS animation
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(100px); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
        `;
        document.head.appendChild(style);
        
        document.body.appendChild(div);
        
        setTimeout(() => {
            div.style.opacity = '0';
            div.style.transition = 'opacity 0.5s';
            setTimeout(() => div.remove(), 500);
        }, 3000);
    }

    function findButtonByText() {
        // Tìm tất cả span có text target
        for (const targetText of TARGET_TEXTS) {
            const xpath = `//span[contains(text(), "${targetText}")]`;
            const result = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
            
            for (let i = 0; i < result.snapshotLength; i++) {
                const span = result.snapshotItem(i);
                
                // Tìm div[role="button"] cha
                let parent = span.parentElement;
                while (parent && parent !== document.body) {
                    if (parent.getAttribute('role') === 'button') {
                        return { button: parent, text: targetText };
                    }
                    parent = parent.parentElement;
                }
            }
        }
        return null;
    }

    function clickButton() {
        const found = findButtonByText();
        
        if (found) {
            log(`Tìm thấy button: "${found.text}"`);
            
            // Click
            found.button.click();
            log('Đã click button!');
            
            // Hiển thị thông báo
            showNotification(found.text);
            
            return true;
        }
        
        return false;
    }

    // Chạy ngay
    log('Extension started on: ' + window.location.href);
    
    setTimeout(() => {
        if (!clickButton()) {
            log('Chưa tìm thấy button, đang theo dõi DOM...');
        }
    }, 1500);

    // Theo dõi DOM thay đổi
    const observer = new MutationObserver(() => {
        if (clickButton()) {
            observer.disconnect();
        }
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });

    // Dừng sau 15 giây
    setTimeout(() => {
        observer.disconnect();
        log('Đã dừng theo dõi DOM');
    }, 15000);

})();
