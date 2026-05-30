/* Shopee extension integration: polling, paste, data application */

async function pasteShopeeData() {
    var existing = document.getElementById('paste-fallback');
    if (existing) existing.remove();
    var div = document.createElement('div');
    div.id = 'paste-fallback';
    div.innerHTML = '<div style="margin:8px 0;padding:12px;background:#fff3cd;border-radius:8px">' +
        '<p style="font-size:.85em;margin:0 0 6px">📋 Dán dữ liệu Shopee vào đây (Ctrl+V):</p>' +
        '<textarea id="paste-box" rows="2" style="width:100%;font-size:.8em;font-family:monospace;padding:6px;border:1px solid #ddd;border-radius:4px" placeholder="SHOPEE_DATA:{...}"></textarea>' +
        '<button onclick="manualPaste()" class="btn" style="padding:4px 12px;font-size:.85em;margin-top:4px">OK</button>' +
        ' <button onclick="document.getElementById(\'paste-fallback\').remove()" style="padding:4px 12px;font-size:.85em;margin-top:4px;background:#eee;border:1px solid #ddd;border-radius:8px;cursor:pointer">Hủy</button></div>';
    var statusEl = document.getElementById('shopee-poll-status');
    statusEl.parentElement.parentNode.insertBefore(div, statusEl.parentElement.nextSibling);
    var box = document.getElementById('paste-box');
    box.focus();
    try {
        var text = await navigator.clipboard.readText();
        if (text.startsWith('SHOPEE_DATA:')) { box.value = text; }
    } catch (e) { }
}

function manualPaste() {
    var text = document.getElementById('paste-box')?.value || '';
    var el = document.getElementById('paste-fallback');
    if (el) el.remove();
    if (text.startsWith('SHOPEE_DATA:')) {
        processShopeeText(text);
    } else {
        document.getElementById('shopee-poll-status').textContent = '❌ Dữ liệu không hợp lệ';
    }
}

async function processShopeeText(text) {
    var statusEl = document.getElementById('shopee-poll-status');
    try {
        var data = JSON.parse(text.substring(12));
        statusEl.textContent = '⏳ Đang tải ảnh từ Shopee...';
        var resp = await fetch('/receive-shopee-data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        var result = await resp.json();
        applyShopeeData(result);
    } catch (e) {
        statusEl.textContent = '❌ ' + e.message;
        setTimeout(function () { statusEl.textContent = ''; }, 4000);
    }
}

function applyShopeeData(data) {
    var statusEl = document.getElementById('shopee-poll-status');
    switchTab('url');
    var urlInput = document.querySelector('#panel-url input[name="url"]');
    if (urlInput && data.url) urlInput.value = data.url;
    window._shopeeBookmarkletData = data;

    var preview = document.getElementById('bookmarklet-preview');
    if (!preview) {
        preview = document.createElement('div');
        preview.id = 'bookmarklet-preview';
        var form = document.getElementById('form-url');
        form.parentNode.insertBefore(preview, form);
    }
    var reviews = data.reviews || [];
    var html = '<div class="result-card" style="margin-bottom:12px">';
    html += '<h3>📦 Dữ liệu từ Extension</h3>';
    html += '<p style="font-size:.85em;color:#666;margin-bottom:4px">📖 ' + (data.title || '') + '</p>';
    html += '<p style="font-size:.85em;margin:0">';
    if (data.price) html += '💰 ' + data.price + ' ';
    if (data.rating) html += '⭐ ' + data.rating + '/5 ';
    if (data.rating_count) html += '(' + data.rating_count.toLocaleString() + ' đánh giá) ';
    if (data.sold_count) html += '🛒 Đã bán ' + data.sold_count.toLocaleString();
    html += '</p>';
    if (reviews.length) {
        html += '<details style="margin-top:8px"><summary style="font-size:.85em;cursor:pointer">💬 ' + reviews.length + ' review thực tế</summary>';
        html += '<div style="font-size:.8em;color:#555;margin-top:4px">';
        reviews.slice(0, 6).forEach(function (r) {
            html += '<p style="margin:4px 0;padding:4px 8px;background:#f8f8f8;border-radius:4px">"“' + r.text.substring(0, 100) + '”' + (r.likes ? ' 👍' + r.likes : '') + '</p>';
        });
        html += '</div></details>';
    }
    html += '</div>';
    preview.innerHTML = html;
    statusEl.textContent = '✅ Đã nhận dữ liệu từ Extension!';
    setTimeout(function () { statusEl.textContent = ''; }, 5000);
}

async function importExtensionSingle() {
    var statusEl = document.getElementById('shopee-poll-status');
    statusEl.textContent = '⏳ Đang lấy dữ liệu từ Extension...';
    try {
        let resp = await fetch('/poll-shopee-data');
        let d = await resp.json();
        if (d.ready) {
            applyShopeeData(d.data);
            return;
        }
        resp = await fetch('/poll-shopee-queue');
        d = await resp.json();
        if (d.products?.length) {
            const latest = d.products[d.products.length - 1];
            applyShopeeData(latest);
        } else {
            statusEl.textContent = '❌ Chưa có dữ liệu. Hãy scrape sản phẩm từ Extension trước.';
            setTimeout(() => { statusEl.textContent = ''; }, 4000);
        }
    } catch (e) {
        statusEl.textContent = '❌ ' + e.message;
        setTimeout(() => { statusEl.textContent = ''; }, 4000);
    }
}

let _shopeePolling = null;
function startShopeePolling() {
    if (_shopeePolling) return;
    _shopeePolling = setInterval(async () => {
        try {
            const resp = await fetch('/poll-shopee-data');
            const d = await resp.json();
            if (d.ready) applyShopeeData(d.data);
        } catch (e) { }
    }, 3000);
}
