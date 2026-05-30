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

    // Group image files by product folder name
    // Shopee Save structure: shopeesave_<date>/<product_name>/main_images/*.jpg
    var folders = {};
    files.forEach(function(f) {
        if (!f.type.startsWith('image/')) return;
        var parts = f.webkitRelativePath.split('/');
        // Find product name: skip root folder (shopeesave_*), product name is next
        var productName = null;
        for (var i = 0; i < parts.length - 1; i++) {
            if (parts[i].match(/^shopeesave/i)) continue;
            if (parts[i].match(/^(main_images|variant_images|product_video)$/i)) break;
            productName = parts[i];
            break;
        }
        if (!productName) return;
        // Prefer main_images, also accept variant_images, skip product_video
        var subdir = parts.find(function(p) { return p.match(/^(main_images|variant_images)$/i); });
        if (!subdir && parts.length >= 3) subdir = 'other'; // flat structure fallback
        if (!subdir) return;
        if (!folders[productName]) folders[productName] = [];
        folders[productName].push(f);
    });

    var folderNames = Object.keys(folders);
    if (!folderNames.length) {
        status.textContent = '❌ Không tìm thấy ảnh trong thư mục';
        input.value = '';
        return;
    }

    // Match folders to product cards by fuzzy title matching
    var cards = Array.from(document.querySelectorAll('[id^="pcard-"]'));
    var matched = 0;

    // Compute all match scores
    var scores = [];
    cards.forEach(function(card, ci) {
        var url = card.querySelector('.pc-url')?.value || '';
        var title = (window._importedProducts || []).find(function(p) { return p.url === url; })?.title || '';
        if (!title) {
            try { title = decodeURIComponent(url.split('shopee.vn/')[1] || '').split('-i.')[0].replace(/-/g, ' '); } catch(e) {}
        }
        if (!title) return;
        folderNames.forEach(function(fn, fi) {
            var score = _fuzzyMatch(title.toLowerCase(), fn.toLowerCase());
            if (score > 0.2) scores.push({ ci: ci, fi: fi, score: score, card: card, folder: fn });
        });
    });

    // Sort by score descending, assign greedily
    scores.sort(function(a, b) { return b.score - a.score; });
    var usedCards = {};
    var usedFolders = {};
    scores.forEach(function(s) {
        if (usedCards[s.ci] || usedFolders[s.fi]) return;
        addFilesToCard(s.card, folders[s.folder]);
        usedCards[s.ci] = true;
        usedFolders[s.fi] = true;
        matched++;
    });

    // Fallback: assign remaining folders to remaining cards by position
    if (matched < cards.length) {
        var remainingFolders = folderNames.filter(function(_, fi) { return !usedFolders[fi]; });
        var remainingCards = cards.filter(function(_, ci) { return !usedCards[ci]; });
        for (var ri = 0; ri < Math.min(remainingCards.length, remainingFolders.length); ri++) {
            addFilesToCard(remainingCards[ri], folders[remainingFolders[ri]]);
            matched++;
        }
    }

    status.textContent = '✅ Gán ảnh cho ' + matched + '/' + cards.length + ' sản phẩm (' + Object.keys(folders).length + ' thư mục)';
    // Debug: log matching details
    console.log('Image folders found:', Object.keys(folders).map(function(k) { return k + ' (' + folders[k].length + ' files)'; }));
    console.log('Match scores:', scores.slice(0, 10).map(function(s) { return s.folder + ' → card ' + s.ci + ' (score=' + s.score.toFixed(2) + ')'; }));
    input.value = '';
}

function _fuzzyMatch(a, b) {
    // Normalize: underscores to spaces, strip Vietnamese diacritics
    function norm(s) {
        return s.replace(/_/g, ' ')
            .normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D')
            .toLowerCase();
    }
    var na = norm(a);
    var nb = norm(b);
    var wordsA = na.split(/\s+/).filter(function(w) { return w.length > 1; });
    var wordsB = nb.split(/\s+/).filter(function(w) { return w.length > 1; });
    if (!wordsA.length || !wordsB.length) return 0;
    var matches = 0;
    wordsA.forEach(function(wa) {
        if (wordsB.some(function(wb) { return wb.includes(wa) || wa.includes(wb); })) matches++;
    });
    return matches / Math.max(wordsA.length, wordsB.length);
}

function _extractShopeeItemId(url) {
    var m = url.match(/[-.]i\.(\d+\.\d+)/);
    return m ? m[1] : '';
}

