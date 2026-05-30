/* Video generation, presets, image management, AI images */

var PRESETS = {
    product: ['ken_burns', 'vignette'],
    tiktok: ['bounce_zoom', 'flash'],
    luxury: ['parallax', 'soft_glow'],
    vintage: ['ken_burns', 'sepia'],
    warm: ['ken_burns', 'color_tint'],
    focus: ['zoom_center', 'none'],
    unboxing: ['none', 'none'],
    genz: ['bounce_zoom', 'glitch'],
};

function applyPreset(val) {
    var custom = document.getElementById('custom-effects');
    var ef = document.getElementById('img-effect');
    var st = document.getElementById('img-style');
    if (val === 'custom') {
        custom.style.display = 'flex';
        return;
    }
    custom.style.display = 'none';
    var p = PRESETS[val] || ['ken_burns', 'none'];
    ef.value = p[0];
    st.value = p[1];
}

function limitVideoImages(cb) {
    const checked = document.querySelectorAll('.vid-img-check:checked');
    if (checked.length > 16) { cb.checked = false; return; }
    document.querySelectorAll('.vid-img-check').forEach(c => {
        const img = c.nextElementSibling;
        if (img) img.style.borderColor = c.checked ? '#e94560' : 'transparent';
    });
}

function removeVidImg(label) {
    label.remove();
}

function previewVideoUploads(input) {
    var preview = document.getElementById('video-upload-preview');
    var gallery = document.getElementById('vid-img-gallery');
    preview.innerHTML = '';
    gallery.querySelectorAll('.uploaded-img-item').forEach(el => el.remove());
    Array.from(input.files).forEach(function (file, i) {
        if (file.type.startsWith('video/')) {
            var div = document.createElement('div');
            div.style.cssText = 'position:relative;display:inline-block';
            var vid = document.createElement('video');
            vid.src = URL.createObjectURL(file);
            vid.style.cssText = 'height:80px;border-radius:6px';
            vid.controls = true;
            div.appendChild(vid);
            var cb = document.createElement('input');
            cb.type = 'checkbox'; cb.className = 'vid-upload-check'; cb.checked = true;
            cb.dataset.index = i;
            cb.style.cssText = 'position:absolute;top:4px;left:4px;width:18px;height:18px;z-index:2';
            div.insertBefore(cb, div.firstChild);
            preview.appendChild(div);
        } else {
            var label = document.createElement('label');
            label.className = 'uploaded-img-item';
            label.style.cssText = 'position:relative;cursor:pointer';
            var url = URL.createObjectURL(file);
            label.innerHTML = `<input type="checkbox" class="vid-img-check vid-upload-check" value="__upload_${i}" data-index="${i}" checked style="position:absolute;top:4px;left:4px;width:18px;height:18px;z-index:2" onchange="limitVideoImages(this)">` +
                `<span style="position:absolute;top:4px;right:28px;background:#25F4EE;color:#333;font-size:10px;padding:1px 5px;border-radius:4px;z-index:3">📤</span>` +
                `<img src="${url}" style="height:100px;border-radius:6px;border:2px solid #25F4EE">` +
                `<button type="button" onclick="removeUploadedImg(this.parentElement,${i})" style="position:absolute;top:-6px;right:-6px;background:#e94560;color:#fff;border:none;border-radius:50%;width:20px;height:20px;cursor:pointer;font-size:12px;line-height:20px;padding:0;z-index:3">✕</button>`;
            gallery.appendChild(label);
        }
    });
    var hint = gallery.previousElementSibling;
    if (hint && gallery.children.length > 0) {
        hint.textContent = '☑️ Chọn ảnh cho video & AI (tối đa 16):';
        hint.style.color = '#666';
    }
}

function removeUploadedImg(label, index) {
    label.remove();
    var input = document.getElementById('video-media-upload');
    removeVideoFile(input, index);
}

function removeVideoFile(input, index) {
    var dt = new DataTransfer();
    Array.from(input.files).forEach(function (f, i) { if (i !== index) dt.items.add(f); });
    input.files = dt.files;
    previewVideoUploads(input);
}

