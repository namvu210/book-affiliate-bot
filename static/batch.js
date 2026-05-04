/* Batch mode: product cards, step-by-step review flow, batch publish */

function batchLog(msg) {
    var el = document.getElementById('batch-log');
    if (el) { el.textContent += new Date().toLocaleTimeString() + ' | ' + msg + '\n'; el.scrollTop = el.scrollHeight; }
}

// === Import from Excel + Image Folder ===

async function importExcel(input) {
    var file = input.files[0];
    if (!file) return;
    var status = document.getElementById('import-status');
    status.textContent = '⏳ Đang đọc Excel...';
    try {
        var fd = new FormData();
        fd.append('file', file);
        var resp = await fetch('/import-excel', { method: 'POST', body: fd });
        if (!resp.ok) throw new Error((await resp.json()).detail || 'Lỗi');
        var data = await resp.json();
        var products = data.products || [];
        // Clear existing cards and create new ones
        document.getElementById('product-cards').innerHTML = '';
        _cardId = 0;
        products.forEach(function(p) { addProductCard(p.url, p.affiliate); });
        // Store titles for image matching
        window._importedProducts = products;
        status.textContent = '✅ ' + products.length + ' sản phẩm từ Excel. Chọn thư mục ảnh để tự động gán.';
    } catch(e) {
        status.textContent = '❌ ' + e.message;
    }
    input.value = '';
}

function importImageFolder(input) {
    var files = Array.from(input.files);
    if (!files.length) return;
    var status = document.getElementById('import-status');

    // Group files by subfolder
    var folders = {};
    files.forEach(function(f) {
        if (!f.type.startsWith('image/')) return;
        var parts = f.webkitRelativePath.split('/');
        if (parts.length < 2) return;
        var folder = parts[1] || parts[0]; // first subfolder name
        if (!folders[folder]) folders[folder] = [];
        folders[folder].push(f);
    });

    var folderNames = Object.keys(folders);
    if (!folderNames.length) {
        status.textContent = '❌ Không tìm thấy ảnh trong thư mục';
        input.value = '';
        return;
    }

    // Match folders to product cards by fuzzy title matching
    var cards = document.querySelectorAll('[id^="pcard-"]');
    var matched = 0;
    cards.forEach(function(card) {
        var url = card.querySelector('.pc-url')?.value || '';
        var title = (window._importedProducts || []).find(function(p) { return p.url === url; })?.title || '';
        if (!title) {
            // Extract from URL
            try { title = decodeURIComponent(url.split('shopee.vn/')[1] || '').split('-i.')[0].replace(/-/g, ' '); } catch(e) {}
        }
        if (!title) return;

        // Find best matching folder
        var bestFolder = null;
        var bestScore = 0;
        folderNames.forEach(function(fn) {
            var score = _fuzzyMatch(title.toLowerCase(), fn.toLowerCase());
            if (score > bestScore) { bestScore = score; bestFolder = fn; }
        });

        if (bestFolder && bestScore > 0.3) {
            addFilesToCard(card, folders[bestFolder]);
            matched++;
            // Remove matched folder so it's not reused
            var idx = folderNames.indexOf(bestFolder);
            if (idx >= 0) folderNames.splice(idx, 1);
        }
    });

    status.textContent = '✅ Gán ảnh cho ' + matched + '/' + cards.length + ' sản phẩm (' + Object.keys(folders).length + ' thư mục)';
    input.value = '';
}

function _fuzzyMatch(a, b) {
    // Simple word overlap score
    var wordsA = a.split(/\s+/).filter(function(w) { return w.length > 1; });
    var wordsB = b.split(/\s+/).filter(function(w) { return w.length > 1; });
    if (!wordsA.length || !wordsB.length) return 0;
    var matches = 0;
    wordsA.forEach(function(wa) {
        if (wordsB.some(function(wb) { return wb.includes(wa) || wa.includes(wb); })) matches++;
    });
    return matches / Math.max(wordsA.length, wordsB.length);
}

