/* History tab: publish history and schedule management */

async function loadHistory() {
    var platform = document.getElementById('history-platform')?.value || '';
    var days = document.getElementById('history-days')?.value || '30';
    var container = document.getElementById('history-table');
    var countEl = document.getElementById('history-count');
    container.innerHTML = '<p style="color:#666">Đang tải...</p>';
    try {
        var schedResp = await fetch('/api/schedule');
        var schedData = await schedResp.json();
        var jobs = schedData.jobs || [];
        var now = new Date();
        var currentTime = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0');
        var pending = jobs.filter(j => j.status === 'pending');
        var failed = jobs.filter(j => j.status === 'failed');
        var todayStr = (now.getMonth() + 1).toString().padStart(2, '0') + '/' + now.getDate().toString().padStart(2, '0');
        var missed = pending.filter(j => {
            if (j.slot.includes('T')) return new Date(j.slot) < now;
            return j.slot < currentTime;
        });
        var upcoming = pending.filter(j => {
            if (j.slot.includes('T')) return new Date(j.slot) >= now;
            return j.slot >= currentTime;
        });

        var html = '';
        if (missed.length) {
            html += '<div style="background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;padding:12px;margin-bottom:12px">';
            html += '<strong>⚠️ Bài đăng bị lỡ (' + missed.length + ')</strong>';
            missed.forEach(function (j) {
                var title = (j.review_data?.book?.title || '').substring(0, 40);
                var platIcon = { facebook: '📘', tiktok: '🎵', youtube: '▶️', instagram: '📷', all: '📤' }[j.platform] || j.platform;
                var vidLink = j.video_url ? '<a href="' + j.video_url + '" target="_blank" title="Xem video">' + platIcon + '</a>' : platIcon;
                html += '<div style="display:flex;align-items:center;gap:8px;margin-top:8px;font-size:.85em">';
                var slotDisplay = j.slot.includes('T') ? j.slot.slice(5, 10).replace('-', '/') + ' ' + j.slot.slice(11, 16) : todayStr + ' ' + j.slot;
                html += '<span>' + vidLink + ' ' + title + ' (lịch ' + slotDisplay + ')</span>';
                html += '<button onclick="scheduleAction(\'' + j.id + '\',\'now\')" style="padding:2px 8px;border:none;background:#1877f2;color:#fff;border-radius:4px;cursor:pointer;font-size:.8em">📤 Đăng ngay</button>';
                html += '<button onclick="scheduleAction(\'' + j.id + '\',\'reschedule\')" style="padding:2px 8px;border:none;background:#f59e0b;color:#fff;border-radius:4px;cursor:pointer;font-size:.8em">⏰ Lên lịch lại</button>';
                html += '<button onclick="scheduleAction(\'' + j.id + '\',\'cancel\')" style="padding:2px 8px;border:none;background:#eee;border-radius:4px;cursor:pointer;font-size:.8em">🗑️ Bỏ qua</button>';
                html += '</div>';
            });
            html += '</div>';
        }
        if (failed.length) {
            html += '<div style="background:#fef2f2;border:1px solid #ef4444;border-radius:8px;padding:12px;margin-bottom:12px">';
            html += '<strong>❌ Đăng thất bại (' + failed.length + ')</strong>';
            failed.forEach(function (j) {
                var title = (j.review_data?.book?.title || '').substring(0, 40);
                var platIcons = { facebook: '📘', tiktok: '🎵', youtube: '▶️', instagram: '📷' };
                var platIcon = platIcons[j.platform] || j.platform;
                html += '<div style="display:flex;align-items:center;gap:8px;margin-top:6px;font-size:.85em">';
                html += '<span>' + platIcon + ' ' + title + ' <span style="color:#ef4444;font-size:.8em">(' + (j.last_error || '').substring(0, 40) + ')</span></span>';
                html += '<button onclick="scheduleAction(\'' + j.id + '\',\'now\')" style="padding:2px 8px;border:none;background:#e94560;color:#fff;border-radius:4px;cursor:pointer;font-size:.8em">🔄</button>';
                html += '<button onclick="scheduleAction(\'' + j.id + '\',\'cancel\')" style="padding:2px 6px;border:none;background:#eee;border-radius:4px;cursor:pointer;font-size:.8em">✕</button>';
                html += '</div>';
            });
            html += '</div>';
        }
        if (upcoming.length) {
            html += '<div style="background:#ecfdf5;border:1px solid #10b981;border-radius:8px;padding:12px;margin-bottom:12px">';
            html += '<strong>📅 Lịch đăng bài (' + upcoming.length + ')</strong>';
            upcoming.sort(function (a, b) {
                var sa = a.slot.includes('T') ? a.slot : now.toISOString().slice(0, 11) + a.slot;
                var sb = b.slot.includes('T') ? b.slot : now.toISOString().slice(0, 11) + b.slot;
                return sa.localeCompare(sb);
            });
            upcoming.forEach(function (j) {
                var title = (j.review_data?.book?.title || '').substring(0, 40);
                var platIcon = { facebook: '📘', tiktok: '🎵', youtube: '▶️', instagram: '📷', all: '📤' }[j.platform] || j.platform;
                var vidLink = j.video_url ? '<a href="' + j.video_url + '" target="_blank" title="Xem video">' + platIcon + '</a>' : platIcon;
                html += '<div style="display:flex;align-items:center;gap:8px;margin-top:6px;font-size:.85em">';
                var slotDisplay2 = j.slot.includes('T') ? j.slot.slice(5, 10).replace('-', '/') + ' ' + j.slot.slice(11, 16) : todayStr + ' ' + j.slot;
                html += '<span>' + vidLink + ' ' + title + ' → ' + slotDisplay2 + '</span>';
                html += '<button onclick="scheduleAction(\'' + j.id + '\',\'cancel\')" style="padding:2px 6px;border:none;background:#eee;border-radius:4px;cursor:pointer;font-size:.8em">✕</button>';
                html += '</div>';
            });
            html += '</div>';
        }

        var resp = await fetch('/api/history?platform=' + platform + '&days=' + days);
        var data = await resp.json();
        var records = data.records || [];
        countEl.textContent = records.length + ' bài đăng';
        if (records.length) {
            html += '<table style="width:100%;border-collapse:collapse;font-size:.85em">';
            html += '<tr style="background:#f8f9fa;text-align:left"><th style="padding:8px">Ngày</th><th>Sản phẩm</th><th>Nền tảng</th><th>Persona</th><th>Thao tác</th></tr>';
            records.forEach(function (r) {
                var date = (r.published_at || '').substring(0, 10);
                var platIcon = { facebook: '📘', tiktok: '🎵', youtube: '▶️', instagram: '📷' }[r.platform] || r.platform;
                var platCell = r.post_url ? '<a href="' + r.post_url + '" target="_blank" title="Xem bài đăng">' + platIcon + '</a>' : platIcon;
                var title = (r.title || '').substring(0, 50);
                var videoLink = r.video_path ? '<a href="' + r.video_path + '" target="_blank">▶️</a>' : '';
                var copyBtn = r.review_text ? '<button onclick="navigator.clipboard.writeText(this.dataset.t);this.textContent=\'✅\'" data-t="' + r.review_text.replace(/"/g, '&quot;').replace(/\n/g, ' ') + '" style="border:none;background:none;cursor:pointer">📋</button>' : '';
                var shopeeLink = r.url ? '<a href="' + r.url + '" target="_blank" style="font-size:.8em">🔗</a>' : '';
                html += '<tr style="border-bottom:1px solid #eee">';
                html += '<td style="padding:6px 8px">' + date + '</td>';
                html += '<td style="padding:6px 8px">' + title + ' ' + shopeeLink + '</td>';
                html += '<td style="padding:6px 8px">' + platCell + '</td>';
                html += '<td style="padding:6px 8px;font-size:.8em">' + (r.persona || '') + '</td>';
                html += '<td style="padding:6px 8px">' + videoLink + ' ' + copyBtn + '</td>';
                html += '</tr>';
            });
            html += '</table>';
        } else if (!missed.length && !upcoming.length) {
            html += '<p style="color:#999">Chưa có bài đăng nào.</p>';
        }
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<p style="color:red">Lỗi: ' + e.message + '</p>';
    }
}

async function scheduleAction(jobId, action) {
    var fd = new FormData();
    fd.append('job_id', jobId);
    if (action === 'now') {
        await fetch('/api/schedule/publish-now', { method: 'POST', body: fd });
    } else if (action === 'reschedule') {
        var tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1);
        var tmrDate = tomorrow.toISOString().slice(0, 10);
        var tmrStr = (tomorrow.getMonth() + 1).toString().padStart(2, '0') + '/' + tomorrow.getDate().toString().padStart(2, '0');
        var pick = document.createElement('select');
        pick.innerHTML = '<option value="' + tmrDate + 'T08:30">' + tmrStr + ' 08:30</option><option value="' + tmrDate + 'T12:00">' + tmrStr + ' 12:00</option><option value="' + tmrDate + 'T19:00">' + tmrStr + ' 19:00</option><option value="' + tmrDate + 'T21:30">' + tmrStr + ' 21:30</option><option value="custom">📅 Tùy chọn</option>';
        pick.style.cssText = 'margin-left:4px';
        var dtInput = document.createElement('input');
        dtInput.type = 'datetime-local';
        dtInput.style.cssText = 'margin-left:4px;display:none;font-size:.8em';
        pick.onchange = function () { dtInput.style.display = pick.value === 'custom' ? 'inline' : 'none'; };
        var ok = document.createElement('button');
        ok.textContent = '✓';
        ok.style.cssText = 'margin-left:4px;cursor:pointer';
        ok.onclick = async function () {
            var slot = pick.value === 'custom' ? dtInput.value : pick.value;
            fd.append('slot', slot);
            await fetch('/api/schedule/reschedule', { method: 'POST', body: fd });
            loadHistory();
        };
        var target = event?.target;
        if (target) { target.after(pick); pick.after(dtInput); dtInput.after(ok); }
        return;
    } else {
        await fetch('/api/schedule/cancel', { method: 'POST', body: fd });
    }
    loadHistory();
}
