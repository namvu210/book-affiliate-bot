/* Screenplay generation and editing — shot-level cinematic breakdowns */

var storyStyles = {};
var cinematicStyles = {};

/* --- Product image management --- */

function initMovieImageDropzone() {
    var dropzone = document.getElementById('movie-img-dropzone');
    var fileInput = document.getElementById('movie-img-input');
    if (!dropzone || !fileInput) return;
    dropzone.addEventListener('click', function () { fileInput.click(); });
    dropzone.addEventListener('drop', function (e) {
        e.preventDefault();
        this.style.borderColor = '#ddd';
        movieAddImageFiles(e.dataTransfer.files);
    });
    fileInput.addEventListener('change', function () { movieAddImageFiles(this.files); this.value = ''; });
}

function movieImportFolder(input) {
    var files = Array.from(input.files).filter(function (f) { return f.type.startsWith('image/'); });
    if (files.length) movieAddImageFiles(files);
    input.value = '';
}

function movieAddImageFiles(files) {
    if (!movieState.imageFiles) movieState.imageFiles = [];
    if (!movieState.selectedImageIndexes) movieState.selectedImageIndexes = new Set();

    for (var i = 0; i < files.length; i++) {
        if (!files[i].type.startsWith('image/')) continue;
        movieState.imageFiles.push(files[i]);
    }
    movieRenderImageThumbs();
}

function movieRenderImageThumbs() {
    var container = document.getElementById('movie-img-thumbs');
    var countEl = document.getElementById('movie-img-count');
    var files = movieState.imageFiles || [];
    var selected = movieState.selectedImageIndexes || new Set();

    countEl.textContent = files.length + ' ảnh' + (selected.size ? ' (' + selected.size + ' cho AI)' : '');

    container.innerHTML = '';
    files.forEach(function (file, idx) {
        var wrap = document.createElement('div');
        wrap.style.cssText = 'position:relative;display:inline-block;cursor:pointer';

        var img = document.createElement('img');
        img.style.cssText = 'height:100px;border-radius:6px;object-fit:cover;border:2.5px solid ' + (selected.has(idx) ? '#7c3aed' : 'transparent');
        img.src = URL.createObjectURL(file);

        if (selected.has(idx)) {
            var badge = document.createElement('span');
            badge.className = 'ai-badge';
            badge.style.cssText = 'position:absolute;top:-4px;left:-4px;background:#7c3aed;color:#fff;font-size:9px;padding:1px 5px;border-radius:4px;z-index:3';
            badge.textContent = '🤖 AI';
            wrap.appendChild(badge);
        }

        wrap.addEventListener('click', (function (i, im) {
            return function (e) {
                if (e.target.tagName === 'BUTTON') return;
                if (selected.has(i)) {
                    selected.delete(i);
                } else if (selected.size < 3) {
                    selected.add(i);
                }
                movieState.selectedImageIndexes = selected;
                movieRenderImageThumbs();
            };
        })(idx, img));

        var btn = document.createElement('button');
        btn.textContent = '✕';
        btn.style.cssText = 'position:absolute;top:-4px;right:-4px;background:#e94560;color:#fff;border:none;border-radius:50%;width:18px;height:18px;font-size:10px;cursor:pointer;line-height:18px;padding:0;z-index:4';
        btn.onclick = (function (i) {
            return function (e) {
                e.stopPropagation();
                movieState.imageFiles.splice(i, 1);
                // Rebuild selected indexes (shift down)
                var newSelected = new Set();
                selected.forEach(function (si) {
                    if (si < i) newSelected.add(si);
                    else if (si > i) newSelected.add(si - 1);
                });
                movieState.selectedImageIndexes = newSelected;
                selected = newSelected;
                movieRenderImageThumbs();
            };
        })(idx);

        wrap.appendChild(img);
        wrap.appendChild(btn);
        container.appendChild(wrap);
    });

    document.getElementById('movie-img-dropzone').style.borderColor = files.length ? '#4ecca3' : '#ddd';
}

function movieApplyFetchedImages(imageUrls) {
    // When fetching from Shopee, show remote images as selectable thumbnails
    if (!movieState.fetchedImageUrls) movieState.fetchedImageUrls = [];
    movieState.fetchedImageUrls = imageUrls || [];
    movieState.selectedFetchedIndexes = new Set();
    // Auto-select first 3
    for (var i = 0; i < Math.min(3, imageUrls.length); i++) {
        movieState.selectedFetchedIndexes.add(i);
    }
    movieRenderFetchedThumbs();
}