// === Import from Extension ===
async function importFromExtension() {
    var status = document.getElementById('import-status');
    status.textContent = '⏳ Đang lấy dữ liệu từ extension...';
    try {
        var resp = await fetch('/poll-shopee-queue');
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        var data = await resp.json();
        var products = data.products || [];
        if (!products.length) {
            status.textContent = '⚠️ Chưa có sản phẩm. Scrape từ extension trước.';
            return;
        }
        var added = 0, enriched = 0;
        products.forEach(function(p) {
            if (!p.url) return;
            var scrapedData = {
                title: p.title || '',
                description: p.description || '',
                price: p.price || '',
                rating: p.rating || null,
                rating_count: p.rating_count || 0,
                sold_count: p.sold_count || 0,
                reviews: p.reviews || [],
            };
            var pItemId = _extractShopeeItemId(p.url);
            var existingInput = Array.from(document.querySelectorAll('[id^="pcard-"] .pc-url')).find(function(el) {
                if (!el.value) return false;
                if (el.value === p.url) return true;
                var elItemId = _extractShopeeItemId(el.value);
                return elItemId && pItemId && elItemId === pItemId;
            });
            var card;
            if (existingInput) {
                card = existingInput.closest('[id^="pcard-"]');
                card._scrapedData = scrapedData;
                card.dataset.scraped = JSON.stringify(scrapedData);
                enriched++;
            } else {
                var id = addProductCard(p.url, '');
                card = document.getElementById('pcard-' + id);
                card._scrapedData = scrapedData;
                card.dataset.scraped = JSON.stringify(scrapedData);
                added++;
            }
            if (card) {
                var oldInfo = card.querySelector('.pc-scraped-info');
                if (oldInfo) oldInfo.remove();
                var info = document.createElement('div');
                info.className = 'pc-scraped-info';
                info.style.cssText = 'font-size:.8em;color:#4ecca3;margin-top:4px;padding:4px 8px;background:#f0fdf9;border-radius:6px';
                var title = (p.title || '').substring(0, 50);
                var meta = [];
                if (p.rating) meta.push(p.rating + '/5');
                if (p.rating_count) meta.push(p.rating_count + ' ratings');
                if (p.sold_count) meta.push(p.sold_count + ' sold');
                info.textContent = '🔌 ' + title + (meta.length ? ' (' + meta.join(', ') + ')' : '');
                card.querySelector('.pc-dropzone').before(info);
            }
        });
        var msg = [];
        if (added) msg.push(added + ' thêm mới');
        if (enriched) msg.push(enriched + ' đã gán data');
        status.textContent = msg.length ? '✅ ' + msg.join(', ') : '⚠️ Không có sản phẩm nào';
    } catch(e) {
        status.textContent = '❌ ' + e.message;
    }
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
    if (!card._aiPicks) card._aiPicks = new Set();
    for (var i = 0; i < files.length; i++) {
        if (!files[i].type.startsWith('image/')) continue;
        var file = files[i];
        card._files.push(file);
        var idx = card._files.length;
        var wrap = document.createElement('div');
        wrap.style.cssText = 'position:relative;display:inline-block;cursor:pointer';
        var img = document.createElement('img');
        img.style.cssText = 'height:120px;border-radius:4px;object-fit:cover;border:2px solid transparent';
        img.src = URL.createObjectURL(file);
        var numBadge = document.createElement('span');
        numBadge.className = 'img-num';
        numBadge.style.cssText = 'position:absolute;bottom:4px;left:4px;background:rgba(0,0,0,0.7);color:#fff;font-size:10px;padding:1px 5px;border-radius:4px;z-index:3';
        numBadge.textContent = idx;
        // Click to toggle AI reference selection
        (function(c, w, im, fileRef) {
            w.addEventListener('click', function(e) {
                if (e.target.tagName === 'BUTTON') return; // don't toggle on remove click
                if (c._aiPicks.has(fileRef)) {
                    c._aiPicks.delete(fileRef);
                    im.style.border = '2px solid transparent';
                    w.querySelector('.ai-badge')?.remove();
                } else if (c._aiPicks.size < 3) {
                    c._aiPicks.add(fileRef);
                    im.style.border = '2px solid #7c3aed';
                    var badge = document.createElement('span');
                    badge.className = 'ai-badge';
                    badge.style.cssText = 'position:absolute;top:-4px;left:-4px;background:#7c3aed;color:#fff;font-size:9px;padding:1px 4px;border-radius:4px;z-index:3';
                    badge.textContent = '🤖 AI';
                    w.appendChild(badge);
                }
                _updateAiLabel(c);
            });
        })(card, wrap, img, file);
        var btn = document.createElement('button');
        btn.textContent = '✕';
        btn.style.cssText = 'position:absolute;top:-4px;right:-4px;background:#e94560;color:#fff;border:none;border-radius:50%;width:18px;height:18px;font-size:10px;cursor:pointer;line-height:18px;padding:0;z-index:4';
        btn.onclick = (function(c, w, fileRef) {
            return function(e) {
                e.stopPropagation();
                var fi = c._files.indexOf(fileRef);
                if (fi >= 0) c._files.splice(fi, 1);
                c._aiPicks.delete(fileRef);
                w.remove();
                _updateAiLabel(c);
                _updateImageCount(c);
            };
        })(card, wrap, file);
        wrap.appendChild(img);
        wrap.appendChild(btn);
        wrap.appendChild(numBadge);
        thumbs.appendChild(wrap);
    }
    card.querySelector('.pc-dropzone').style.borderColor = '#4ecca3';
    // Show image count
    var countEl = card.querySelector('.pc-img-count');
    if (!countEl) { countEl = document.createElement('span'); countEl.className = 'pc-img-count'; countEl.style.cssText = 'font-size:.8em;color:#666;margin-left:8px'; card.querySelector('.pc-dropzone').after(countEl); }
    countEl.textContent = '📷 ' + card._files.length + ' ảnh';
    _updateAiLabel(card);
}

function _updateAiLabel(card) {
    var existing = card.querySelector('.ai-label');
    if (existing) existing.remove();
    var label = document.createElement('div');
    label.className = 'ai-label';
    label.style.cssText = 'font-size:.75em;color:#7c3aed;margin-top:2px';
    var count = card._aiPicks ? card._aiPicks.size : 0;
    label.textContent = count > 0
        ? '🤖 ' + count + '/3 ảnh được chọn cho AI (click ảnh để chọn/bỏ)'
        : '🤖 Click chọn tối đa 3 ảnh cho AI tham chiếu';
    card.querySelector('.pc-thumbs').parentElement.appendChild(label);
}

function _updateImageCount(card) {
    var countEl = card.querySelector('.pc-img-count');
    if (countEl) countEl.textContent = '📷 ' + (card._files ? card._files.length : 0) + ' ảnh';
    card.querySelectorAll('.pc-thumbs .img-num').forEach(function(badge, i) {
        badge.textContent = i + 1;
    });
}

function _rebuildDivider() {} // no-op, kept for compatibility

function getProductCards() {
    var cards = document.querySelectorAll('[id^="pcard-"]');
    var products = [];
    cards.forEach(function(card) {
        var url = card.querySelector('.pc-url')?.value?.trim();
        var aff = card.querySelector('.pc-aff')?.value?.trim() || '';
        // If no product URL but has affiliate link, use affiliate as URL
        if ((!url || !url.startsWith('http')) && aff && aff.startsWith('http')) {
            url = aff;
        }
        if (!url || !url.startsWith('http')) return;
        var scraped = card._scrapedData || null;
        if (!scraped && card.dataset.scraped) {
            try { scraped = JSON.parse(card.dataset.scraped); } catch(e) {}
        }
        products.push({ url: url, affiliate: card.querySelector('.pc-aff')?.value?.trim() || '', files: card._files || [], aiFiles: card._aiPicks ? Array.from(card._aiPicks) : [], scrapedData: scraped });
    });
    return products;
}

document.addEventListener('DOMContentLoaded', function() { addProductCard(); });

// === Batch State ===
var _batchState = { products: [], currentIdx: 0, results: [] };