function previewUploads(input) {
    const preview = document.getElementById('upload-preview');
    preview.innerHTML = '';
    const dt = new DataTransfer();
    Array.from(input.files).forEach((file, i) => {
        dt.items.add(file);
        const div = document.createElement('div');
        div.style.cssText = 'position:relative;display:inline-block';
        if (file.type.startsWith('video/')) {
            const vid = document.createElement('video');
            vid.src = URL.createObjectURL(file);
            vid.style.cssText = 'height:80px;border-radius:6px';
            vid.controls = true;
            div.appendChild(vid);
        } else {
            const img = document.createElement('img');
            img.src = URL.createObjectURL(file);
            img.style.cssText = 'height:80px;border-radius:6px';
            div.appendChild(img);
        }
        const btn = document.createElement('button');
        btn.textContent = '✕';
        btn.style.cssText = 'position:absolute;top:-6px;right:-6px;background:#e94560;color:#fff;border:none;border-radius:50%;width:20px;height:20px;cursor:pointer;font-size:12px;line-height:20px;padding:0';
        btn.onclick = () => { div.remove(); removeFile(input, i); };
        div.appendChild(btn);
        preview.appendChild(div);
    });
}

function removeFile(input, index) {
    const dt = new DataTransfer();
    Array.from(input.files).forEach((f, i) => { if (i !== index) dt.items.add(f); });
    input.files = dt.files;
    previewUploads(input);
}

function getVideoFormData() {
    const platform = document.getElementById('video-platform').value;
    const selected = Array.from(document.querySelectorAll('.vid-img-check:checked')).map(c => c.value);
    const textarea = document.getElementById('post-' + platform);
    if (textarea && window._lastReviewData?.[platform]) window._lastReviewData[platform].social_post = textarea.value;
    const fd = new FormData();
    fd.append('review_json', JSON.stringify(window._lastReviewData));
    fd.append('pdf_path', window._lastPdfPath || '');
    fd.append('platform', platform);
    fd.append('selected_images', JSON.stringify(selected));
    fd.append('music_volume', document.getElementById('music-volume')?.value || '15');
    fd.append('aspect_ratio', document.getElementById('video-aspect')?.value || '9:16');
    fd.append('subtitle_style', document.getElementById('subtitle-style')?.value || 'tiktok');
    fd.append('highlight_color', document.getElementById('highlight-color')?.value || '#FFD700');
    fd.append('img_effect', document.getElementById('img-effect')?.value || 'ken_burns');
    fd.append('img_transition', document.getElementById('img-transition')?.value || '');
    fd.append('img_style', document.getElementById('img-style')?.value || 'none');
    fd.append('zoom_ratio', document.getElementById('zoom-ratio')?.value || '15');
    fd.append('show_intro', document.getElementById('show-intro')?.checked ? '1' : '0');
    fd.append('show_outro', document.getElementById('show-outro')?.checked ? '1' : '0');
    const introBg = document.getElementById('intro-bg-select')?.value || '';
    if (introBg) fd.append('intro_bg_url', introBg);
    const outroBg = document.getElementById('outro-bg-select')?.value || '';
    if (outroBg) fd.append('outro_bg_url', outroBg);
    const logoFile = document.getElementById('video-logo')?.files?.[0];
    if (logoFile) fd.append('logo', logoFile);
    fd.append('logo_text', document.getElementById('logo-text')?.value?.trim() || '');
    fd.append('logo_position', document.getElementById('logo-position')?.value || 'top-right');
    const voice = getGlobalVoice();
    fd.append('voice_type', voice.type);
    fd.append('voice_id', voice.voiceId);
    fd.append('voice_speed', String(100 + parseInt(voice.speed)));
    const musicSel = document.getElementById('music-select');
    const customUrl = document.getElementById('custom-music-url')?.value?.trim();
    const customFile = document.getElementById('custom-music-file')?.files?.[0];
    if (customFile) fd.append('music_upload', customFile);
    else if (customUrl) fd.append('music_file', customUrl);
    else if (musicSel?.value) fd.append('music_file', musicSel.value);
    const uploadEl = document.getElementById('video-media-upload');
    if (uploadEl?.files) {
        const checked = new Set();
        document.querySelectorAll('.vid-upload-check:checked').forEach(cb => checked.add(parseInt(cb.dataset.index)));
        for (let i = 0; i < Math.min(uploadEl.files.length, 8); i++) {
            if (checked.size === 0 || checked.has(i)) fd.append('media', uploadEl.files[i]);
        }
    }
    document.getElementById('music-preview')?.pause();
    return { fd, platform };
}

