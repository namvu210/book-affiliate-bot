/* Movie Ad Generator — assembly (Phase 5) */

var musicCategories = {};

async function loadMusicCategories() {
    try {
        var resp = await fetch('/api/movie/music-categories');
        if (resp.ok) musicCategories = await resp.json();
    } catch (e) {}
}

function renderAssemblyStep() {
    var container = document.getElementById('assembly-container');
    if (!movieState.project) {
        container.innerHTML = '<p style="color:#999">Chưa có project.</p>';
        return;
    }

    var segmentVideos = movieState.project.segment_videos || {};
    var segments = (movieState.project.screenplay || {}).segments || [];
    var hasVideo = (segments.length > 0 && Object.keys(segmentVideos).length === segments.length) ||
                   movieState.project.extended_video || movieState.project.video_clip;
    var finalVideo = movieState.project.final_video;
    var screenplay = movieState.project.screenplay || {};

    var html = '';

    if (!hasVideo) {
        html += '<div style="padding:20px;background:#fef2f2;border-radius:8px;text-align:center">';
        html += '<p style="color:#ef4444">⚠️ Cần tạo video trước (Bước 5)</p>';
        html += '</div>';
        container.innerHTML = html;
        return;
    }

    // Options
    html += '<div style="background:#f8f9fa;border-radius:8px;padding:16px;margin-bottom:16px">';
    html += '<h3 style="font-size:.9em;margin-bottom:12px">Tùy chọn xuất video</h3>';

    var overlay = screenplay.marketing_overlay || {};

    // Marketing overlay texts
    html += '<label style="font-size:.85em">Hook overlay (0-2s, stop the scroll):</label>';
    html += '<input type="text" id="assembly-hook-overlay" value="' + (overlay.hook_overlay || '').replace(/"/g, '&quot;') + '" placeholder="VD: Cái gì mà viral khắp TikTok?" style="margin-bottom:8px">';

    html += '<label style="font-size:.85em">Benefit overlay (3-10s, value):</label>';
    html += '<input type="text" id="assembly-benefit-overlay" value="' + (overlay.benefit_overlay || '').replace(/"/g, '&quot;') + '" placeholder="VD: Linen mát, không nhăn, mặc cả ngày" style="margin-bottom:8px">';

    html += '<label style="font-size:.85em">CTA overlay (outro, drive action):</label>';
    html += '<input type="text" id="assembly-cta-overlay" value="' + (overlay.cta_overlay || 'Link mua o mo ta nhe!').replace(/"/g, '&quot;') + '" placeholder="VD: Link ở bio - chỉ còn 50 cái" style="margin-bottom:8px">';

    // Intro hook (separate from marketing overlay — this is the intro frame text)
    html += '<label style="font-size:.85em">Intro text (trên nền mờ):</label>';
    html += '<input type="text" id="assembly-hook" value="' + (screenplay.story_hook || '').replace(/"/g, '&quot;') + '" style="margin-bottom:8px">';

    // Audio & caption options
    html += '<div style="display:flex;gap:16px;align-items:center;margin:8px 0;flex-wrap:wrap">';
    html += '<label style="font-size:.85em;margin:0"><input type="checkbox" id="assembly-keep-audio" checked> Giữ audio Veo (dialogue)</label>';
    html += '<label style="font-size:.85em;margin:0"><input type="checkbox" id="assembly-captions"> Captions (phụ đề)</label>';
    html += '</div>';

    // Music selection
    html += '<label style="font-size:.85em">Nhạc nền:</label>';
    html += '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">';
    html += '<select id="assembly-music-cat" onchange="loadMusicTracks()" style="padding:6px 10px;border-radius:6px;border:1.5px solid #ddd;font-size:.85em">';
    html += '<option value="">-- Không có nhạc --</option>';
    for (var cat in musicCategories) {
        html += '<option value="' + cat + '">' + cat + ' (' + musicCategories[cat] + ' tracks)</option>';
    }
    html += '</select>';
    html += '<select id="assembly-music-track" style="padding:6px 10px;border-radius:6px;border:1.5px solid #ddd;font-size:.85em;min-width:150px"><option value="">Chọn track</option></select>';
    html += '</div>';

    // Volume
    html += '<div style="display:flex;gap:8px;align-items:center;margin-top:8px">';
    html += '<label style="font-size:.85em;margin:0">Volume nhạc:</label>';
    html += '<input type="range" id="assembly-music-vol" min="0" max="50" value="25" style="flex:1;max-width:200px">';
    html += '<span id="assembly-vol-label" style="font-size:.8em;color:#666">25%</span>';
    html += '</div>';

    html += '</div>';

    // Assemble button
    html += '<div style="text-align:center;margin-bottom:16px">';
    html += '<button onclick="assembleMovie()" class="btn" style="padding:12px 32px;font-size:1em">🎬 Xuất video hoàn chỉnh</button>';
    html += '<span id="assembly-status" style="font-size:.85em;color:#666;margin-left:12px"></span>';
    html += '</div>';

    // Final video preview + publish
    if (finalVideo) {
        html += '<div style="border:2px solid #10b981;border-radius:10px;overflow:hidden;margin-bottom:16px">';
        html += '<div style="background:#f0fdf4;padding:8px 12px;border-bottom:1px solid #d1fae5">';
        html += '<strong style="font-size:.9em;color:#10b981">✅ Video hoàn chỉnh</strong>';
        html += '</div>';
        html += '<div style="padding:12px">';
        html += '<video src="' + finalVideo + '?t=' + Date.now() + '" controls playsinline style="width:100%;max-height:500px;border-radius:8px;background:#000"></video>';
        html += '<div style="margin-top:8px;display:flex;gap:8px;justify-content:center">';
        html += '<a href="' + finalVideo + '" download class="btn" style="padding:6px 16px;font-size:.85em;text-decoration:none">⬇️ Download</a>';
        html += '<button onclick="assembleMovie()" class="btn btn-secondary" style="padding:6px 16px;font-size:.85em">🔄 Xuất lại</button>';
        html += '</div></div></div>';

        // Publish section
        html += '<div style="background:#f8f9fa;border-radius:8px;padding:16px">';
        html += '<h3 style="font-size:.9em;margin-bottom:12px">📤 Đăng lên mạng xã hội</h3>';
        html += '<label style="font-size:.85em">Caption:</label>';
        html += '<textarea id="publish-caption" rows="3" placeholder="Viết caption cho bài đăng...">' + (screenplay.story_hook || '') + '</textarea>';
        html += '<label style="font-size:.85em">Hashtags (cách nhau bằng dấu cách):</label>';
        html += '<input type="text" id="publish-hashtags" placeholder="#fashion #dress #shopee" style="margin-bottom:8px">';
        html += '<label style="font-size:.85em">Affiliate link:</label>';
        html += '<input type="text" id="publish-link" value="' + (movieState.project.affiliate_link || '').replace(/"/g, '&quot;') + '" placeholder="https://s.shopee.vn/..." style="margin-bottom:12px">';
        html += '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">';
        html += '<label style="font-size:.85em;margin:0"><input type="checkbox" value="tiktok" class="publish-platform" checked> TikTok</label>';
        html += '<label style="font-size:.85em;margin:0"><input type="checkbox" value="facebook" class="publish-platform"> Facebook</label>';
        html += '<label style="font-size:.85em;margin:0"><input type="checkbox" value="youtube" class="publish-platform"> YouTube</label>';
        html += '</div>';
        html += '<div style="display:flex;gap:8px;align-items:center;margin-top:12px;flex-wrap:wrap">';
        html += '<button onclick="publishMovie()" class="btn" style="padding:8px 20px;font-size:.85em">📤 Đăng ngay</button>';
        html += '<select id="schedule-slot" style="padding:6px 10px;border-radius:6px;border:1.5px solid #ddd;font-size:.85em">';
        html += '<option value="">Chọn giờ...</option>';
        html += '<option value="08:30">08:30</option>';
        html += '<option value="12:00">12:00</option>';
        html += '<option value="19:00">19:00</option>';
        html += '<option value="21:30">21:30</option>';
        html += '</select>';
        html += '<button onclick="scheduleMovie()" class="btn btn-secondary" style="padding:8px 20px;font-size:.85em">🕐 Hẹn giờ</button>';
        html += '<span id="publish-status" style="font-size:.85em;color:#666"></span>';
        html += '</div></div>';
    }

    container.innerHTML = html;

    // Volume slider listener
    var volSlider = document.getElementById('assembly-music-vol');
    if (volSlider) {
        volSlider.oninput = function () {
            document.getElementById('assembly-vol-label').textContent = this.value + '%';
        };
    }
}

async function loadMusicTracks() {
    var cat = document.getElementById('assembly-music-cat').value;
    var select = document.getElementById('assembly-music-track');
    select.innerHTML = '<option value="">Chọn track</option>';
    if (!cat) return;

    try {
        var resp = await fetch('/api/movie/music/' + encodeURIComponent(cat));
        if (!resp.ok) return;
        var tracks = await resp.json();
        tracks.forEach(function (t) {
            var opt = document.createElement('option');
            opt.value = t.path;
            opt.textContent = t.name;
            select.appendChild(opt);
        });
    } catch (e) {}
}

async function assembleMovie() {
    if (!movieState.project) return;

    var status = document.getElementById('assembly-status');
    status.textContent = '⏳ Đang xuất video...';

    var hook = document.getElementById('assembly-hook').value;
    var hookOverlay = document.getElementById('assembly-hook-overlay').value;
    var benefitOverlay = document.getElementById('assembly-benefit-overlay').value;
    var ctaOverlay = document.getElementById('assembly-cta-overlay').value;
    var keepAudio = document.getElementById('assembly-keep-audio').checked;
    var captions = document.getElementById('assembly-captions').checked;
    var musicTrack = document.getElementById('assembly-music-track').value;
    var musicVol = parseInt(document.getElementById('assembly-music-vol').value) / 100;

    try {
        var resp = await fetch('/api/movie/project/' + movieState.project.id + '/assemble', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                hook: hook,
                cta: ctaOverlay,
                keep_veo_audio: keepAudio,
                captions: captions,
                marketing_overlay: {
                    hook_overlay: hookOverlay,
                    benefit_overlay: benefitOverlay,
                    cta_overlay: ctaOverlay,
                },
                music_path: musicTrack,
                music_volume: musicVol,
            }),
        });
        if (!resp.ok) { var err = await resp.json(); throw new Error(err.detail); }
        var data = await resp.json();

        movieState.project.final_video = data.video_url;
        movieState.project.status = 'complete';
        status.textContent = '✅ Hoàn tất!';
        renderAssemblyStep();
    } catch (e) {
        status.textContent = '❌ ' + e.message;
    }
}

async function scheduleMovie() {
    if (!movieState.project) return;

    var status = document.getElementById('publish-status');
    var slot = document.getElementById('schedule-slot').value;
    if (!slot) {
        status.textContent = '⚠️ Chọn giờ đăng';
        return;
    }

    status.textContent = '⏳ Đang hẹn giờ...';

    var caption = document.getElementById('publish-caption').value;
    var hashtags = document.getElementById('publish-hashtags').value.trim().split(/\s+/).filter(Boolean);
    var link = document.getElementById('publish-link').value;
    var platforms = [];
    document.querySelectorAll('.publish-platform:checked').forEach(function (el) {
        platforms.push(el.value);
    });

    if (!platforms.length) {
        status.textContent = '⚠️ Chọn ít nhất 1 platform';
        return;
    }

    try {
        var resp = await fetch('/api/movie/project/' + movieState.project.id + '/schedule', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                slot: slot,
                platforms: platforms,
                caption: caption,
                hashtags: hashtags,
                affiliate_link: link,
            }),
        });
        if (!resp.ok) { var err = await resp.json(); throw new Error(err.detail); }
        var data = await resp.json();

        status.textContent = '✅ Đã hẹn giờ ' + data.slot + ' (ID: ' + data.job_id.slice(0, 8) + ')';
    } catch (e) {
        status.textContent = '❌ ' + e.message;
    }
}

async function publishMovie() {
    if (!movieState.project) return;

    var status = document.getElementById('publish-status');
    status.textContent = '⏳ Đang đăng...';

    var caption = document.getElementById('publish-caption').value;
    var hashtags = document.getElementById('publish-hashtags').value.trim().split(/\s+/).filter(Boolean);
    var link = document.getElementById('publish-link').value;
    var platforms = [];
    document.querySelectorAll('.publish-platform:checked').forEach(function (el) {
        platforms.push(el.value);
    });

    if (!platforms.length) {
        status.textContent = '⚠️ Chọn ít nhất 1 platform';
        return;
    }

    try {
        var resp = await fetch('/api/movie/project/' + movieState.project.id + '/publish', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                platforms: platforms,
                caption: caption,
                hashtags: hashtags,
                affiliate_link: link,
            }),
        });
        if (!resp.ok) { var err = await resp.json(); throw new Error(err.detail); }
        var data = await resp.json();

        var msgs = data.results.map(function (r) {
            return r.platform + ': ' + (r.success ? '✅' : '❌ ' + r.message);
        });
        status.textContent = msgs.join(' | ');
    } catch (e) {
        status.textContent = '❌ ' + e.message;
    }
}