function _saveBatchState() {
    try {
        var s = JSON.parse(JSON.stringify(_batchState, function(k, v) {
            if (v instanceof File) return undefined;
            return v;
        }));
        sessionStorage.setItem('batchState', JSON.stringify(s));
        // Also save to server
        fetch('/api/batch/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({batch_id: _batchState._batchId || '', reviews: _batchState.reviews || []})
        }).then(function(r) { return r.json(); }).then(function(d) {
            if (d.batch_id) _batchState._batchId = d.batch_id;
        }).catch(function() {});
    } catch(e) {}
}

function _restoreBatchState() {
    // Try sessionStorage first (faster)
    try {
        var s = sessionStorage.getItem('batchState');
        if (s) {
            _batchState = JSON.parse(s);
            if (_batchState.reviews && _batchState.reviews.length) {
                batchStep2Render();
                return true;
            }
        }
    } catch(e) {}
    // Fallback: restore from server
    try {
        var xhr = new XMLHttpRequest();
        xhr.open('GET', '/api/batch/latest', false); // sync for page load
        xhr.send();
        if (xhr.status === 200) {
            var job = JSON.parse(xhr.responseText);
            if (job.reviews && job.reviews.length) {
                _batchState.reviews = job.reviews;
                _batchState._batchId = job.id;
                batchStep2Render();
                return true;
            }
        }
    } catch(e) {}
    return false;
}

// Restore on load
if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', function() {
        _restoreBatchState();
    });
}

async function startBatchReview() {
    var products = getProductCards();
    if (products.length === 0) { alert('Thêm ít nhất 1 sản phẩm!'); return; }
    var noImages = products.filter(function(p) { return !p.files.length; });
    if (noImages.length > 0) {
        if (!confirm('⚠️ ' + noImages.length + ' sản phẩm chưa có ảnh. Video sẽ chỉ dùng ảnh AI (hoặc màn hình đen nếu AI thất bại).\n\nTiếp tục?')) return;
    }
    var selectedPlatforms = [];
    if (document.getElementById('batch-plat-facebook').checked) selectedPlatforms.push('facebook');
    if (document.getElementById('batch-plat-instagram').checked) selectedPlatforms.push('instagram');
    if (document.getElementById('batch-plat-tiktok').checked) selectedPlatforms.push('tiktok');
    if (document.getElementById('batch-plat-youtube').checked) selectedPlatforms.push('youtube');
    if (document.getElementById('batch-plat-threads').checked) selectedPlatforms.push('threads');
    if (selectedPlatforms.length === 0) { alert('Chọn ít nhất 1 nền tảng!'); return; }
    var btn = document.getElementById('btn-batch-review');
    var progress = document.getElementById('batch-progress');
    var results = document.getElementById('batch-results');
    var batchVoice = getGlobalVoice();
    var wordCount = document.getElementById('batch-word-count-fb')?.value || '120';
    var wordCountFb = document.getElementById('batch-word-count-fb')?.value || '120';
    btn.disabled = true;
    results.innerHTML = '';
    _batchState = { products: products, currentIdx: 0, results: [], voice: batchVoice, wordCount: wordCount, wordCountFb: wordCountFb, platforms: selectedPlatforms };
    batchLog('Products: ' + products.length + ', Voice: ' + batchVoice.type);

    // Step 1: Suggest 2 personas per product, user picks 1
    progress.innerHTML = '<div style="font-size:.9em">⏳ Bước 1: Phân tích đối tượng khách hàng...</div>';
    for (var i = 0; i < products.length; i++) {
        var p = products[i];
        try {
            var imported = (window._importedProducts || []).find(function(ip) { return ip.url === p.url; });
            var slug = (imported && imported.title && imported.title.length > 5) ? imported.title : decodeURIComponent(p.url.split('shopee.vn/')[1] || '').split('-i.')[0].replace(/-/g, ' ');
            // If slug is too short/meaningless, fetch real title from AffiPad
            if (!slug || slug.length < 5 || slug.match(/^[a-zA-Z0-9]{5,15}$/)) {
                try {
                    var titleResp = await fetch('/fetch-product-title', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:p.url})});
                    var titleData = await titleResp.json();
                    if (titleData.title && titleData.title.length > 5) slug = titleData.title;
                } catch(e) {}
            }
            var fd = new FormData();
            fd.append('title', slug);
            var resp = await fetch('/suggest-personas', { method: 'POST', body: fd });
            var pdata = await resp.json();
            p.personas = (pdata.personas || []).slice(0, 2);
            if (!p.personas.length || pdata.error) throw new Error(pdata.error || 'Empty personas');
            batchLog('📦 ' + (i+1) + '. ' + slug.substring(0,40) + ' → ' + p.personas.map(x => x.name).join(', '));
            p.title = slug;
        } catch(e) {
            // Retry once
            try {
                var fd2 = new FormData();
                fd2.append('title', slug || p.url);
                var resp2 = await fetch('/suggest-personas', { method: 'POST', body: fd2 });
                var pdata2 = await resp2.json();
                p.personas = (pdata2.personas || []).slice(0, 2);
                if (p.personas.length) {
                    batchLog('🔄 Retry OK for ' + (i+1));
                    p.title = slug || p.url.substring(0, 50);
                    continue;
                }
            } catch(e2) {}
            batchLog('❌ Persona failed for ' + (i+1) + ': ' + e.message);
            p.personas = [];
            p.personaFailed = true;
            p.title = slug || p.url.substring(0, 50);
        }
    }

    var html = '<h3 style="margin-bottom:12px">📋 Bước 1: Xác nhận đối tượng khách hàng</h3>';
    products.forEach(function(p, i) {
        html += '<div class="result-card" style="padding:12px;margin-bottom:8px">';
        html += '<strong>' + (i+1) + '. ' + (p.title||'').substring(0,60) + '</strong>';
        if (p.personaFailed) {
            html += '<div style="margin-top:6px;color:#e94560;font-size:.85em">⚠️ Không thể gợi ý đối tượng (LLM lỗi). ';
            html += '<button class="btn" onclick="retryPersona(' + i + ')" style="padding:3px 10px;font-size:.85em">🔄 Thử lại</button></div>';
        } else {
            html += '<div style="margin-top:6px;display:flex;align-items:center;gap:8px"><select id="persona-select-' + i + '" style="padding:6px 10px;border-radius:6px;border:1.5px solid #ddd;font-size:.85em;flex:1">';
            p.personas.forEach(function(per, j) {
                html += '<option value="' + j + '">🎯 ' + per.name + ' (' + (per.focus||'') + ')</option>';
            });
            html += '</select><button onclick="retryPersona(' + i + ')" style="padding:4px 8px;border:1px solid #ddd;border-radius:6px;cursor:pointer;font-size:.8em" title="Gợi ý lại">🔄</button></div>';
        }
        html += '</div>';
    });
    html += '<div style="margin-top:12px"><button class="btn" onclick="batchStep2()" style="padding:10px 24px">✅ Tiếp tục → Tạo Review</button> ';
    html += '<button onclick="document.getElementById(\'btn-batch-review\').disabled=false;document.getElementById(\'batch-results\').innerHTML=\'\'" style="padding:10px 16px;background:#eee;border:1px solid #ddd;border-radius:8px;cursor:pointer">❌ Hủy</button></div>';
    results.innerHTML = html;
    progress.innerHTML = '';
}