async function previewVideo() {
    const btn = document.getElementById('btn-preview');
    const pr = document.getElementById('preview-result');
    btn.disabled = true; btn.textContent = '⏳ Preview...';
    try {
        const { fd } = getVideoFormData();
        fd.append('preview_only', '1');
        const resp = await fetch('/generate-video', { method: 'POST', body: fd });
        if (!resp.ok) { const err = await resp.json(); throw new Error(err.detail || 'Lỗi'); }
        const data = await resp.json();
        pr.innerHTML = `<img src="${data.preview_url}" style="max-width:300px;border-radius:12px;border:2px solid #ddd">
            <p style="font-size:.85em;color:#666;margin-top:4px">Preview — nhấn "Tạo Video" để render</p>`;
    } catch (e) { pr.innerHTML = `<p style="color:red">❌ ${e.message}</p>`; }
    finally { btn.disabled = false; btn.textContent = '👁️ Xem trước'; }
}

async function generateVideo() {
    const btn = document.getElementById('btn-video');
    const vr = document.getElementById('video-result');
    btn.disabled = true; btn.textContent = '⏳ Đang tạo video...'; vr.innerHTML = '';
    try {
        const { fd, platform } = getVideoFormData();
        const resp = await fetch('/generate-video', { method: 'POST', body: fd });
        if (!resp.ok) { const err = await resp.json(); throw new Error(err.detail || 'Lỗi'); }
        const data = await resp.json();
        const label = platform === 'facebook' ? 'Facebook Reels' : 'TikTok';
        let h = `<video controls style="width:100%;max-width:400px;border-radius:12px"><source src="${data.video_url}" type="video/mp4"></video>
            <br><a href="${data.video_url}" download class="btn" style="margin-top:8px;display:inline-block;font-size:.9em">⬇️ ${label}</a>`;
        if (data.srt_url) h += `<br><a href="${data.srt_url}" download style="font-size:.85em;color:#0f3460;margin-top:4px;display:inline-block">📝 Phụ đề SRT</a>`;
        h += `<br><select id="fb-page-select" style="padding:4px 8px;border-radius:6px;border:1px solid #ddd;font-size:.8em;margin-top:8px"><option value="">Trang FB mặc định</option></select>`;
        h += ` <button class="btn" onclick="publishVideo('${data.video_url}','facebook')" style="margin-top:8px;font-size:.9em;background:#1877f2">📤 Đăng Facebook Reels</button>`;
        h += ` <button class="btn" onclick="publishVideo('${data.video_url}','instagram')" style="margin-top:8px;font-size:.9em;background:linear-gradient(45deg,#f09433,#e6683c,#dc2743,#cc2366,#bc1888)">📷 Đăng Instagram Reels</button>`;
        h += ` <button class="btn" onclick="publishVideo('${data.video_url}','tiktok')" style="margin-top:8px;font-size:.9em;background:#000">🎵 Đăng TikTok</button>`;
        h += ` <button class="btn" onclick="publishVideo('${data.video_url}','youtube')" style="margin-top:8px;font-size:.9em;background:#c00">▶️ YouTube Shorts</button>`;
        h += ` <button class="btn" onclick="publishVideo('${data.video_url}','threads')" style="margin-top:8px;font-size:.9em;background:#000">🧵 Đăng Threads</button>`;
        h += `<br><select id="schedule-slot" style="padding:4px 8px;border-radius:6px;border:1px solid #ddd;font-size:.8em;margin-top:8px" onchange="document.getElementById('schedule-custom-dt').style.display=this.value==='custom'?'inline':'none'"><option value="">Slot tiếp theo</option><option value="08:30">08:30</option><option value="12:00">12:00</option><option value="19:00">19:00</option><option value="21:30">21:30</option><option value="custom">📅 Tùy chọn...</option></select>`;
        h += `<input type="datetime-local" id="schedule-custom-dt" style="padding:4px 8px;border-radius:6px;border:1px solid #ddd;font-size:.8em;margin-left:4px;display:none">`;
        h += ` <button class="btn" onclick="scheduleVideo('${data.video_url}','all')" style="margin-top:8px;font-size:.9em;background:#f59e0b">⏰ Lên lịch</button>`;
        h += `<span id="publish-status" style="font-size:.85em;margin-left:8px"></span>`;
        vr.innerHTML = h;
        loadFbPageSelect('fb-page-select');
    } catch (e) { vr.innerHTML = `<p style="color:red">❌ ${e.message}</p>`; }
    finally { btn.disabled = false; btn.textContent = '🎬 Tạo Video'; }
}