// === Product Cards ===
var _cardId = 0;
function addProductCard(url, affiliate) {
    var id = _cardId++;
    var container = document.getElementById('product-cards');
    var card = document.createElement('div');
    card.id = 'pcard-' + id;
    card.style.cssText = 'border:1.5px solid #ddd;border-radius:10px;padding:14px;margin-bottom:10px;background:#fff;position:relative';
    card.innerHTML =
        '<button onclick="this.parentElement.remove()" style="position:absolute;top:8px;right:10px;background:none;border:none;cursor:pointer;font-size:1.1em;color:#999" title="Xóa">✕</button>' +
        '<div style="display:flex;gap:8px;margin-bottom:8px">' +
            '<input type="url" class="pc-url" placeholder="https://shopee.vn/..." value="' + (url||'') + '" style="flex:2;padding:8px;border:1.5px solid #ddd;border-radius:6px;font-size:.85em">' +
            '<input type="url" class="pc-aff" placeholder="Link affiliate (tuỳ chọn)" value="' + (affiliate||'') + '" style="flex:1;padding:8px;border:1.5px solid #ddd;border-radius:6px;font-size:.85em">' +
        '</div>' +
        '<div class="pc-dropzone" style="border:2px dashed #ddd;border-radius:8px;padding:16px;text-align:center;color:#999;cursor:pointer;font-size:.85em;min-height:60px" ' +
            'ondragover="event.preventDefault();this.style.borderColor=\'#e94560\'" ondragleave="this.style.borderColor=\'#ddd\'">' +
            '📷 Kéo thả ảnh hoặc click để chọn (jpg, png)' +
            '<input type="file" multiple accept="image/*" style="display:none">' +
        '</div>' +
        '<div class="pc-thumbs" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px"></div>';
    var dropzone = card.querySelector('.pc-dropzone');
    var fileInput = card.querySelector('input[type="file"]');
    dropzone.addEventListener('click', function() { fileInput.click(); });
    dropzone.addEventListener('drop', function(e) { e.preventDefault(); this.style.borderColor='#ddd'; addFilesToCard(card, e.dataTransfer.files); });
    fileInput.addEventListener('change', function() { addFilesToCard(card, this.files); });
    container.appendChild(card);
    return id;
}

function addFilesToCard(card, files) {
    var thumbs = card.querySelector('.pc-thumbs');
    if (!card._files) card._files = [];
    for (var i = 0; i < files.length; i++) {
        if (!files[i].type.startsWith('image/')) continue;
        card._files.push(files[i]);
        var img = document.createElement('img');
        img.style.cssText = 'height:60px;border-radius:4px;object-fit:cover';
        img.src = URL.createObjectURL(files[i]);
        thumbs.appendChild(img);
    }
    card.querySelector('.pc-dropzone').style.borderColor = '#4ecca3';
}

function getProductCards() {
    var cards = document.querySelectorAll('[id^="pcard-"]');
    var products = [];
    cards.forEach(function(card) {
        var url = card.querySelector('.pc-url')?.value?.trim();
        if (!url || !url.startsWith('http')) return;
        products.push({ url: url, affiliate: card.querySelector('.pc-aff')?.value?.trim() || '', files: card._files || [] });
    });
    return products;
}

document.addEventListener('DOMContentLoaded', function() { addProductCard(); });

// === Batch State ===
var _batchState = { products: [], currentIdx: 0, results: [] };