async function retryPersona(idx) {
    var p = _batchState.products[idx];
    if (!p) return;
    try {
        var fd = new FormData();
        fd.append('title', p.title || p.url);
        var resp = await fetch('/suggest-personas', { method: 'POST', body: fd });
        var pdata = await resp.json();
        p.personas = (pdata.personas || []).slice(0, 2);
        if (p.personas.length) {
            p.personaFailed = false;
            var card = document.querySelectorAll('.result-card')[idx];
            if (card) {
                var div = card.querySelector('div[style*="color"]') || card.lastElementChild;
                div.outerHTML = '<div style="margin-top:6px"><select id="persona-select-' + idx + '" style="padding:6px 10px;border-radius:6px;border:1.5px solid #ddd;font-size:.85em">' +
                    p.personas.map(function(per, j) { return '<option value="' + j + '">🎯 ' + per.name + ' (' + (per.focus||'') + ')</option>'; }).join('') +
                    '</select></div>';
                var manual = card.querySelector('input[id^="persona-manual"]');
                if (manual) manual.remove();
            }
            batchLog('🔄 Retry persona OK for ' + (idx+1));
        } else {
            alert('Vẫn không thể gợi ý. Nhập thủ công bên dưới.');
        }
    } catch(e) {
        alert('Lỗi: ' + e.message);
    }
}

async function batchStep2() {
    // Skip products with no persona
    var products = _batchState.products.filter(function(p) { return p.personas && p.personas.length; });
    if (!products.length) {
        alert('⚠️ Không có sản phẩm nào có đối tượng. Bấm 🔄 Thử lại hoặc quay lại sau.');
        return;
    }
    var skipped = _batchState.products.length - products.length;
    if (skipped) batchLog('⚠️ Bỏ qua ' + skipped + ' sản phẩm không có đối tượng');

    // Read persona selections BEFORE replacing HTML
    _batchState.products.forEach(function(p, i) {
        var sel = document.getElementById('persona-select-' + i);
        if (sel) {
            var selIdx = parseInt(sel.value || '0');
            p.selectedPersona = p.personas[selIdx] || p.personas[0];
            batchLog('Persona ' + (i+1) + ': selected "' + p.selectedPersona.name + '" (index ' + selIdx + ')');
        }
    });

    var products = _batchState.products.filter(function(p) { return p.personas && p.personas.length; });
    var progress = document.getElementById('batch-progress');
    var results = document.getElementById('batch-results');
    results.innerHTML = '<h3 style="margin-bottom:12px">⏳ Bước 2a: Tạo Review...</h3>';
    var allReviews = [];

    // Step 2a: Review text only (fast, retryable)
    for (var i = 0; i < products.length; i++) {
        var p = products[i];
        var persona = p.selectedPersona || p.personas[0];
        progress.innerHTML = '<div style="font-size:.9em">⏳ Review ' + (i+1) + '/' + products.length + ' — ' + persona.name + '...</div>' +
            '<div style="background:#eee;border-radius:4px;height:8px;margin-top:6px"><div style="background:#e94560;height:8px;border-radius:4px;width:' + ((i+1)/products.length*100) + '%"></div></div>';
        batchLog('📝 Review: ' + (p.title||'').substring(0,30) + ' × ' + persona.name);
        try {
            var fd = new FormData();
            fd.append('url', p.url);
            if (p.affiliate) fd.append('affiliate_url', p.affiliate);
            fd.append('custom_audience', JSON.stringify(persona));
            fd.append('word_count_tk', _batchState.wordCount);
            fd.append('word_count_fb', _batchState.wordCountFb);
            fd.append('platforms', _batchState.platforms.join(','));
            if (p.scrapedData) {
                batchLog('📊 Scraped: rating=' + p.scrapedData.rating + ' reviews=' + (p.scrapedData.reviews||[]).length + ' desc=' + (p.scrapedData.description||'').length);
                if (p.scrapedData.reviews && p.scrapedData.reviews.length) fd.append('scraped_reviews', JSON.stringify(p.scrapedData.reviews));
                if (p.scrapedData.rating) fd.append('scraped_rating', p.scrapedData.rating);
                if (p.scrapedData.rating_count) fd.append('scraped_rating_count', p.scrapedData.rating_count);
                if (p.scrapedData.sold_count) fd.append('scraped_sold_count', p.scrapedData.sold_count);
                if (p.scrapedData.description) fd.append('scraped_description', p.scrapedData.description);
                if (p.scrapedData.price) fd.append('scraped_price', p.scrapedData.price);
            } else {
                batchLog('⚠️ No scrapedData for this product');
            }
            var resp = await fetch('/batch-review', { method: 'POST', body: fd });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            var data = await resp.json();
            var review = data.facebook?.social_post || data.tiktok?.social_post || '';
            if (!review) throw new Error('Review trống (LLM lỗi)');
            allReviews.push({ product: p, persona: persona, data: data, idx: i, reviewDone: true, assetsDone: false });
            batchLog('✅ Review OK → ' + review.length + ' ký tự');
        } catch(e) {
            batchLog('❌ Review: ' + e.message);
            allReviews.push({ product: p, persona: persona, data: null, error: e.message, idx: i, reviewDone: false, assetsDone: false });
        }
    }
    _batchState.reviews = allReviews;
    _saveBatchState();
    progress.innerHTML = '';
    batchStep2aRender();
}