function movieRenderFetchedThumbs() {
    var container = document.getElementById('movie-img-thumbs');
    var countEl = document.getElementById('movie-img-count');
    var urls = movieState.fetchedImageUrls || [];
    var selected = movieState.selectedFetchedIndexes || new Set();

    countEl.textContent = urls.length + ' ảnh' + (selected.size ? ' (' + selected.size + ' cho AI)' : '');

    container.innerHTML = '';
    urls.forEach(function (url, idx) {
        var wrap = document.createElement('div');
        wrap.style.cssText = 'position:relative;display:inline-block;cursor:pointer';

        var img = document.createElement('img');
        img.style.cssText = 'height:100px;border-radius:6px;object-fit:cover;border:2.5px solid ' + (selected.has(idx) ? '#7c3aed' : 'transparent');
        img.src = url;

        if (selected.has(idx)) {
            var badge = document.createElement('span');
            badge.className = 'ai-badge';
            badge.style.cssText = 'position:absolute;top:-4px;left:-4px;background:#7c3aed;color:#fff;font-size:9px;padding:1px 5px;border-radius:4px;z-index:3';
            badge.textContent = '🤖 AI';
            wrap.appendChild(badge);
        }

        wrap.addEventListener('click', (function (i) {
            return function (e) {
                if (e.target.tagName === 'BUTTON') return;
                if (selected.has(i)) {
                    selected.delete(i);
                } else if (selected.size < 3) {
                    selected.add(i);
                }
                movieState.selectedFetchedIndexes = selected;
                movieRenderFetchedThumbs();
            };
        })(idx));

        wrap.appendChild(img);
        container.appendChild(wrap);
    });
}

function movieGetSelectedImages() {
    // Returns list of image URLs/paths to send to project
    // Priority: fetched images (from Shopee), then uploaded files (need upload first)
    var urls = movieState.fetchedImageUrls || [];
    var selectedFetched = movieState.selectedFetchedIndexes || new Set();
    if (urls.length && selectedFetched.size) {
        var result = [];
        selectedFetched.forEach(function (i) { if (urls[i]) result.push(urls[i]); });
        return result;
    }
    // For uploaded files, we need to upload them first during project creation
    return [];
}

async function loadStoryStyles() {
    try {
        var resp = await fetch('/api/movie/story-styles');
        var data = await resp.json();
        storyStyles = data.styles || {};
        var select = document.getElementById('story-style-select');
        if (!select) return;
        select.innerHTML = '<option value="auto">🎲 Ngẫu nhiên</option>';
        Object.keys(storyStyles).forEach(function (key) {
            select.innerHTML += '<option value="' + key + '">' + key + ' — ' + storyStyles[key].substring(0, 40) + '</option>';
        });
    } catch (e) { }
    try {
        var resp2 = await fetch('/api/movie/cinematic-styles');
        var data2 = await resp2.json();
        cinematicStyles = data2.styles || {};
        var select2 = document.getElementById('cinematic-style-select');
        if (!select2) return;
        select2.innerHTML = '<option value="auto">🎲 Ngẫu nhiên</option>';
        Object.keys(cinematicStyles).forEach(function (key) {
            select2.innerHTML += '<option value="' + key + '">' + key.replace(/_/g, ' ') + '</option>';
        });
    } catch (e) { }
}

/* --- Product fetching --- */

function autoFetchMovieProduct() {
    var url = document.getElementById('movie-product-url').value.trim();
    if (url && url.includes('shopee')) fetchMovieProduct();
}

async function fetchMovieProduct() {
    var url = document.getElementById('movie-product-url').value.trim();
    if (!url) { alert('Nhập link Shopee'); return; }

    var status = document.getElementById('movie-fetch-status');
    status.textContent = '⏳ Đang lấy thông tin sản phẩm...';

    try {
        var fd = new FormData();
        fd.append('url', url);
        var resp = await fetch('/fetch-images', { method: 'POST', body: fd });
        if (!resp.ok) { var err = await resp.json(); throw new Error(err.detail || 'Lỗi'); }
        var data = await resp.json();
        applyMovieProductData(data, url);
        status.textContent = '✅ Đã lấy thông tin!';
        setTimeout(function () { status.textContent = ''; }, 3000);
    } catch (e) {
        status.textContent = '❌ ' + e.message;
    }
}

