/* Settings dialog and API keys management */

function openSettings() {
    fetch('/api/settings').then(r => r.json()).then(d => {
        var labels = {
            GEMINI_API_KEY: 'Gemini API Key', ELEVENLABS_API_KEY: 'ElevenLabs API Key',
            AFFIPAD_API_KEY: 'AffiPad API Key',
            TIKTOK_CLIENT_KEY: 'TikTok Client Key', TIKTOK_CLIENT_SECRET: 'TikTok Client Secret',
            YOUTUBE_CLIENT_ID: 'YouTube Client ID', YOUTUBE_CLIENT_SECRET: 'YouTube Client Secret',
            FACEBOOK_APP_ID: 'Facebook App ID', FACEBOOK_APP_SECRET: 'Facebook App Secret',
        };
        var html = '';
        for (var k in d) {
            var status = d[k] ? '✅' : '❌';
            html += '<label style="display:block;margin-bottom:8px;font-size:.9em">' + status + ' ' + (labels[k] || k) +
                '<input type="password" id="set-' + k + '" placeholder="' + (d[k] ? '(đã cấu hình)' : 'Chưa có') +
                '" style="width:100%;padding:6px 10px;border:1px solid #ddd;border-radius:6px;margin-top:2px"></label>';
        }
        document.getElementById('settings-fields').innerHTML = html;
        document.getElementById('settings-dialog').showModal();
    });
}

function saveSettings() {
    var data = {};
    document.querySelectorAll('[id^="set-"]').forEach(el => {
        if (el.value.trim()) data[el.id.replace('set-', '')] = el.value.trim();
    });
    if (Object.keys(data).length === 0) { document.getElementById('settings-msg').textContent = 'Không có gì để lưu'; return; }
    fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
        .then(r => r.json()).then(d => { document.getElementById('settings-msg').textContent = d.message || 'Đã lưu'; });
}

function uploadKol(input, slot) {
    if (!input.files[0]) return;
    var fd = new FormData();
    fd.append('file', input.files[0]);
    fd.append('slot', slot);
    fetch('/upload-kol', { method: 'POST', body: fd }).then(r => r.json()).then(d => {
        document.getElementById('kol-status-' + slot).textContent = 'KOL ' + slot + ' ✅';
    });
}