function batchStep2aRender() {
    var allReviews = _batchState.reviews;
    var results = document.getElementById('batch-results');
    var html = '<h3 style="margin-bottom:12px">📋 Bước 2a: Review</h3>';
    allReviews.forEach(function(r, ri) {
        html += '<div class="result-card" style="padding:12px;margin-bottom:8px">';
        html += '<strong>' + (r.idx+1) + '. ' + (r.product.title||'').substring(0,60) + '</strong> — 🎯 ' + r.persona.name;
        if (r.error) {
            html += ' <span style="color:red">❌ ' + r.error + '</span>';
            html += ' <button class="btn" onclick="retryBatchReview(' + ri + ')" style="padding:3px 10px;font-size:.8em;background:#e94560">🔄 Thử lại</button>';
        } else {
            var review = r.data?.facebook?.social_post || r.data?.tiktok?.social_post || '';
            html += ' <span style="color:green">✅</span> <span style="font-size:.8em;color:#666">' + review.length + ' ký tự</span>';
            html += ' <button onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display===\'none\'?\'block\':\'none\'" style="padding:2px 8px;border:1px solid #ddd;border-radius:4px;cursor:pointer;font-size:.75em;background:#f8f9fa;margin-left:6px">👁️</button>';
            html += '<div style="display:none;margin-top:8px;font-size:.85em">';
            html += '<pre style="white-space:pre-wrap;background:#f8f9fa;padding:8px;border-radius:4px;margin-top:4px;font-family:inherit;font-size:.9em">' + review.replace(/</g,'&lt;') + '</pre>';
            html += '</div>';
        }
        html += '</div>';
    });
    var hasSuccess = allReviews.some(function(r) { return r.reviewDone; });
    if (hasSuccess) {
        html += '<div style="margin-top:12px"><button class="btn" onclick="batchStep2b()" style="padding:10px 24px">✅ Tiếp tục → Tạo Audio & Ảnh</button> ';
        html += '<button onclick="document.getElementById(\'btn-batch-review\').disabled=false;document.getElementById(\'batch-results\').innerHTML=\'\'" style="padding:10px 16px;background:#eee;border:1px solid #ddd;border-radius:8px;cursor:pointer">❌ Hủy</button></div>';
    }
    results.innerHTML = html;
}

async function retryBatchReview(ri) {
    var r = _batchState.reviews[ri];
    if (!r) return;
    var p = r.product;
    var persona = r.persona;
    batchLog('🔄 Retry review: ' + (p.title||'').substring(0,30));
    try {
        var fd = new FormData();
        fd.append('url', p.url);
        if (p.affiliate) fd.append('affiliate_url', p.affiliate);
        fd.append('custom_audience', JSON.stringify(persona));
        fd.append('word_count_tk', _batchState.wordCount);
        fd.append('word_count_fb', _batchState.wordCountFb);
        fd.append('platforms', _batchState.platforms.join(','));
        if (p.scrapedData) {
            if (p.scrapedData.reviews && p.scrapedData.reviews.length) fd.append('scraped_reviews', JSON.stringify(p.scrapedData.reviews));
            if (p.scrapedData.rating) fd.append('scraped_rating', p.scrapedData.rating);
            if (p.scrapedData.rating_count) fd.append('scraped_rating_count', p.scrapedData.rating_count);
            if (p.scrapedData.sold_count) fd.append('scraped_sold_count', p.scrapedData.sold_count);
            if (p.scrapedData.description) fd.append('scraped_description', p.scrapedData.description);
            if (p.scrapedData.price) fd.append('scraped_price', p.scrapedData.price);
        }
        var resp = await fetch('/batch-review', { method: 'POST', body: fd });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        var data = await resp.json();
        var review = data.facebook?.social_post || data.tiktok?.social_post || '';
        if (!review) throw new Error('Review trống');
        _batchState.reviews[ri] = { product: p, persona: persona, data: data, idx: r.idx, reviewDone: true, assetsDone: false };
        batchLog('✅ Retry OK');
        batchStep2aRender();
    } catch(e) {
        batchLog('❌ Retry failed: ' + e.message);
        alert('Vẫn lỗi: ' + e.message);
    }
}

async function batchStep2b() {
    // Step 2b: Generate audio + images for successful reviews
    var reviews = _batchState.reviews.filter(function(r) { return r.reviewDone && !r.assetsDone; });
    if (!reviews.length) { batchStep2Render(); return; }

    var progress = document.getElementById('batch-progress');
    var results = document.getElementById('batch-results');
    results.innerHTML = '<h3 style="margin-bottom:12px">⏳ Bước 2b: Audio & Ảnh...</h3>';

    for (var i = 0; i < reviews.length; i++) {
        var r = reviews[i];
        var p = r.product;
        progress.innerHTML = '<div style="font-size:.9em">⏳ Assets ' + (i+1) + '/' + reviews.length + ' — ' + (p.title||'').substring(0,30) + '...</div>' +
            '<div style="background:#eee;border-radius:4px;height:8px;margin-top:6px"><div style="background:#e94560;height:8px;border-radius:4px;width:' + ((i+1)/reviews.length*100) + '%"></div></div>';
        batchLog('🎵🖼️ Assets: ' + (p.title||'').substring(0,30));
        try {
            var fd = new FormData();
            fd.append('review_json', JSON.stringify(r.data));
            fd.append('url', p.url);
            fd.append('platforms', _batchState.platforms.join(','));
            fd.append('voice_type', _batchState.voice.type);
            fd.append('voice_id', _batchState.voice.voiceId);
            fd.append('edge_voice', _batchState.voice.edgeVoice || 'vi-VN-HoaiMyNeural');
            fd.append('voice_speed', 100 + parseInt(_batchState.voice.speed));
            // Send images
            var aiSet = new Set(p.aiFiles || []);
            (p.aiFiles || []).forEach(function(f) { fd.append('media', f); });
            (p.files || []).forEach(function(f) { if (!aiSet.has(f)) fd.append('media', f); });
            var resp = await fetch('/batch-assets', { method: 'POST', body: fd });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            var data = await resp.json();
            r.data = data;
            r.assetsDone = true;
            var aiStatus = data._ai_status || {};
            var aiMsg = aiStatus.expected ? ' (AI: ' + (aiStatus.generated||0) + '/' + aiStatus.expected + ')' : '';
            if (aiStatus.real_images < 5 && aiStatus.expected === 0) aiMsg = ' ⚠️ <5 ảnh, không tạo AI';
            if (aiStatus.expected > 0 && aiStatus.generated < aiStatus.expected) r.aiIncomplete = true;
            batchLog('✅ Assets OK — images:' + (data.product_images||[]).length + aiMsg);
            _saveBatchState();
        } catch(e) {
            batchLog('❌ Assets: ' + e.message);
            r.assetsError = e.message;
        }
    }
    progress.innerHTML = '';
    batchStep2Render();
}

