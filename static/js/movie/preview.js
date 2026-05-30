/* Scene image generation — single key frame */

async function generateSceneImage() {
    if (!movieState.project) { alert('Tạo project trước'); return; }

    var card = document.getElementById('scene-img-area');
    card.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:300px;background:#f0f2f5;border-radius:8px"><p style="color:#666">⏳ Đang tạo ảnh...</p></div>';

    try {
        var resp = await fetch('/api/movie/project/' + movieState.project.id + '/scene-image', {
            method: 'POST'
        });
        if (!resp.ok) { var err = await resp.json(); throw new Error(err.detail); }
        var data = await resp.json();
        movieState.project.scene_image = data.image_url;
        renderSceneImageCard(data.image_url);
    } catch (e) {
        card.innerHTML = '<div style="padding:20px;background:#fef2f2;border-radius:8px;text-align:center"><p style="color:#ef4444">❌ ' + e.message + '</p><button onclick="generateSceneImage()" class="btn" style="padding:6px 14px;font-size:.85em;margin-top:8px">🔄 Thử lại</button></div>';
    }
}

function renderSceneImageCard(imageUrl) {
    var card = document.getElementById('scene-img-area');
    var html = '<div style="position:relative">';
    html += '<img src="' + imageUrl + '?t=' + Date.now() + '" style="width:100%;max-height:500px;object-fit:contain;border-radius:8px;background:#000">';
    html += '<div style="position:absolute;bottom:8px;right:8px;display:flex;gap:4px">';
    html += '<button onclick="generateSceneImage()" style="padding:4px 10px;border:none;background:rgba(0,0,0,.7);color:#fff;border-radius:6px;cursor:pointer;font-size:.8em">🔄 Tạo lại</button>';
    html += '<button onclick="window.open(\'' + imageUrl + '\',\'_blank\')" style="padding:4px 10px;border:none;background:rgba(0,0,0,.7);color:#fff;border-radius:6px;cursor:pointer;font-size:.8em">🔍 Phóng to</button>';
    html += '</div></div>';
    card.innerHTML = html;
}

function renderSceneImagesStep() {
    var container = document.getElementById('scene-images-container');
    if (!movieState.project || !movieState.project.screenplay) {
        container.innerHTML = '<p style="color:#999">Chưa có kịch bản. Quay lại bước 3.</p>';
        return;
    }

    var sp = movieState.project.screenplay;
    var existingImage = movieState.project.scene_image;
    var html = '';

    html += '<div style="border:1px solid #ddd;border-radius:10px;overflow:hidden">';

    // Header
    html += '<div style="background:#f8f9fa;padding:10px 14px;border-bottom:1px solid #eee;display:flex;justify-content:space-between;align-items:center">';
    html += '<strong>Scene Key Frame — ' + (sp.mood || '') + '</strong>';
    html += '<span style="font-size:.8em;color:#666">16 giây (single continuous take)</span>';
    html += '</div>';

    // Two-column: screenplay info | image
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0">';

    // Left: screenplay details
    html += '<div style="padding:12px;border-right:1px solid #f0f0f0;font-size:.82em;overflow-y:auto;max-height:550px">';
    html += '<div style="margin-bottom:10px"><strong style="color:#7c3aed">🖼️ Key Frame:</strong><br>' + (sp.key_frame_description || '<em>—</em>') + '</div>';

    // Shots breakdown
    var shots = sp.shots || [];
    if (shots.length) {
        html += '<div style="margin-bottom:10px"><strong style="color:#e94560">🎞️ Shots/Beats:</strong></div>';
        shots.forEach(function (shot) {
            html += '<div style="background:#fafafa;border-radius:6px;padding:6px 8px;margin-bottom:6px;border-left:3px solid #e94560">';
            html += '<div style="display:flex;justify-content:space-between;font-size:.9em;font-weight:600">';
            html += '<span>' + (shot.timing || '') + '</span>';
            html += '<span style="color:#666">' + (shot.framing || '') + '</span>';
            html += '</div>';
            html += '<div style="margin-top:3px">' + (shot.action || '') + '</div>';
            html += '<div style="margin-top:2px;font-size:.85em;color:#888">';
            html += '📐 ' + (shot.framing || '') + ' · 🎥 ' + (shot.camera_movement || '') + ' · 💡 ' + (shot.lighting || '');
            html += '</div></div>';
        });
    }

    // Motion prompts
    html += '<div style="margin-bottom:8px;padding:8px;background:#f0f7ff;border-radius:6px;border-left:3px solid #0ea5e9">';
    html += '<strong style="color:#0ea5e9;font-size:.9em">🎯 Motion (0-8s):</strong><br><span style="font-style:italic">' + (sp.motion_prompt || '<em>—</em>') + '</span>';
    html += '</div>';

    html += '<div style="margin-bottom:8px;padding:8px;background:#f0fdf4;border-radius:6px;border-left:3px solid #10b981">';
    html += '<strong style="color:#10b981;font-size:.9em">🔗 Extend (8-16s):</strong><br><span style="font-style:italic">' + (sp.extend_prompt || '<em>—</em>') + '</span>';
    html += '</div>';

    if (sp.dialogue) {
        html += '<div style="padding:8px;background:#fffbeb;border-radius:6px;border-left:3px solid #f59e0b">';
        html += '<strong style="color:#f59e0b;font-size:.9em">💬 Dialogue:</strong><br>"' + sp.dialogue + '"';
        html += '</div>';
    }
    html += '</div>';

    // Right: image
    html += '<div id="scene-img-area" style="padding:12px;display:flex;align-items:center;justify-content:center">';
    if (existingImage) {
        html += '<div style="position:relative;width:100%">';
        html += '<img src="' + existingImage + '?t=' + Date.now() + '" style="width:100%;max-height:500px;object-fit:contain;border-radius:8px;background:#000">';
        html += '<div style="position:absolute;bottom:8px;right:8px;display:flex;gap:4px">';
        html += '<button onclick="generateSceneImage()" style="padding:4px 10px;border:none;background:rgba(0,0,0,.7);color:#fff;border-radius:6px;cursor:pointer;font-size:.8em">🔄 Tạo lại</button>';
        html += '<button onclick="window.open(\'' + existingImage + '\',\'_blank\')" style="padding:4px 10px;border:none;background:rgba(0,0,0,.7);color:#fff;border-radius:6px;cursor:pointer;font-size:.8em">🔍 Phóng to</button>';
        html += '</div></div>';
    } else {
        html += '<div style="display:flex;align-items:center;justify-content:center;width:100%;height:300px;background:#f8f9fa;border-radius:8px">';
        html += '<button onclick="generateSceneImage()" class="btn" style="padding:12px 24px;font-size:1em">🖼️ Tạo Scene Image</button>';
        html += '</div>';
    }
    html += '</div>';

    html += '</div>'; // grid
    html += '</div>'; // card

    container.innerHTML = html;
}