async function importMovieFromExtension() {
    var status = document.getElementById('movie-fetch-status');
    status.textContent = '⏳ Đang lấy từ Extension...';
    try {
        var resp = await fetch('/poll-shopee-data');
        var d = await resp.json();
        if (d.ready) {
            applyMovieProductData(d.data);
            status.textContent = '✅ Đã nhận từ Extension!';
            setTimeout(function () { status.textContent = ''; }, 3000);
            return;
        }
        resp = await fetch('/poll-shopee-queue');
        d = await resp.json();
        if (d.products && d.products.length) {
            var latest = d.products[d.products.length - 1];
            applyMovieProductData(latest);
            status.textContent = '✅ Đã nhận từ Extension!';
            setTimeout(function () { status.textContent = ''; }, 3000);
        } else {
            status.textContent = '❌ Chưa có dữ liệu. Scrape sản phẩm từ Extension trước.';
            setTimeout(function () { status.textContent = ''; }, 4000);
        }
    } catch (e) {
        status.textContent = '❌ ' + e.message;
    }
}

function applyMovieProductData(data, url) {
    // Fill form fields
    if (data.title) document.getElementById('movie-product-title').value = data.title;
    if (url) document.getElementById('movie-product-url').value = url;
    else if (data.url) document.getElementById('movie-product-url').value = data.url;
    if (data.description) document.getElementById('movie-product-desc').value = data.description;

    // Store product data
    movieState.productData = data;

    // Show product card
    var card = document.getElementById('movie-product-card');
    card.style.display = 'block';
    document.getElementById('movie-product-card-title').textContent = data.title || '';
    var meta = '';
    if (data.price) meta += '💰 ' + data.price + ' ';
    if (data.rating) meta += '⭐ ' + data.rating + '/5 ';
    if (data.rating_count) meta += '(' + data.rating_count.toLocaleString() + ' đánh giá) ';
    if (data.sold_count) meta += '🛒 ' + data.sold_count.toLocaleString() + ' đã bán';
    document.getElementById('movie-product-card-meta').textContent = meta;

    // Thumbnail
    var thumbEl = document.getElementById('movie-product-thumb');
    var imgs = data.product_images || [];
    if (imgs.length) {
        thumbEl.innerHTML = '<img src="' + imgs[0] + '" style="width:100%;height:100%;object-fit:cover">';
    }

    // Show fetched images as selectable thumbnails
    if (imgs.length) {
        movieApplyFetchedImages(imgs);
    }
}

/* --- Project creation --- */

async function createProject() {
    var title = document.getElementById('movie-product-title').value.trim();
    var url = document.getElementById('movie-product-url').value.trim();
    var desc = document.getElementById('movie-product-desc').value.trim();
    var affiliateLink = document.getElementById('movie-affiliate-link').value.trim();

    if (!title) { alert('Nhập tên sản phẩm'); return; }
    if (movieState.selectedKols.length === 0) { alert('Quay lại chọn KOL trước'); return; }

    var btn = document.getElementById('btn-create-project');
    btn.disabled = true;
    btn.textContent = '⏳ Đang tạo...';

    try {
        // Get selected product images (fetched URLs or upload local files)
        var productImages = movieGetSelectedImages();

        // If user uploaded local files and no fetched images selected, upload them
        if (!productImages.length && movieState.imageFiles && movieState.imageFiles.length) {
            var selected = movieState.selectedImageIndexes || new Set();
            var filesToUpload = [];
            if (selected.size) {
                selected.forEach(function (i) { if (movieState.imageFiles[i]) filesToUpload.push(movieState.imageFiles[i]); });
            } else {
                filesToUpload = movieState.imageFiles.slice(0, 3);
            }
            if (filesToUpload.length) {
                var fd = new FormData();
                filesToUpload.forEach(function (f) { fd.append('images', f); });
                var upResp = await fetch('/api/movie/upload-product-images', { method: 'POST', body: fd });
                if (upResp.ok) {
                    var upData = await upResp.json();
                    productImages = upData.image_urls || [];
                }
            }
        }

        var resp = await fetch('/api/movie/project/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                product_title: title,
                product_url: url,
                product_images: productImages,
                kol_ids: movieState.selectedKols,
                affiliate_link: affiliateLink,
            })
        });
        if (!resp.ok) { var err = await resp.json(); throw new Error(err.detail); }
        var project = await resp.json();
        movieState.project = project;
        movieState.project._product_description = desc;
        document.getElementById('project-status').textContent = '✅ Project: ' + project.id;
        nextStep();
    } catch (e) {
        alert('Lỗi: ' + e.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Tạo Project & Tiếp tục →';
    }
}