function batchStep2Render() {
    var allReviews = _batchState.reviews;
    var results = document.getElementById('batch-results');
    var html = '<h3 style="margin-bottom:12px">📋 Bước 2: Xem lại Review</h3>';
    var lastIdx = -1;
    allReviews.forEach(function(r, ri) {
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
            html += ' <button class="btn" onclick="retryBatchReview(' + ri + ')" style="padding:3px 10px;font-size:.8em;background:#e94560">🔄 Review</button>';
        } else if (r.assetsError) {
            html += ' <span style="color:orange">⚠️ Review ✅ nhưng audio/ảnh lỗi: ' + r.assetsError + '</span>';
            html += ' <button class="btn" onclick="retryBatchAssets(' + ri + ')" style="padding:3px 10px;font-size:.8em;background:#f59e0b">🔄 Assets</button>';
        } else if (!r.assetsDone) {
            html += ' <span style="color:#666">📝 Review ✅ — chưa tạo audio/ảnh</span>';
        } else {
            var aiStatus = r.data?._ai_status || {};
            if (aiStatus.real_images < 5 && !aiStatus.expected) {
                html += ' <span style="color:orange;font-size:.8em">⚠️ Ít hơn 5 ảnh — không tạo AI images</span>';
            }
            if (r.aiIncomplete) {
                html += ' <span style="color:orange;font-size:.8em">⚠️ AI ảnh thiếu (' + (aiStatus.generated||0) + '/' + aiStatus.expected + ')</span>';
                html += ' <button class="btn" onclick="retryBatchAssets(' + ri + ')" style="padding:3px 10px;font-size:.8em;background:#f59e0b">🔄 AI ảnh</button>';
            }
            var fb = r.data?.facebook?.social_post || r.data?.tiktok?.social_post || '';
            var fbAudio = r.data?.facebook?.audio_url || r.data?.tiktok?.audio_url || '';
            if (fbAudio) html += '<div style="margin-top:4px"><span style="font-size:.8em;color:#666">🎧 Audio:</span> <audio controls style="height:24px;vertical-align:middle"><source src="' + fbAudio + '"></audio></div>';
            if (!fbAudio && fb) html += '<div style="margin-top:4px;color:orange;font-size:.85em">⚠️ Audio thiếu <button class="btn" onclick="retryBatchAssets(' + ri + ')" style="padding:3px 10px;font-size:.8em;background:#f59e0b">🔄 Tạo lại audio</button></div>';
            html += '<div style="margin-top:6px;font-size:.85em">';
            html += '<details><summary>📝 Review (' + fb.length + ' ký tự)</summary><pre style="white-space:pre-wrap;background:#fff;padding:8px;border-radius:4px;margin-top:4px;font-family:inherit;font-size:.9em">' + fb.replace(/</g,'&lt;') + '</pre></details>';
            html += '</div>';
        }
        html += '</div>';
    });
    if (lastIdx >= 0) html += '</div>';
    var hasReady = allReviews.some(function(r) { return r.assetsDone; });
    html += '<div style="margin-top:12px">';
    if (hasReady) html += '<button class="btn" onclick="batchStep3()" style="padding:10px 24px">✅ Tiếp tục → Tạo Video</button> ';
    html += '<button onclick="document.getElementById(\'btn-batch-review\').disabled=false;document.getElementById(\'batch-results\').innerHTML=\'\'" style="padding:10px 16px;background:#eee;border:1px solid #ddd;border-radius:8px;cursor:pointer">❌ Hủy</button></div>';
    results.innerHTML = html;
}

async function retryBatchAssets(ri) {
    var r = _batchState.reviews[ri];
    if (!r || !r.data) return;
    var p = r.product;
    batchLog('🔄 Retry assets: ' + (p.title||'').substring(0,30));
    try {
        var fd = new FormData();
        fd.append('review_json', JSON.stringify(r.data));
        fd.append('url', p.url);
        fd.append('platforms', _batchState.platforms.join(','));
        fd.append('voice_type', _batchState.voice.type);
        fd.append('voice_id', _batchState.voice.voiceId);
        fd.append('edge_voice', _batchState.voice.edgeVoice || 'vi-VN-HoaiMyNeural');
        fd.append('voice_speed', 100 + parseInt(_batchState.voice.speed));
        var aiSet = new Set(p.aiFiles || []);
        (p.aiFiles || []).forEach(function(f) { fd.append('media', f); });
        (p.files || []).forEach(function(f) { if (!aiSet.has(f)) fd.append('media', f); });
        var resp = await fetch('/batch-assets', { method: 'POST', body: fd });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        var data = await resp.json();
        r.data = data;
        r.assetsDone = true;
        r.assetsError = null;
        _saveBatchState();
        batchLog('✅ Retry assets OK');
        batchStep2Render();
    } catch(e) {
        batchLog('❌ Retry assets failed: ' + e.message);
        alert('Vẫn lỗi: ' + e.message);
    }
}