async function startBatchReview() {
    var products = getProductCards();
    if (products.length === 0) { alert('Thêm ít nhất 1 sản phẩm!'); return; }
    var selectedPlatforms = [];
    if (document.getElementById('batch-plat-facebook').checked) selectedPlatforms.push('facebook');
    if (document.getElementById('batch-plat-tiktok').checked) selectedPlatforms.push('tiktok');
    if (document.getElementById('batch-plat-youtube').checked) selectedPlatforms.push('youtube');
    if (selectedPlatforms.length === 0) { alert('Chọn ít nhất 1 nền tảng!'); return; }
    var btn = document.getElementById('btn-batch-review');
    var progress = document.getElementById('batch-progress');
    var results = document.getElementById('batch-results');
    var batchVoice = getGlobalVoice();
    var wordCount = document.getElementById('batch-word-count')?.value || '150';
    var wordCountFb = document.getElementById('batch-word-count-fb')?.value || '200';
    var audience = document.getElementById('batch-audience').value;
    var customAudience = '';
    if (audience === 'custom') {
        customAudience = JSON.stringify({
            name: document.getElementById('batch-cp-name').value || 'Khách hàng',
            tone: document.getElementById('batch-cp-tone').value || 'thân thiện',
            focus: document.getElementById('batch-cp-focus').value || 'chất lượng sản phẩm',
        });
    }
    btn.disabled = true;
    results.innerHTML = '';
    _batchState = { products: products, currentIdx: 0, results: [], voice: batchVoice, wordCount: wordCount, wordCountFb: wordCountFb, audience: audience, customAudience: customAudience, platforms: selectedPlatforms };
    batchLog('Products: ' + products.length + ', Voice: ' + batchVoice.type + ', Audience: ' + audience);

    progress.innerHTML = '<div style="font-size:.9em">⏳ Bước 1: Phân tích đối tượng khách hàng...</div>';
    for (var i = 0; i < products.length; i++) {
        var p = products[i];
        try {
            var slug = decodeURIComponent(p.url.split('shopee.vn/')[1] || '').split('-i.')[0].replace(/-/g, ' ');
            if (audience === 'auto') {
                var fd = new FormData();
                fd.append('title', slug);
                var resp = await fetch('/suggest-personas', { method: 'POST', body: fd });
                var pdata = await resp.json();
                p.personas = (pdata.personas || []).slice(0, 2);
                batchLog('📦 ' + (i+1) + '. ' + slug.substring(0,40) + ' → ' + p.personas.map(x => x.name).join(', '));
            } else {
                p.personas = customAudience ? [JSON.parse(customAudience)] : [{name:'Khách hàng', tone:'thân thiện', focus:'chất lượng'}];
            }
            if (!p.personas.length) p.personas = [{name:'Khách hàng phổ thông', tone:'thân thiện', focus:'chất lượng sản phẩm'}];
            p.title = slug;
        } catch(e) {
            batchLog('❌ Persona failed for ' + (i+1) + ': ' + e.message);
            p.personas = [{name:'Khách hàng phổ thông', tone:'thân thiện', focus:'chất lượng sản phẩm'}];
            p.title = p.url.substring(0, 50);
        }
    }

    var html = '<h3 style="margin-bottom:12px">📋 Bước 1: Xác nhận đối tượng khách hàng</h3>';
    products.forEach(function(p, i) {
        html += '<div class="result-card" style="padding:12px;margin-bottom:8px">';
        html += '<strong>' + (i+1) + '. ' + (p.title||'').substring(0,60) + '</strong>';
        html += '<div style="margin-top:6px">';
        p.personas.forEach(function(per) {
            html += '<span style="display:inline-block;background:#e8f0fe;padding:4px 10px;border-radius:12px;font-size:.85em;margin:2px 4px">🎯 ' + per.name + '</span>';
        });
        html += '</div></div>';
    });
    html += '<div style="margin-top:12px"><button class="btn" onclick="batchStep2()" style="padding:10px 24px">✅ Tiếp tục → Tạo Review</button> ';
    html += '<button onclick="document.getElementById(\'btn-batch-review\').disabled=false;document.getElementById(\'batch-results\').innerHTML=\'\'" style="padding:10px 16px;background:#eee;border:1px solid #ddd;border-radius:8px;cursor:pointer">❌ Hủy</button></div>';
    results.innerHTML = html;
    progress.innerHTML = '';
}