async function batchGenerate() {
    const btn = document.getElementById('btn-batch');
    const vr = document.getElementById('video-result');
    btn.disabled = true; btn.textContent = '⏳ Đang tạo 3 video...'; vr.innerHTML = '';
    const configs = [['9:16', 'tiktok', 'TikTok'], ['9:16', 'facebook', 'Reels'], ['9:16', 'tiktok', 'YouTube Shorts']];
    let html = '';
    for (const [aspect, plat, label] of configs) {
        try {
            const { fd } = getVideoFormData();
            fd.set('aspect_ratio', aspect); fd.set('platform', plat);
            const resp = await fetch('/generate-video', { method: 'POST', body: fd });
            if (!resp.ok) throw new Error('Lỗi');
            const data = await resp.json();
            const pubPlatform = label === 'Reels' ? 'facebook' : (label === 'TikTok' ? 'tiktok' : 'youtube');
            const pubColors = { tiktok: '#000', facebook: '#1877f2', youtube: '#c00' };
            html += `<div style="display:inline-block;margin:8px;vertical-align:top">
                <video controls style="max-width:220px;border-radius:8px"><source src="${data.video_url}" type="video/mp4"></video>
                <br><a href="${data.video_url}" download class="btn" style="font-size:.8em;padding:6px 12px;margin-top:4px;display:inline-block">⬇️ ${label}</a>
                <button class="btn" onclick="publishVideo('${data.video_url}','${pubPlatform}')" style="font-size:.8em;padding:6px 12px;margin-top:4px;background:${pubColors[pubPlatform]}">📤 Đăng</button>
                <span id="pub-status-${pubPlatform}" style="font-size:.8em;display:block;margin-top:4px"></span></div>`;
            vr.innerHTML = html + '<p style="font-size:.85em;color:#666">Đang tạo...</p>';
        } catch (e) { html += `<p style="color:red;font-size:.85em">❌ ${label}: ${e.message}</p>`; }
    }
    vr.innerHTML = html;
    btn.disabled = false; btn.textContent = '📦 Tạo tất cả';
}