async function batchStep3() {
    var reviews = _batchState.reviews.filter(r => r.data && r.assetsDone);
    var progress = document.getElementById('batch-progress');
    var results = document.getElementById('batch-results');
    results.innerHTML = '<h3 style="margin-bottom:12px">⏳ Bước 3: Tạo Video...</h3>';

    // Build video tasks — ONE video per review (shared across platforms)
    // Skip products without audio or images
    var tasks = [];
    var skipped = 0;
    var skipReasons = [];
    for (var i = 0; i < reviews.length; i++) {
        var hasAudio = reviews[i].data?.facebook?.audio_url || reviews[i].data?.tiktok?.audio_url;
        var hasImages = (reviews[i].data?.product_images || []).length > 0;
        if (!hasAudio || !hasImages) {
            var reason = !hasAudio ? 'thiếu audio' : 'thiếu ảnh';
            batchLog('⏭️ Bỏ qua ' + (reviews[i].product.title||'').substring(0,30) + ' — ' + reason);
            skipped++;
            continue;
        }
        tasks.push({ review: reviews[i], platform: 'tiktok' });
    }
    if (skipped) batchLog('⚠️ ' + skipped + ' sản phẩm bỏ qua. Tạo audio/ảnh trước rồi thử lại.');

    // Run with concurrency limit of 2
    var videoResults = [];
    var completed = 0;
    async function runTask(task, retries) {
        retries = retries || 0;
        try {
            var fd = new FormData();
            fd.append('review_json', JSON.stringify(task.review.data));
            fd.append('platform', task.platform);
            fd.append('aspect_ratio', '9:16');
            fd.append('voice_speed', 100 + parseInt(_batchState.voice.speed));
            fd.append('logo_text', document.getElementById('batch-logo-text')?.value?.trim() || '');
            fd.append('img_effect', 'random');
            fd.append('img_style', 'random');
            var resp = await fetch('/generate-video', { method: 'POST', body: fd });
            if (!resp.ok) {
                var errData = await resp.json().catch(function() { return {}; });
                throw new Error(errData.detail || 'HTTP ' + resp.status);
            }
            var vdata = await resp.json();
            batchLog('🎬 ' + task.review.persona.name + ' → ' + task.platform + ': ' + vdata.video_url);
            return { review: task.review, platform: task.platform, video_url: vdata.video_url, srt_url: vdata.srt_url };
        } catch(e) {
            if (retries < 1) {
                batchLog('⚠️ Retry video ' + task.platform + '...');
                return runTask(task, retries + 1);
            }
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

    videoResults.forEach(function(v, vi) {
        html += '<div class="result-card" style="padding:14px;margin-bottom:10px">';
        html += '<h4>📦 ' + (v.review.idx+1) + '. ' + (v.review.product.title||'').substring(0,50) + '</h4>';
        html += '<div style="font-size:.85em;color:#666;margin-bottom:8px">🎯 ' + v.review.persona.name + '</div>';
        if (v.error) {
            html += '<div style="margin:4px 0;font-size:.85em;color:red">❌ ' + v.error + ' <button class="btn" onclick="retryVideo(' + vi + ')" style="padding:2px 8px;font-size:.8em;background:#e94560">🔄</button></div>';
        } else {
            html += '<div style="display:inline-block;margin:6px 8px 6px 0;vertical-align:top">';
            html += '<video controls style="max-width:180px;border-radius:8px"><source src="' + v.video_url + '" type="video/mp4"></video>';
            html += '<br><a href="' + v.video_url + '" download class="btn" style="font-size:.75em;padding:4px 10px;margin-top:4px;display:inline-block">⬇️ Video</a>';
            html += '<div style="margin-top:6px">';
            html += '<select class="fb-page-sel" style="padding:2px 6px;border-radius:4px;border:1px solid #ddd;font-size:.7em;margin-right:4px"></select>';
            var publishPlatforms = _batchState.platforms.slice();
            if (publishPlatforms.indexOf('instagram') < 0 && window._igConnected) publishPlatforms.push('instagram');
            publishPlatforms.forEach(function(plat) {
                var icons = {facebook:'📘',instagram:'📷',tiktok:'🎵',youtube:'▶️'};
                var bgs = {facebook:'#1877f2',instagram:'#e1306c',tiktok:'#000',youtube:'#c00'};
                html += ' <button class="btn" onclick="batchPublish(' + vi + ',this,\'' + plat + '\')" style="font-size:.75em;padding:4px 10px;background:' + (bgs[plat]||'#1877f2') + '">' + (icons[plat]||'📤') + ' Đăng</button>';
            });
            html += ' <button class="btn" onclick="batchSchedule(' + vi + ',this)" style="font-size:.75em;padding:4px 10px;background:#f59e0b">⏰</button>';
            html += '</div>';
            html += '<span class="bp-status" style="font-size:.8em;display:block;margin-top:2px"></span>';
            html += '</div>';
        }
        html += '</div>';
    });
    results.innerHTML = html;
    window._batchVideoResults = videoResults;
    progress.innerHTML = '<div style="font-size:.9em;color:green">✅ Hoàn thành! Xem video và đăng bài bên dưới.</div>';
    document.getElementById('btn-batch-review').disabled = false;
    // Populate FB page selectors
    fetch('/api/facebook-pages').then(r=>r.json()).then(d=>{
        if (!d.pages || d.pages.length <= 1) return;
        document.querySelectorAll('.fb-page-sel').forEach(function(sel){
            sel.innerHTML = '';
            d.pages.forEach(function(p){ var o=document.createElement('option'); o.value=p.page_id; o.textContent=p.name; sel.appendChild(o); });
        });
    }).catch(()=>{});
}

async function retryVideo(vi) {
    var videoResults = window._batchVideoResults;
    if (!videoResults || !videoResults[vi]) return;
    var task = { review: videoResults[vi].review, platform: videoResults[vi].platform };
    batchLog('🔄 Retrying video ' + task.platform + ' for ' + (task.review.product.title||'').substring(0,30));
    try {
        var fd = new FormData();
        fd.append('review_json', JSON.stringify(task.review.data));
        fd.append('platform', task.platform);
        fd.append('aspect_ratio', '9:16');
        fd.append('voice_speed', 100 + parseInt(_batchState.voice.speed));
        fd.append('logo_text', document.getElementById('batch-logo-text')?.value?.trim() || '');
        var resp = await fetch('/generate-video', { method: 'POST', body: fd });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        var vdata = await resp.json();
        videoResults[vi] = { review: task.review, platform: task.platform, video_url: vdata.video_url, srt_url: vdata.srt_url };
        window._batchReviews[vi] = task.review.data;
        window._batchVideos[vi] = { url: vdata.video_url, platform: task.platform };
        batchLog('✅ Retry video OK: ' + vdata.video_url);
        batchStep3Render(videoResults);
    } catch(e) {
        batchLog('❌ Retry video failed: ' + e.message);
        alert('Vẫn lỗi: ' + e.message);
    }
}

function batchStep3Render(videoResults) {
    window._batchVideoResults = videoResults;
    var results = document.getElementById('batch-results');
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
        var labels = {facebook:'📘 Reels',instagram:'📷 IG Reels',tiktok:'🎵 TikTok',youtube:'▶️ YouTube'};
        var bgs = {facebook:'#1877f2',instagram:'#e1306c',tiktok:'#000',youtube:'#c00'};
        var label = labels[v.platform] || v.platform;
        if (v.error) {
            html += '<div style="margin:4px 0;font-size:.85em;color:red">❌ ' + label + ': ' + v.error + ' <button class="btn" onclick="retryVideo(' + vi + ')" style="padding:2px 8px;font-size:.8em;background:#e94560">🔄</button></div>';
        } else {
            html += '<div style="display:inline-block;margin:6px 8px 6px 0;vertical-align:top">';
            html += '<video controls style="max-width:180px;border-radius:8px"><source src="' + v.video_url + '" type="video/mp4"></video>';
            html += '<br><a href="' + v.video_url + '" download class="btn" style="font-size:.75em;padding:4px 10px;margin-top:4px;display:inline-block">⬇️ ' + label + '</a>';
            if (v.platform === 'facebook') html += ' <select class="fb-page-sel" style="padding:2px 6px;border-radius:4px;border:1px solid #ddd;font-size:.7em"></select>';
            html += ' <button class="btn" onclick="batchPublish(' + vi + ',this)" style="font-size:.75em;padding:4px 10px;margin-top:4px;background:' + (bgs[v.platform]||'#1877f2') + '">📤 Đăng</button>';
            html += ' <button class="btn" onclick="batchSchedule(' + vi + ',this)" style="font-size:.75em;padding:4px 10px;margin-top:4px;background:#f59e0b">⏰</button>';
            html += '<span class="bp-status" style="font-size:.8em;display:block;margin-top:2px"></span>';
            html += '</div>';
        }
    });
    if (lastReviewIdx >= 0) html += '</div>';
    results.innerHTML = html;
    // Populate FB page selectors
    fetch('/api/facebook-pages').then(r=>r.json()).then(d=>{
        if (!d.pages || d.pages.length <= 1) return;
        document.querySelectorAll('.fb-page-sel').forEach(function(sel){
            sel.innerHTML = '';
            d.pages.forEach(function(p){ var o=document.createElement('option'); o.value=p.page_id; o.textContent=p.name; sel.appendChild(o); });
        });
    }).catch(()=>{});
}