async function generateScreenplay() {
    if (!movieState.project) { alert('Tạo project trước'); return; }

    var style = document.getElementById('story-style-select').value;
    var cinema = document.getElementById('cinematic-style-select').value;
    var btn = document.getElementById('btn-gen-screenplay');
    btn.disabled = true;
    btn.textContent = '⏳ Đang tạo kịch bản...';
    document.getElementById('screenplay-result').innerHTML = '<p style="color:#666">Đang gọi Gemini... (có thể mất 10-20s)</p>';

    try {
        var resp = await fetch('/api/movie/project/' + movieState.project.id + '/screenplay', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                story_style: style,
                cinematic_style: cinema,
                product_description: movieState.project._product_description || '',
            })
        });
        if (!resp.ok) { var err = await resp.json(); throw new Error(err.detail); }
        var screenplay = await resp.json();
        movieState.project.screenplay = screenplay;
        renderScreenplay(screenplay);
    } catch (e) {
        document.getElementById('screenplay-result').innerHTML = '<p style="color:red">❌ ' + e.message + '</p>';
    } finally {
        btn.disabled = false;
        btn.textContent = '🎬 Tạo kịch bản';
    }
}

function renderScreenplay(sp) {
    var html = '';

    // Header
    html += '<div style="background:#f0fdf4;border:1px solid #10b981;border-radius:8px;padding:16px;margin-bottom:16px">';
    html += '<h3 style="margin:0 0 6px">🎬 ' + (sp.title || '') + '</h3>';
    html += '<p style="font-size:.85em;color:#555;margin:0">' + (sp.story_hook || '') + '</p>';
    if (sp.product_placement) html += '<p style="font-size:.8em;color:#888;margin:4px 0 0">📦 ' + sp.product_placement + '</p>';
    if (sp.cinematic_style) html += '<span style="font-size:.75em;background:#e8f4f8;color:#0f3460;padding:2px 8px;border-radius:10px;margin-top:6px;display:inline-block">🎥 ' + sp.cinematic_style.replace(/_/g, ' ') + '</span>';
    if (sp.mood) html += ' <span style="font-size:.75em;background:#e0e7ff;color:#3730a3;padding:2px 8px;border-radius:10px;margin-top:6px;display:inline-block">' + sp.mood + '</span>';
    html += '</div>';

    // Key frame description
    html += '<div style="margin-bottom:16px">';
    html += '<label style="font-size:.8em;font-weight:600;color:#555">🖼️ Key Frame (frame đầu tiên của video):</label>';
    html += '<textarea id="sp-keyframe" rows="3" style="width:100%;font-size:.85em;padding:8px;border:1px solid #ddd;border-radius:6px;margin-top:4px">' + (sp.key_frame_description || '') + '</textarea>';
    html += '</div>';

    // Segments timeline bar
    var segments = sp.segments || [];
    var totalDur = segments.reduce(function(s, seg) { return s + (seg.duration || 0); }, 0);

    html += '<div style="margin-bottom:8px;display:flex;align-items:center;gap:8px">';
    html += '<label style="font-size:.8em;font-weight:600;color:#555;margin:0">🎞️ Segments (' + totalDur + 's):</label>';
    if (totalDur !== 16) html += '<span style="font-size:.75em;color:#ef4444;font-weight:600">⚠️ Tổng phải = 16s</span>';
    html += '</div>';

    // Timeline bar
    html += '<div style="display:flex;gap:2px;margin-bottom:12px;border-radius:6px;overflow:hidden;height:24px">';
    var colors = {"story": "#0ea5e9", "closeup": "#8b5cf6"};
    segments.forEach(function(seg, i) {
        var color = colors[seg.type] || '#999';
        var label = seg.type === 'closeup' ? '📸' : '📖';
        html += '<div style="flex:' + seg.duration + ';background:' + color + ';display:flex;align-items:center;justify-content:center;color:#fff;font-size:.7em;font-weight:600">';
        html += label + ' ' + seg.duration + 's';
        html += '</div>';
    });
    html += '</div>';

    // Segment editors
    segments.forEach(function(seg, i) {
        var isStory = seg.type === 'story';
        var borderColor = isStory ? '#0ea5e9' : '#8b5cf6';
        var typeLabel = isStory ? '📖 Story' : '📸 Close-up';

        html += '<div style="border:1.5px solid ' + borderColor + ';border-radius:8px;margin-bottom:10px;overflow:hidden">';

        // Header
        html += '<div style="padding:6px 12px;background:' + borderColor + '15;display:flex;align-items:center;gap:8px">';
        html += '<strong style="font-size:.82em;color:' + borderColor + '">' + typeLabel + '</strong>';
        html += '<select id="sp-seg-' + i + '-dur" style="padding:2px 6px;border:1px solid #ddd;border-radius:4px;font-size:.78em">';
        [4, 6, 8].forEach(function(d) {
            html += '<option value="' + d + '"' + (seg.duration === d ? ' selected' : '') + '>' + d + 's</option>';
        });
        html += '</select>';
        html += '<select id="sp-seg-' + i + '-type" style="padding:2px 6px;border:1px solid #ddd;border-radius:4px;font-size:.78em">';
        html += '<option value="story"' + (seg.type === 'story' ? ' selected' : '') + '>Story</option>';
        html += '<option value="closeup"' + (seg.type === 'closeup' ? ' selected' : '') + '>Close-up</option>';
        html += '</select>';

        // Connection indicator
        if (i > 0 && isStory && segments[i-1].type === 'story') {
            html += '<span style="font-size:.7em;color:#10b981;margin-left:auto">🔗 extends from seg ' + i + '</span>';
        } else if (i > 0 && isStory) {
            html += '<span style="font-size:.7em;color:#f59e0b;margin-left:auto">⚡ new shot</span>';
        }
        html += '</div>';

        // Prompt
        html += '<div style="padding:8px 12px">';
        html += '<textarea id="sp-seg-' + i + '-prompt" rows="2" style="width:100%;font-size:.82em;padding:6px 8px;border:1px solid #ddd;border-radius:5px" placeholder="English prompt for Veo...">' + (seg.prompt || '') + '</textarea>';
        if (isStory && seg.dialogue) {
            html += '<input id="sp-seg-' + i + '-dialogue" type="text" value="' + (seg.dialogue || '').replace(/"/g, '&quot;') + '" style="width:100%;font-size:.8em;padding:4px 8px;border:1px solid #ddd;border-radius:4px;margin-top:4px" placeholder="💬 Dialogue (tùy chọn)">';
        } else if (isStory) {
            html += '<input id="sp-seg-' + i + '-dialogue" type="text" value="" style="width:100%;font-size:.8em;padding:4px 8px;border:1px solid #ddd;border-radius:4px;margin-top:4px" placeholder="💬 Dialogue (tùy chọn)">';
        }
        html += '</div>';
        html += '</div>';
    });

    // Dialogue (global)
    html += '<div style="margin-top:8px;margin-bottom:16px">';
    html += '<label style="font-size:.8em;font-weight:600;color:#555">💬 Dialogue (global):</label>';
    html += '<input type="text" id="sp-dialogue" value="' + (sp.dialogue || '').replace(/"/g, '&quot;') + '" style="width:100%;font-size:.85em;padding:6px 8px;border:1px solid #ddd;border-radius:6px;margin-top:4px" placeholder="(tùy chọn — ghi đè per-segment dialogue)">';
    html += '</div>';

    // Actions
    html += '<div style="display:flex;gap:8px;flex-wrap:wrap">';
    html += '<button onclick="saveScreenplay()" class="btn" style="padding:8px 16px;font-size:.85em">💾 Lưu chỉnh sửa</button>';
    html += '<button onclick="generateScreenplay()" class="btn btn-secondary" style="padding:8px 16px;font-size:.85em">🔄 Tạo lại</button>';
    html += '<span id="screenplay-save-status" style="font-size:.85em;color:#10b981;line-height:36px"></span>';
    html += '</div>';

    document.getElementById('screenplay-result').innerHTML = html;
}

async function saveScreenplay() {
    if (!movieState.project || !movieState.project.screenplay) return;
    var sp = movieState.project.screenplay;

    sp.key_frame_description = document.getElementById('sp-keyframe')?.value || '';
    var dlg = document.getElementById('sp-dialogue')?.value || '';
    sp.dialogue = dlg || null;

    // Save segments
    var segments = sp.segments || [];
    segments.forEach(function(seg, i) {
        seg.duration = parseInt(document.getElementById('sp-seg-' + i + '-dur')?.value || seg.duration) || 8;
        seg.type = document.getElementById('sp-seg-' + i + '-type')?.value || seg.type;
        seg.prompt = document.getElementById('sp-seg-' + i + '-prompt')?.value || '';
        var dlgEl = document.getElementById('sp-seg-' + i + '-dialogue');
        if (dlgEl) seg.dialogue = dlgEl.value || null;
    });
    sp.segments = segments;

    try {
        var resp = await fetch('/api/movie/project/' + movieState.project.id + '/screenplay', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(sp)
        });
        if (resp.ok) {
            movieState.project.screenplay = sp;
            var el = document.getElementById('screenplay-save-status');
            if (el) { el.textContent = '✅ Đã lưu'; setTimeout(function () { el.textContent = ''; }, 2000); }
            renderScreenplay(sp);
        }
    } catch (e) {
        alert('Lỗi: ' + e.message);
    }
}