async function generateAiImages() {
    var btn = document.getElementById('btn-ai-images');
    var status = document.getElementById('ai-img-status');
    if (!window._lastReviewData) { status.textContent = '❌ Tạo review trước'; return; }
    btn.disabled = true; btn.textContent = '⏳ Đang tạo...';
    status.textContent = '';
    try {
        var data = window._lastReviewData;
        var persona = data.tiktok || data.facebook || {};
        var fd = new FormData();
        fd.append('title', data.book?.title || '');
        fd.append('persona_name', 'Khách hàng');
        fd.append('persona_focus', persona.key_points?.[0] || '');
        var checkedUrls = Array.from(document.querySelectorAll('.vid-img-check:checked'))
            .map(c => c.value)
            .filter(u => !u.includes('ai_images') && !u.startsWith('__upload_'));
        fd.append('product_images', JSON.stringify(
            checkedUrls.concat(data.product_images || []).filter((v, i, a) => a.indexOf(v) === i).slice(0, 6)
        ));
        var uploadEl = document.getElementById('video-media-upload');
        if (uploadEl?.files) {
            var checkedUploads = new Set();
            document.querySelectorAll('.vid-img-check.vid-upload-check:checked').forEach(cb => {
                checkedUploads.add(parseInt(cb.dataset.index));
            });
            for (var i = 0; i < Math.min(uploadEl.files.length, 6); i++) {
                if (checkedUploads.has(i) && uploadEl.files[i].type.startsWith('image/')) {
                    fd.append('media', uploadEl.files[i]);
                }
            }
        }
        var resp = await fetch('/generate-ai-images', { method: 'POST', body: fd });
        var result = await resp.json();
        var aiImgs = result.ai_images || [];
        if (aiImgs.length > 0) {
            var gallery = document.getElementById('vid-img-gallery');
            if (gallery) {
                aiImgs.forEach(function (url) {
                    var label = document.createElement('label');
                    label.style.cssText = 'position:relative;cursor:pointer';
                    label.innerHTML = '<input type="checkbox" class="vid-img-check" value="' + url + '" checked style="position:absolute;top:4px;left:4px;width:18px;height:18px;z-index:2" onchange="limitVideoImages(this)">' +
                        '<span style="position:absolute;top:4px;right:28px;background:#7c3aed;color:#fff;font-size:10px;padding:1px 5px;border-radius:4px;z-index:3">🤖 AI</span>' +
                        '<img src="' + url + '" style="height:100px;border-radius:6px;border:2px solid #7c3aed">' +
                        '<button type="button" data-img="' + url + '" onclick="regenAiImage(this,this.dataset.img)" style="position:absolute;bottom:4px;right:4px;background:#7c3aed;color:#fff;border:none;border-radius:4px;padding:2px 6px;cursor:pointer;font-size:11px;z-index:3">🔄</button>';
                    gallery.appendChild(label);
                });
            }
            status.textContent = '✅ ' + aiImgs.length + ' ảnh AI đã tạo';
        } else {
            status.textContent = '❌ Không tạo được ảnh AI';
        }
    } catch (e) { status.textContent = '❌ ' + e.message; }
    btn.disabled = false; btn.textContent = '🖼️ Tạo ảnh AI';
}

async function regenAiImage(btn, oldUrl) {
    var label = btn.parentElement;
    btn.textContent = '⏳';
    btn.disabled = true;
    try {
        var imgs = (window._lastReviewData || {}).product_images || window._productImages || [];
        var productImg = imgs.find(function (u) { return !u.includes('ai_images'); }) || imgs[0] || '';
        if (!productImg) throw new Error('Không có ảnh sản phẩm');
        var fd = new FormData();
        fd.append('scene', 'Create a lifestyle photo of a Vietnamese person with this product. Different angle and background. Warm lighting. TikTok product photography.');
        fd.append('product_image', productImg);
        var resp = await fetch('/regenerate-image', { method: 'POST', body: fd });
        if (!resp.ok) throw new Error('Failed');
        var data = await resp.json();
        var newUrl = data.image_url;
        var img = label.querySelector('img');
        if (img) img.src = newUrl;
        var cb = label.querySelector('input[type=checkbox]');
        if (cb) cb.value = newUrl;
        btn.textContent = '🔄';
    } catch (e) {
        btn.textContent = '❌';
        setTimeout(function () { btn.textContent = '🔄'; }, 2000);
    }
    btn.disabled = false;
}

// Nova Reel AI Video
function setNovaPrompt(text) {
    document.getElementById('nova-prompt').value = text;
}