async function batchStep2() {
    var products = _batchState.products;
    var progress = document.getElementById('batch-progress');
    var results = document.getElementById('batch-results');
    results.innerHTML = '<h3 style="margin-bottom:12px">⏳ Bước 2: Tạo Review...</h3>';
    var allReviews = [];

    for (var i = 0; i < products.length; i++) {
        var p = products[i];
        progress.innerHTML = '<div style="font-size:.9em">⏳ Sản phẩm ' + (i+1) + '/' + products.length + '...</div>' +
            '<div style="background:#eee;border-radius:4px;height:8px;margin-top:6px"><div style="background:#e94560;height:8px;border-radius:4px;width:' + ((i+1)/products.length*100) + '%"></div></div>';
        for (var j = 0; j < p.personas.length; j++) {
            var persona = p.personas[j];
            batchLog('Generating: ' + (p.title||'').substring(0,30) + ' × ' + persona.name);
            try {
                var fd = new FormData();
                fd.append('url', p.url);
                if (p.affiliate) fd.append('affiliate_url', p.affiliate);
                fd.append('audience', 'custom');
                fd.append('custom_audience', JSON.stringify(persona));
                fd.append('word_count_tk', _batchState.wordCount);
                fd.append('word_count_fb', _batchState.wordCountFb);
                fd.append('platforms', _batchState.platforms.join(','));
                for (var k = 0; k < p.files.length; k++) fd.append('media', p.files[k]);
                var resp = await fetch('/from-url', { method: 'POST', body: fd });
                if (!resp.ok) throw new Error('Lỗi server');
                var data = await resp.json();
                allReviews.push({ product: p, persona: persona, data: data, idx: i });
                batchLog('✅ ' + persona.name + ' → TK:' + (data.tiktok?.social_post||'').length + ' FB:' + (data.facebook?.social_post||'').length);
            } catch(e) {
                batchLog('❌ ' + persona.name + ': ' + e.message);
                allReviews.push({ product: p, persona: persona, data: null, error: e.message, idx: i });
            }
        }
    }
    _batchState.reviews = allReviews;

    var html = '<h3 style="margin-bottom:12px">📋 Bước 2: Xem lại Review</h3>';
    var lastIdx = -1;
    allReviews.forEach(function(r) {
        if (r.idx !== lastIdx) {
            if (lastIdx >= 0) html += '</div>';
            html += '<div class="result-card" style="padding:14px;margin-bottom:10px">';
            html += '<h4 style="margin-bottom:8px">📦 ' + (r.idx+1) + '. ' + (r.product.title||'').substring(0,60) + '</h4>';
            lastIdx = r.idx;
        }
        html += '<div style="padding:8px;margin:6px 0;background:#f8f9fa;border-radius:6px">';
        html += '<strong>🎯 ' + r.persona.name + '</strong>';
        if (r.error) {
            html += ' <span style="color:red">❌ ' + r.error + '</span>';
        } else {
            var tk = r.data?.tiktok?.social_post || '';
            var fb = r.data?.facebook?.social_post || '';
            var tkAudio = r.data?.tiktok?.audio_url || '';
            var fbAudio = r.data?.facebook?.audio_url || '';
            if (tkAudio) html += '<div style="margin-top:4px"><span style="font-size:.8em;color:#666">🎵 TikTok:</span> <audio controls style="height:24px;vertical-align:middle"><source src="' + tkAudio + '"></audio></div>';
            if (fbAudio) html += '<div><span style="font-size:.8em;color:#666">📘 Facebook:</span> <audio controls style="height:24px;vertical-align:middle"><source src="' + fbAudio + '"></audio></div>';
            html += '<div style="margin-top:6px;font-size:.85em">';
            html += '<details><summary>🎵 TikTok (' + tk.length + ' ký tự)</summary><pre style="white-space:pre-wrap;background:#fff;padding:8px;border-radius:4px;margin-top:4px;font-family:inherit;font-size:.9em">' + tk.replace(/</g,'&lt;') + '</pre></details>';
            html += '<details><summary>📘 Facebook (' + fb.length + ' ký tự)</summary><pre style="white-space:pre-wrap;background:#fff;padding:8px;border-radius:4px;margin-top:4px;font-family:inherit;font-size:.9em">' + fb.replace(/</g,'&lt;') + '</pre></details>';
            html += '</div>';
        }
        html += '</div>';
    });
    if (lastIdx >= 0) html += '</div>';
    html += '<div style="margin-top:12px"><button class="btn" onclick="batchStep3()" style="padding:10px 24px">✅ Tiếp tục → Tạo Video</button> ';
    html += '<button onclick="document.getElementById(\'btn-batch-review\').disabled=false;document.getElementById(\'batch-results\').innerHTML=\'\'" style="padding:10px 16px;background:#eee;border:1px solid #ddd;border-radius:8px;cursor:pointer">❌ Hủy</button></div>';
    results.innerHTML = html;
    progress.innerHTML = '';
}

