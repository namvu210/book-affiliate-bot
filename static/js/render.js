/* Result rendering: takes review data and builds the result DOM */

function renderResult(data) {
    const r = document.getElementById('result');
    let html = '';

    const bmPreview = document.getElementById('bookmarklet-preview');
    if (bmPreview) bmPreview.innerHTML = '';

    if (data.book) {
        html += `<div class="book-meta">
            <strong>📖 ${data.book.title}</strong> — ${data.book.author}
            ${data.book.price ? ' | 💰 ' + data.book.price : ''}
            ${data.book.rating ? ' | ⭐ ' + data.book.rating + '/5 (' + data.book.rating_count + ' đánh giá)' : ''}
            ${data.book.review_count_used ? ' | 💬 ' + data.book.review_count_used + ' nhận xét thực được phân tích' : ''}
            ${data.book.shopee_url ? ' | <a href="' + data.book.shopee_url + '" target="_blank">🛒 Shopee</a>' : ''}
        </div>`;
    }

    const imgs = data.product_images || data.product_images_original || [];
    const localImgs = data.product_images || [];
    if (imgs.length > 0) {
        window._productImages = localImgs.length ? localImgs : imgs;
    }

    const platforms = [data.facebook ? 'facebook' : null].filter(Boolean);
    if (!platforms.length && data.review) platforms.push(null);
    for (const p of platforms) {
        const d = p ? data[p] : data;
        if (!d) continue;
        const label = '📝 Review';
        const postText = d.social_post || d.review || '';

        html += `<div class="result-card">
            <h3>${p ? label : '📝 Review'}
                <button class="copy-btn" onclick="copyText('post-${p || 'single'}')">📋 Copy</button>
                <button class="copy-btn" onclick="regenReview('${p || 'single'}')" id="btn-regen-${p || 'single'}" style="background:#7c3aed;margin-right:4px">🔄 Tạo lại</button>
            </h3>
            <textarea id="post-${p || 'single'}" rows="10" style="width:100%;padding:12px;border:1.5px solid #ddd;border-radius:8px;font-size:.9em;line-height:1.6;font-family:inherit;resize:vertical">${postText}</textarea>
            <div style="margin-top:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                <button class="btn" onclick="generateSpeech('${p || 'single'}')" id="btn-speech-${p || 'single'}" style="padding:8px 20px;font-size:.9em">
                    🔊 Tạo giọng nói
                </button>
                <div id="audio-${p || 'single'}">${d.audio_url ? `<audio controls style="height:36px"><source src="${d.audio_url}" type="audio/mpeg"></audio><a href="${d.audio_url}" download style="font-size:.85em;margin-left:4px">⬇️</a>` : ''}</div>
            </div>
            <div class="tags" style="margin-top:8px">${(d.hashtags || []).map(t => '<span class="tag">' + t + '</span>').join('')}</div>
        </div>`;

        if (d.hook) {
            html += `<div class="result-card">
                <h3>🎬 Hook (mở đầu video)</h3>
                <pre>${d.hook}</pre>
            </div>`;
        }

        if (d.key_points) {
            html += `<div class="result-card">
                <h3>✨ Điểm nổi bật</h3>
                <ul style="padding-left:20px">${d.key_points.map(p => '<li>' + p + '</li>').join('')}</ul>
            </div>`;
        }

        const captionText = (d.social_post || '').replace(/\[[a-zA-Z_ ]+\]/g, '').replace(/  +/g, ' ').trim();
        const hashtags = (d.hashtags || []).map(h => '#' + h.replace(/^#/, '')).join(' ');
        const affLink = data.affiliate_link || data.book?.shopee_url || '';
        const fullCaption = captionText + (hashtags ? '\n\n' + hashtags : '') + (affLink ? '\n\n🛒 Mua ngay: ' + affLink : '');

        html += `<div class="result-card">
            <h3>📤 Caption khi đăng <button class="copy-btn" onclick="navigator.clipboard.writeText(document.getElementById('caption-preview').textContent)">📋 Copy</button></h3>
            <pre id="caption-preview" style="white-space:pre-wrap;background:#f8f9fa;padding:12px;border-radius:8px;font-family:inherit;font-size:.9em;line-height:1.6;border:1px solid #eee">${fullCaption}</pre>
        </div>`;
    }

    if (data.tiktok || data.facebook) {
        html += renderVideoSection(data);
        window._lastReviewData = data;
        loadMusicList();
        loadTemplateList();
    }

    r.innerHTML = html;
}

function renderVideoSection(data) {
    const vidImgs = data.product_images || [];
    let html = `<div class="result-card">
        <h3>🎬 Tạo Video</h3>
        <div style="display:flex;gap:12px;align-items:center;margin-bottom:12px;flex-wrap:wrap">
            <select id="video-platform" style="padding:8px 12px;border-radius:8px;border:1.5px solid #ddd">
                ${data.tiktok ? '<option value="tiktok">🎵 TikTok</option>' : ''}
                ${data.facebook ? '<option value="facebook">📘 Facebook Reels</option>' : ''}
            </select>
            <select id="video-aspect" style="padding:8px 12px;border-radius:8px;border:1.5px solid #ddd">
                <option value="9:16">📱 9:16 (TikTok/Reels)</option>
                <option value="1:1">⬜ 1:1 (Instagram)</option>
                <option value="16:9">🖥️ 16:9 (YouTube)</option>
            </select>
        </div>
        <div style="display:flex;gap:20px;margin-bottom:12px;flex-wrap:wrap">
            <label style="font-size:.85em;display:flex;align-items:center;gap:6px">
                🔊 Nhạc nền: <span id="vol-val">15</span>%
                <input type="range" id="music-volume" min="0" max="50" value="15" step="5" style="width:100px" oninput="document.getElementById('vol-val').textContent=this.value">
            </label>
        </div>
        <div style="display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap">
            <label style="font-size:.85em">🎨 Kiểu phụ đề:
                <select id="subtitle-style" style="padding:6px 10px;border-radius:6px;border:1.5px solid #ddd;font-size:.85em">
                    <option value="tiktok">TikTok (viền vàng)</option>
                    <option value="news">Tin tức (nền đen)</option>
                    <option value="karaoke">Karaoke (đổi màu)</option>
                    <option value="minimal">Tối giản (trắng)</option>
                </select>
            </label>
            <label style="font-size:.85em">🎨 Màu highlight:
                <input type="color" id="highlight-color" value="#FFD700" style="width:32px;height:28px;border:none;cursor:pointer;vertical-align:middle">
            </label>
            <label style="font-size:.85em">🎬 Phong cách video:
                <select id="video-preset" onchange="applyPreset(this.value)" style="padding:6px 10px;border-radius:6px;border:1.5px solid #ddd;font-size:.85em">
                    <option value="product" selected>📦 Sản phẩm — Ken Burns + Vignette</option>
                    <option value="tiktok">⚡ TikTok — Zoom nhịp + Flash</option>
                    <option value="luxury">✨ Cao cấp — Parallax + Soft Glow</option>
                    <option value="vintage">🎞️ Vintage — Ken Burns + Sepia</option>
                    <option value="warm">🧸 Ấm áp — Ken Burns + Phủ màu</option>
                    <option value="focus">🎯 Tập trung SP — Zoom trung tâm</option>
                    <option value="unboxing">📦 Unboxing — Pixelate Reveal</option>
                    <option value="genz">🔥 Gen Z — Rung lắc + Glitch</option>
                    <option value="custom">⚙️ Tùy chỉnh...</option>
                </select>
            </label>
            <div id="custom-effects" style="display:none;margin-top:8px;gap:8px;flex-wrap:wrap">
                <label style="font-size:.8em">📹 Chuyển động ảnh:
                    <select id="img-effect" style="padding:4px 8px;border-radius:4px;border:1px solid #ddd;font-size:.85em">
                        <option value="ken_burns">Ken Burns (zoom chậm)</option>
                        <option value="zoom_center">Zoom trung tâm</option>
                        <option value="parallax">Parallax (lớp nổi)</option>
                        <option value="slide_lr">Trượt ngang</option>
                        <option value="bounce_zoom">Zoom nhịp điệu</option>
                        <option value="rotate_tilt">Xoay nhẹ</option>
                        <option value="none">Không chuyển động</option>
                    </select>
                </label>
                <label style="font-size:.8em">🔀 Chuyển cảnh:
                    <select id="img-transition" style="padding:4px 8px;border-radius:4px;border:1px solid #ddd;font-size:.85em">
                        <option value="">Mặc định (theo chuyển động)</option>
                        <option value="whip_pan">Whip Pan</option>
                        <option value="glitch_trans">Glitch</option>
                        <option value="shutter">Shutter</option>
                        <option value="zoom_through">Zoom Through</option>
                        <option value="circle_iris">Circle Iris</option>
                        <option value="slip">Slip</option>
                        <option value="scroll_h">Scroll ngang</option>
                        <option value="scroll_v">Scroll dọc</option>
                        <option value="shooting_frame">Shooting Frame</option>
                        <option value="countdown">Countdown</option>
                    </select>
                </label>
                <label style="font-size:.8em">✨ Hiệu ứng phủ:
                    <select id="img-style" style="padding:4px 8px;border-radius:4px;border:1px solid #ddd;font-size:.85em">
                        <option value="none">Không</option>
                        <optgroup label="Màu sắc & ánh sáng">
                            <option value="vignette">Vignette</option>
                            <option value="soft_glow">Soft Glow</option>
                            <option value="color_tint">Phủ màu ấm</option>
                            <option value="color_pop">Color Pop</option>
                            <option value="neon_glow">Neon Glow</option>
                            <option value="light_leak">Light Leak</option>
                            <option value="scanning_light">Scanning Light</option>
                            <option value="halo">Halo</option>
                            <option value="club_mood">Club Mood</option>
                            <option value="cyberpunk">Cyberpunk</option>
                            <option value="camera_focus">Camera Focus</option>
                        </optgroup>
                        <optgroup label="Hạt & lấp lánh">
                            <option value="sparkles">Sparkles</option>
                            <option value="gold_sparkles">Gold Sparkles</option>
                            <option value="glitter_bomb">Glitter Bomb</option>
                            <option value="starlights">Starlights</option>
                            <option value="star_power">Star Power</option>
                            <option value="snowfall">Snowfall</option>
                            <option value="rainbow_heart">Rainbow Heart</option>
                            <option value="pink_hearts">Pink Hearts</option>
                        </optgroup>
                        <optgroup label="Film & Retro">
                            <option value="film_grain">Film Grain</option>
                            <option value="black_noise">Black Noise</option>
                            <option value="sepia">Sepia</option>
                            <option value="grayscale">Đen trắng</option>
                            <option value="chromatic">Chromatic</option>
                            <option value="negative">Negative</option>
                        </optgroup>
                        <optgroup label="Đặc biệt">
                            <option value="flash">Flash</option>
                            <option value="glitch">Glitch</option>
                            <option value="shockwave">Shockwave</option>
                            <option value="x_signal">X Signal</option>
                        </optgroup>
                    </select>
                </label>
            </div>
            <label style="font-size:.85em;display:flex;align-items:center;gap:6px">
                🔍 Zoom: <span id="zoom-val">15</span>%
                <input type="range" id="zoom-ratio" min="5" max="100" value="15" step="5" style="width:80px" oninput="document.getElementById('zoom-val').textContent=this.value">
            </label>
        </div>
        <div style="display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap;align-items:center">
            <label style="font-size:.85em;display:flex;align-items:center;gap:4px">
                <input type="checkbox" id="show-intro"> 📌 Intro:
                <select id="intro-bg-select" style="font-size:.8em;padding:2px 6px;border-radius:4px;border:1px solid #ddd">
                    <option value="">Mặc định</option>
                    ${vidImgs.filter(u => !u.match(/\.(mp4|mov|webm)/i)).map((u, i) => `<option value="${u}">Ảnh ${i + 1}</option>`).join('')}
                </select>
            </label>
            <label style="font-size:.85em;display:flex;align-items:center;gap:4px">
                <input type="checkbox" id="show-outro"> 📢 Outro:
                <select id="outro-bg-select" style="font-size:.8em;padding:2px 6px;border-radius:4px;border:1px solid #ddd">
                    <option value="">Mặc định</option>
                    ${vidImgs.filter(u => !u.match(/\.(mp4|mov|webm)/i)).map((u, i) => `<option value="${u}">Ảnh ${i + 1}</option>`).join('')}
                </select>
            </label>
        </div>
        ${vidImgs.length > 0 ? `
            <p style="font-size:.85em;color:#666;margin-bottom:8px">☑️ Chọn ảnh cho video & AI (tối đa 16):</p>` : '<p style="font-size:.85em;color:#999;margin-bottom:8px">Upload ảnh sản phẩm bên dưới → chọn ảnh để tạo AI</p>'}
            <div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px" id="vid-img-gallery">
                ${vidImgs.map((img, i) => {
        const isAI = img.includes('ai_images');
        return `<label style="position:relative;cursor:pointer">
                        <input type="checkbox" class="vid-img-check" value="${img}" checked
                               style="position:absolute;top:4px;left:4px;width:18px;height:18px;z-index:2"
                               onchange="limitVideoImages(this)">
                        ${isAI ? '<span style="position:absolute;top:4px;right:28px;background:#7c3aed;color:#fff;font-size:10px;padding:1px 5px;border-radius:4px;z-index:3">🤖 AI</span>' : ''}
                        <img src="${img}" style="height:100px;border-radius:6px;border:2px solid ${isAI ? '#7c3aed' : '#e94560'}">
                        ${isAI ? `<button type="button" data-img="${img}" onclick="regenAiImage(this,this.dataset.img)" style="position:absolute;bottom:4px;right:4px;background:#7c3aed;color:#fff;border:none;border-radius:4px;padding:2px 6px;cursor:pointer;font-size:11px;z-index:3">🔄</button>` : ''}
                        <button type="button" onclick="removeVidImg(this.parentElement)" style="position:absolute;top:-6px;right:-6px;background:#e94560;color:#fff;border:none;border-radius:50%;width:20px;height:20px;cursor:pointer;font-size:12px;line-height:20px;padding:0;z-index:3">✕</button>
                    </label>`;
    }).join('')}
            </div>
        <label style="font-weight:normal;font-size:.85em;color:#666">Hoặc upload thêm ảnh/video:
            <input type="file" id="video-media-upload" accept="image/*,video/*" multiple style="margin-left:8px" onchange="previewVideoUploads(this)">
        </label>
        <button onclick="generateAiImages()" class="btn" id="btn-ai-images" style="padding:6px 14px;font-size:.85em;background:#7c3aed;margin-top:8px">🖼️ Tạo ảnh AI</button>
        <span id="ai-img-status" style="font-size:.8em;margin-left:8px;color:#666"></span>
        <div id="video-upload-preview" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px"></div>
        <label style="font-weight:normal;font-size:.85em;color:#666;margin-top:6px;display:block">🏷️ Logo/Watermark:
            <input type="file" id="video-logo" accept="image/*" style="margin-left:8px">
            <input type="text" id="logo-text" placeholder="hoặc nhập text logo..." style="padding:4px 8px;border-radius:6px;border:1px solid #ddd;font-size:.85em;margin-left:4px;width:150px">
            <select id="logo-position" style="padding:4px 8px;border-radius:6px;border:1px solid #ddd;font-size:.85em;margin-left:4px">
                <option value="top-right">↗ Trên phải</option>
                <option value="top-left">↖ Trên trái</option>
                <option value="bottom-right">↘ Dưới phải</option>
                <option value="bottom-left">↙ Dưới trái</option>
            </select>
        </label>
        <div style="margin-top:12px">
            <label style="font-weight:600">🎵 Nhạc nền:</label>
            <div style="display:flex;gap:8px;align-items:center;margin-top:4px;flex-wrap:wrap">
                <select id="music-source" onchange="loadMusicList()" style="padding:8px 12px;border-radius:8px;border:1.5px solid #ddd">
                    <option value="freesound">🔊 Freesound</option>
                    <option value="jamendo">🎶 Jamendo</option>
                </select>
                <select id="music-category" onchange="loadMusicList(this.value)" style="padding:8px 12px;border-radius:8px;border:1.5px solid #ddd">
                    <option value="">Thể loại</option>
                </select>
                <input type="text" id="music-search" placeholder="Tìm nhạc..." style="padding:8px 12px;border-radius:8px;border:1.5px solid #ddd;width:120px" onkeydown="if(event.key==='Enter'){event.preventDefault();loadMusicList('',this.value)}">
                <select id="music-select" style="padding:8px 12px;border-radius:8px;border:1.5px solid #ddd;flex:1">
                    <option value="">Không nhạc nền</option>
                </select>
                <button type="button" onclick="previewMusic()" style="padding:6px 12px;border:1.5px solid #ddd;border-radius:8px;background:#fff;cursor:pointer">▶</button>
                <button type="button" onclick="stopMusic()" style="padding:6px 12px;border:1.5px solid #ddd;border-radius:8px;background:#fff;cursor:pointer">⏹</button>
                <button type="button" onclick="loadMusicList('','',true)" style="padding:6px 12px;border:1.5px solid #ddd;border-radius:8px;background:#fff;cursor:pointer" title="Đổi nhạc mới">🔄</button>
            </div>
            <div style="display:flex;gap:8px;align-items:center;margin-top:6px">
                <input type="text" id="custom-music-url" placeholder="Hoặc dán link nhạc MP3..." style="padding:6px 10px;border-radius:6px;border:1.5px solid #ddd;flex:1;font-size:.85em">
                <input type="file" id="custom-music-file" accept="audio/*,.mp3" style="font-size:.8em;max-width:180px">
            </div>
            <audio id="music-preview" style="display:none"></audio>
        </div>
        <div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap;align-items:center">
            <button class="btn" id="btn-preview" onclick="previewVideo()" style="background:#0f3460;padding:12px 24px">
                👁️ Xem trước
            </button>
            <button class="btn" id="btn-video" onclick="generateVideo()" style="background:#16213e;font-size:1.1em;padding:14px 36px">
                🎬 Tạo Video
            </button>
            <button class="btn" id="btn-batch" onclick="batchGenerate()" style="background:#6a0572;padding:12px 24px">
                📦 Tạo tất cả (TikTok + Reels)
            </button>
        </div>
        <div id="preview-result" style="margin-top:12px"></div>
        <div id="video-result" style="margin-top:12px"></div>
        <div style="margin-top:16px;padding-top:12px;border-top:1px solid #eee">
            </div>
        </div>
    </div>`;
    return html;
}