function previewNovaMedia(input) {
    var preview = document.getElementById('nova-media-preview');
    preview.innerHTML = '';
    if (input.files.length > 16) {
        alert('Tối đa 8 files!');
        input.value = '';
        return;
    }
    Array.from(input.files).forEach(function (file, i) {
        var div = document.createElement('div');
        div.style.cssText = 'position:relative;display:inline-block';
        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.className = 'nova-media-check';
        cb.dataset.index = i;
        cb.style.cssText = 'position:absolute;top:4px;left:4px;width:18px;height:18px;z-index:2';
        if (i < 2) cb.checked = true;
        cb.onchange = function () {
            var checked = document.querySelectorAll('.nova-media-check:checked');
            if (checked.length > 2) { this.checked = false; alert('Chọn tối đa 2 ảnh/video cho AI!'); }
        };
        div.appendChild(cb);
        if (file.type.startsWith('video/')) {
            var vid = document.createElement('video');
            vid.src = URL.createObjectURL(file);
            vid.style.cssText = 'height:80px;border-radius:6px';
            vid.controls = true;
            div.appendChild(vid);
        } else {
            var img = document.createElement('img');
            img.src = URL.createObjectURL(file);
            img.style.cssText = 'height:80px;border-radius:6px;border:2px solid ' + (i < 2 ? '#6a0572' : 'transparent');
            div.appendChild(img);
        }
        preview.appendChild(div);
    });
}

async function novaReelGenerate() {
    const prompt = document.getElementById('nova-prompt')?.value?.trim();
    if (!prompt) { alert('Nhập mô tả video!'); return; }
    const btn = document.getElementById('btn-nova');
    const nr = document.getElementById('nova-result');
    btn.disabled = true; btn.textContent = '⏳ Đang tạo (~90s)...';
    nr.innerHTML = '<p style="font-size:.85em;color:#666">Đang gửi yêu cầu tới Nova Reel...</p>';
    try {
        const fd = new FormData();
        fd.append('prompt', prompt);
        fd.append('nova_duration', document.getElementById('nova-duration')?.value || '6');
        const novaInput = document.getElementById('nova-media');
        if (novaInput?.files) {
            const checked = new Set();
            document.querySelectorAll('.nova-media-check:checked').forEach(cb => checked.add(parseInt(cb.dataset.index)));
            for (let i = 0; i < novaInput.files.length; i++) {
                if (checked.has(i)) fd.append('nova_media', novaInput.files[i]);
            }
        }
        const resp = await fetch('/nova-reel', { method: 'POST', body: fd });
        if (!resp.ok) { const err = await resp.json(); throw new Error(err.detail || 'Lỗi'); }
        const data = await resp.json();
        nr.innerHTML = `<p style="font-size:.85em;color:#666">⏳ Video đang render... Kiểm tra sau 90 giây.</p>`;
        const arn = data.invocation_arn;
        for (let i = 0; i < 30; i++) {
            await new Promise(ok => setTimeout(ok, 5000));
            const sr = await fetch(`/nova-reel-status?arn=${encodeURIComponent(arn)}`);
            const sd = await sr.json();
            if (sd.status === 'COMPLETED') {
                nr.innerHTML = `<p style="color:green">✅ Video tạo xong!</p>
                    <p style="font-size:.85em">S3: ${sd.s3_uri}</p>
                    <p style="font-size:.85em;color:#666">Tải video từ S3 console hoặc dùng: aws s3 cp ${sd.s3_uri} ./output/</p>`;
                break;
            } else if (sd.status === 'FAILED') {
                nr.innerHTML = `<p style="color:red">❌ Lỗi: ${sd.error}</p>`;
                break;
            }
            nr.innerHTML = `<p style="font-size:.85em;color:#666">⏳ Đang render... (${(i + 1) * 5}s)</p>`;
        }
    } catch (e) { nr.innerHTML = `<p style="color:red">❌ ${e.message}</p>`; }
    finally { btn.disabled = false; btn.textContent = '🎬 Tạo AI Video'; }
}