async function batchStep3() {
    var reviews = _batchState.reviews.filter(r => r.data);
    var progress = document.getElementById('batch-progress');
    var results = document.getElementById('batch-results');
    results.innerHTML = '<h3 style="margin-bottom:12px">⏳ Bước 3: Tạo Video...</h3>';

    // Build all video tasks
    var tasks = [];
    for (var i = 0; i < reviews.length; i++) {
        var r = reviews[i];
        for (var j = 0; j < _batchState.platforms.length; j++) {
            tasks.push({ review: r, platform: _batchState.platforms[j] });
        }
    }

    // Run with concurrency limit of 2
    var videoResults = [];
    var completed = 0;
    async function runTask(task) {
        try {
            var fd = new FormData();
            fd.append('review_json', JSON.stringify(task.review.data));
            fd.append('platform', task.platform);
            fd.append('aspect_ratio', '9:16');
            fd.append('voice_speed', _batchState.voice.speed);
            var resp = await fetch('/generate-video', { method: 'POST', body: fd });
            if (!resp.ok) {
                var errData = await resp.json().catch(function() { return {}; });
                throw new Error(errData.detail || 'HTTP ' + resp.status);
            }
            var vdata = await resp.json();
            batchLog('🎬 ' + task.review.persona.name + ' → ' + task.platform + ': ' + vdata.video_url);
            return { review: task.review, platform: task.platform, video_url: vdata.video_url, srt_url: vdata.srt_url };
        } catch(e) {
            batchLog('❌ Video ' + task.platform + ': ' + e.message);
            return { review: task.review, platform: task.platform, error: e.message };
        } finally {
            completed++;
            progress.innerHTML = '<div style="font-size:.9em">⏳ Video ' + completed + '/' + tasks.length + '...</div>' +
                '<div style="background:#eee;border-radius:4px;height:8px;margin-top:6px"><div style="background:#e94560;height:8px;border-radius:4px;width:' + (completed/tasks.length*100) + '%"></div></div>';
        }
    }

    // Process in batches of 2
    for (var start = 0; start < tasks.length; start += 2) {
        var batch = tasks.slice(start, start + 2).map(runTask);
        var batchResults = await Promise.all(batch);
        videoResults = videoResults.concat(batchResults);
    }

    var html = '<h3 style="margin-bottom:12px">📋 Bước 3: Video & Đăng bài</h3>';
    window._batchReviews = videoResults.map(function(v) { return v.review.data; });
    window._batchVideos = videoResults.map(function(v) { return { url: v.video_url, platform: v.platform }; });

    var lastReviewIdx = -1;
    videoResults.forEach(function(v, vi) {
        var reviewIdx = Math.floor(vi / _batchState.platforms.length);
        if (reviewIdx !== lastReviewIdx) {
            if (lastReviewIdx >= 0) html += '</div>';
            html += '<div class="result-card" style="padding:14px;margin-bottom:10px">';
            html += '<h4>📦 ' + (v.review.idx+1) + '. ' + (v.review.product.title||'').substring(0,50) + '</h4>';
            html += '<div style="font-size:.85em;color:#666;margin-bottom:8px">🎯 ' + v.review.persona.name + '</div>';
            lastReviewIdx = reviewIdx;
        }
        var label = v.platform === 'tiktok' ? '🎵 TikTok' : (v.platform === 'youtube' ? '▶️ YouTube' : '📘 Reels');
        if (v.error) {
            html += '<div style="margin:4px 0;font-size:.85em;color:red">❌ ' + label + ': ' + v.error + '</div>';
        } else {
            html += '<div style="display:inline-block;margin:6px 8px 6px 0;vertical-align:top">';
            html += '<video controls style="max-width:180px;border-radius:8px"><source src="' + v.video_url + '" type="video/mp4"></video>';
            html += '<br><a href="' + v.video_url + '" download class="btn" style="font-size:.75em;padding:4px 10px;margin-top:4px;display:inline-block">⬇️ ' + label + '</a>';
            html += ' <button class="btn" onclick="batchPublish(' + vi + ',this)" style="font-size:.75em;padding:4px 10px;margin-top:4px;background:' + (v.platform==='tiktok'?'#000':v.platform==='youtube'?'#c00':'#1877f2') + '">📤 Đăng</button>';
            html += '<span class="bp-status" style="font-size:.8em;display:block;margin-top:2px"></span>';
            html += '</div>';
        }
    });
    if (lastReviewIdx >= 0) html += '</div>';
    results.innerHTML = html;
    progress.innerHTML = '<div style="font-size:.9em;color:green">✅ Hoàn thành! Xem video và đăng bài bên dưới.</div>';
    document.getElementById('btn-batch-review').disabled = false;
}

async function batchPublish(vi, btn) {
    var reviewData = window._batchReviews[vi];
    var videoInfo = window._batchVideos[vi];
    if (!reviewData || !videoInfo) { alert('Dữ liệu không tìm thấy'); return; }
    var platform = videoInfo.platform;
    var videoUrl = videoInfo.url;
    var status = btn.parentElement.querySelector('.bp-status');
    var label = {tiktok:'TikTok',facebook:'Facebook Reels',youtube:'YouTube Shorts'}[platform] || platform;
    btn.disabled = true;
    if (status) status.textContent = '⏳ Đang đăng ' + label + '...';
    try {
        var fd = new FormData();
        fd.append('review_json', JSON.stringify(reviewData));
        fd.append('video_url', videoUrl);
        fd.append('platforms', platform);
        var resp = await fetch('/publish', {method: 'POST', body: fd});
        var data = await resp.json();
        var r = (data.results || [])[0];
        if (r && status) {
            var msg = (r.success ? '✅' : '❌') + ' ' + r.message;
            if (r.post_id && r.success) {
                var urls = {facebook:'https://www.facebook.com/'+r.post_id, youtube:'https://youtu.be/'+r.post_id};
                if (urls[r.platform]) msg += ' <a href="'+urls[r.platform]+'" target="_blank">Xem →</a>';
            }
            status.innerHTML = msg;
        }
    } catch(e) {
        if (status) status.textContent = '❌ ' + e.message;
    }
    btn.disabled = false;
}