async function batchSchedule(vi, btn) {
    var videoResults = window._batchVideoResults;
    if (!videoResults || !videoResults[vi]) return;
    var reviewData = window._batchReviews[vi];
    var videoInfo = window._batchVideos[vi];
    var status = btn.parentElement.querySelector('.bp-status');
    // Show inline slot picker
    if (!btn.nextElementSibling || !btn.nextElementSibling.classList.contains('slot-pick')) {
        var wrap = document.createElement('span');
        wrap.className = 'slot-pick';
        wrap.style.cssText = 'margin-left:4px;font-size:.75em';
        wrap.innerHTML = '<select style="padding:2px 6px;border-radius:4px;border:1px solid #ddd" onchange="if(this.value===\'custom\'){this.nextElementSibling.style.display=\'inline\'}else{this.nextElementSibling.style.display=\'none\'}">' +
            '<option value="">Slot tiếp theo</option><option value="08:30">08:30</option><option value="12:00">12:00</option><option value="19:00">19:00</option><option value="21:30">21:30</option><option value="custom">📅 Tùy chọn...</option></select>' +
            '<input type="datetime-local" style="padding:2px 6px;border-radius:4px;border:1px solid #ddd;font-size:1em;display:none;margin-left:4px"> ' +
            '<button onclick="this.parentElement.previousElementSibling.click()" style="padding:2px 6px;border:none;background:#f59e0b;color:#fff;border-radius:4px;cursor:pointer">✓</button>';
        btn.after(wrap);
        return;
    }
    var sel = btn.nextElementSibling.querySelector('select');
    var dtInput = btn.nextElementSibling.querySelector('input');
    var slot = sel.value === 'custom' ? dtInput.value : sel.value;
    try {
        var fd = new FormData();
        fd.append('review_json', JSON.stringify(reviewData));
        fd.append('video_url', videoInfo.url);
        fd.append('platform', 'all');
        fd.append('slot', slot);
        var pageSelect = btn.parentElement.querySelector('.fb-page-sel');
        if (pageSelect && pageSelect.value) fd.append('page_id', pageSelect.value);
        var resp = await fetch('/schedule', {method: 'POST', body: fd});
        var data = await resp.json();
        if (status) status.innerHTML = '⏰ ' + data.slot;
        var pick = btn.nextElementSibling;
        if (pick && pick.classList.contains('slot-pick')) pick.remove();
    } catch(e) {
        if (status) status.textContent = '❌ ' + e.message;
    }
}

async function batchPublish(vi, btn, force) {
    var reviewData = window._batchReviews[vi];
    var videoInfo = window._batchVideos[vi];
    if (!reviewData || !videoInfo) { alert('Dữ liệu không tìm thấy'); return; }
    var isForce = (force === true);
    var platform = (typeof force === 'string') ? force : videoInfo.platform;
    var videoUrl = videoInfo.url;
    var status = btn.parentElement.querySelector('.bp-status');
    var label = {tiktok:'TikTok',facebook:'Facebook Reels',youtube:'YouTube Shorts',instagram:'Instagram Reels'}[platform] || platform;
    btn.disabled = true;
    if (status) status.textContent = '⏳ Đang đăng ' + label + '...';
    try {
        var fd = new FormData();
        fd.append('review_json', JSON.stringify(reviewData));
        fd.append('video_url', videoUrl);
        fd.append('platforms', platform);
        if (isForce) fd.append('force', '1');
        var pageSelect = btn.parentElement.querySelector('.fb-page-sel');
        if (pageSelect && pageSelect.value) fd.append('page_id', pageSelect.value);
        var resp = await fetch('/publish', {method: 'POST', body: fd});
        var data = await resp.json();
        if (data.duplicate_warning) {
            if (status) status.innerHTML = '⚠️ ' + data.warnings.join(', ') + ' <button onclick="batchPublish(' + vi + ',this.closest(\'div\').querySelector(\'button\'),true)" style="background:#e94560;color:#fff;border:none;border-radius:6px;padding:3px 10px;cursor:pointer;font-size:.8em">Đăng lại</button>';
            btn.disabled = false;
            return;
        }
        var r = (data.results || [])[0];
        if (r && status) {
            var msg = (r.success ? '✅' : '❌') + ' ' + r.message;
            if (r.post_id && r.success) {
                var urls = {facebook:'https://www.facebook.com/'+r.post_id, youtube:'https://youtu.be/'+r.post_id, instagram:'https://www.instagram.com/reel/'+r.post_id};
                if (urls[r.platform]) msg += ' <a href="'+urls[r.platform]+'" target="_blank">Xem →</a>';
            }
            status.innerHTML = msg;
        }
    } catch(e) {
        if (status) status.textContent = '❌ ' + e.message;
    }
    btn.disabled = false;
}
