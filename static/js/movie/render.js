/* Movie Ad Generator — video generation (single 8s clip) */

var clipModels = {};

async function loadClipModels() {
    try {
        var resp = await fetch('/api/movie/clip-models');
        if (resp.ok) clipModels = await resp.json();
    } catch (e) {}
}

function renderVideoClipsStep() {
    var container = document.getElementById('video-clips-container');
    if (!movieState.project || !movieState.project.screenplay) {
        container.innerHTML = '<p style="color:#999">Chưa có kịch bản. Quay lại bước 3.</p>';
        return;
    }

    var sceneImage = movieState.project.scene_image;
    var videoClip = movieState.project.video_clip;

    if (!sceneImage) {
        container.innerHTML = '<div style="padding:20px;background:#fef2f2;border-radius:8px;text-align:center"><p style="color:#ef4444">⚠️ Cần tạo scene image trước (Bước 4)</p></div>';
        return;
    }

    var html = '';

    // Model selector + generate button
    html += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap">';
    html += '<label style="font-size:.85em;margin:0;font-weight:600">Model:</label>';
    html += '<select id="clip-model-select" style="padding:6px 10px;border-radius:6px;border:1.5px solid #ddd;font-size:.85em">';
    for (var key in clipModels) {
        html += '<option value="' + key + '">' + clipModels[key] + '</option>';
    }
    if (!Object.keys(clipModels).length) {
        html += '<option value="veo-3.1-fast-generate-preview">Veo 3.1 Fast</option>';
    }
    html += '</select>';

    if (!videoClip) {
        html += '<button onclick="generateVideo()" class="btn" style="padding:10px 20px;font-size:.9em">🎬 Tạo video 8s</button>';
    } else {
        html += '<button onclick="generateVideo()" class="btn btn-secondary" style="padding:6px 12px;font-size:.8em">🔄 Tạo lại</button>';
    }
    html += '<span id="video-gen-status" style="font-size:.85em;color:#666"></span>';
    html += '</div>';

    // Video preview
    if (videoClip) {
        html += '<div style="border:2px solid #10b981;border-radius:10px;overflow:hidden">';
        html += '<div style="background:#f0fdf4;padding:8px 12px;border-bottom:1px solid #d1fae5">';
        html += '<strong style="font-size:.9em;color:#10b981">✅ Video 8s — sẵn sàng xuất</strong>';
        html += '</div>';
        html += '<div style="padding:12px;text-align:center">';
        html += '<video src="' + videoClip + '?t=' + Date.now() + '" controls playsinline style="width:100%;max-height:500px;border-radius:8px;background:#000"></video>';
        html += '</div></div>';
    }

    container.innerHTML = html;
}

async function generateVideo() {
    if (!movieState.project) return;

    var status = document.getElementById('video-gen-status');
    var model = document.getElementById('clip-model-select')?.value || '';
    if (status) status.textContent = '⏳ Đang tạo video (30-60s)...';

    try {
        var resp = await fetch('/api/movie/project/' + movieState.project.id + '/generate-video?model=' + encodeURIComponent(model), {
            method: 'POST'
        });
        if (!resp.ok) { var err = await resp.json(); throw new Error(err.detail); }
        var data = await resp.json();

        movieState.project.video_clip = data.video_url;
        movieState.project.segment_videos = {"0": data.video_url};
        if (status) status.textContent = '✅ Video xong!';
        renderVideoClipsStep();
    } catch (e) {
        if (status) status.textContent = '❌ ' + e.message;
    }
}
