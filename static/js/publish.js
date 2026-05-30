/* Publishing to social platforms and scheduling */

async function publishVideo(videoUrl, platform, force) {
    platform = platform || 'facebook';
    var label = { tiktok: 'TikTok', facebook: 'Facebook Reels', youtube: 'YouTube Shorts', instagram: 'Instagram Reels', threads: 'Threads' }[platform] || platform;
    var status = document.getElementById('publish-status') || document.getElementById('pub-status-' + platform);
    if (!status) return;
    status.textContent = '⏳ Đang đăng ' + label + '...';
    try {
        var fd = new FormData();
        fd.append('review_json', JSON.stringify(window._lastReviewData || {}));
        fd.append('video_url', videoUrl);
        fd.append('platforms', platform);
        if (force) fd.append('force', '1');
        var pageSelect = document.getElementById('fb-page-select');
        if (pageSelect && pageSelect.value) fd.append('page_id', pageSelect.value);
        var resp = await fetch('/publish', { method: 'POST', body: fd });
        var data = await resp.json();
        if (data.duplicate_warning) {
            status.innerHTML = '⚠️ ' + data.warnings.join(', ') + ' <button onclick="publishVideo(\'' + videoUrl + '\',\'' + platform + '\',true)" style="background:#e94560;color:#fff;border:none;border-radius:6px;padding:4px 12px;cursor:pointer;font-size:.85em">Đăng lại</button>';
            return;
        }
        var results = data.results || [];
        var msg = results.map(function (r) {
            var s = (r.success ? '✅' : '❌') + ' ' + r.platform + ': ' + r.message;
            if (r.post_id && r.success) {
                var urls = { facebook: 'https://www.facebook.com/' + r.post_id, youtube: 'https://youtu.be/' + r.post_id, instagram: 'https://www.instagram.com/reel/' + r.post_id };
                if (urls[r.platform]) s += ' <a href="' + urls[r.platform] + '" target="_blank">Xem bài đăng →</a>';
            }
            return s;
        }).join(' | ');
        status.innerHTML = msg;
    } catch (e) {
        status.textContent = '❌ ' + e.message;
    }
}

async function scheduleVideo(videoUrl, platform) {
    var status = document.getElementById('publish-status');
    var selVal = document.getElementById('schedule-slot')?.value || '';
    var slot = selVal === 'custom' ? (document.getElementById('schedule-custom-dt')?.value || '') : selVal;
    var pageId = document.getElementById('fb-page-select')?.value || '';
    try {
        var fd = new FormData();
        fd.append('review_json', JSON.stringify(window._lastReviewData || {}));
        fd.append('video_url', videoUrl);
        fd.append('platform', platform);
        fd.append('page_id', pageId);
        fd.append('slot', slot);
        var resp = await fetch('/schedule', { method: 'POST', body: fd });
        var data = await resp.json();
        if (status) status.innerHTML = '⏰ Đã lên lịch: <strong>' + data.slot + '</strong>';
    } catch (e) {
        if (status) status.textContent = '❌ ' + e.message;
    }
}
