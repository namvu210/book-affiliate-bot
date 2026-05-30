/* Form submission and review generation */

async function submitForm(url, formData) {
    document.getElementById('spinner').classList.add('show');
    document.getElementById('result').innerHTML = '';
    try {
        const resp = await fetch(url, { method: 'POST', body: formData });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Lỗi server');
        }
        const data = await resp.json();
        window._lastPdfPath = data._pdf_path || '';
        renderResult(data);
    } catch (e) {
        document.getElementById('result').innerHTML =
            `<div class="result-card" style="border-left:4px solid red"><h3>❌ Lỗi</h3><pre>${e.message}</pre></div>`;
    } finally {
        document.getElementById('spinner').classList.remove('show');
    }
}

function initForms() {
    document.getElementById('form-pdf').addEventListener('submit', e => {
        e.preventDefault();
        submitForm('/upload-pdf', new FormData(e.target));
    });

    document.getElementById('form-url').addEventListener('submit', e => {
        e.preventDefault();
        const sel = document.getElementById('audience-select');
        const caField = document.getElementById('custom-audience-json');
        if (sel.value === 'custom') {
            caField.value = JSON.stringify({
                name: document.getElementById('cp-name').value || 'Khách hàng',
                tone: document.getElementById('cp-tone').value || 'thân thiện',
                focus: document.getElementById('cp-focus').value || 'chất lượng sản phẩm',
            });
        } else if (sel.value.startsWith('suggested-')) {
            caField.value = sel.options[sel.selectedIndex].dataset.persona || '';
        } else {
            caField.value = '';
        }
        const fd = new FormData(e.target);
        if (window._shopeeBookmarkletData) {
            const sd = window._shopeeBookmarkletData;
            if (sd.reviews?.length) fd.set('scraped_reviews', JSON.stringify(sd.reviews));
            if (sd.rating) fd.set('scraped_rating', sd.rating);
            if (sd.rating_count) fd.set('scraped_rating_count', sd.rating_count);
            if (sd.sold_count) fd.set('scraped_sold_count', sd.sold_count);
            if (sd.description) fd.set('scraped_description', sd.description);
            if (sd.price) fd.set('scraped_price', sd.price);
        }
        const voice = getGlobalVoice();
        fd.set('voice_type', voice.type);
        fd.set('voice_speed', 100 + parseInt(voice.speed));
        fd.set('voice_id', voice.voiceId);
        submitForm('/from-url', fd);
    });
}

async function suggestPersonas() {
    const urlInput = document.querySelector('#panel-url input[name="url"]');
    const url = urlInput?.value?.trim();
    if (!url) { alert('Nhập link Shopee trước!'); return; }
    let slug = decodeURIComponent(url.split('shopee.vn/')[1] || '').split('-i.')[0].replace(/-/g, ' ');
    if (slug.startsWith('product/') || slug.length < 5) {
        if (window._shopeeBookmarkletData?.title) {
            slug = window._shopeeBookmarkletData.title;
        } else {
            try {
                const r = await fetch('/fetch-product-title', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: url }) });
                const d = await r.json();
                if (d.title) slug = d.title;
            } catch (e) { }
        }
    }
    const sel = document.getElementById('audience-select');
    sel.innerHTML = '<option disabled selected>⏳ Đang gợi ý...</option>';
    try {
        const fd = new FormData();
        fd.append('title', slug);
        const resp = await fetch('/suggest-personas', { method: 'POST', body: fd });
        if (!resp.ok) throw new Error('API error');
        const data = await resp.json();
        let opts = '';
        (data.personas || []).forEach((p, i) => {
            const pJson = JSON.stringify(p).replace(/'/g, '&#39;').replace(/"/g, '&quot;');
            opts += `<option value="suggested-${i}" data-persona="${pJson}" ${i === 0 ? 'selected' : ''}>🎯 ${p.name}</option>`;
        });
        opts += `<option value="custom">✏️ Tự nhập...</option>`;
        sel.innerHTML = opts;
        document.getElementById('custom-persona').style.display = 'none';
    } catch (e) {
        sel.innerHTML = `<option value="custom" selected>✏️ Tự nhập...</option>`;
        document.getElementById('custom-persona').style.display = 'block';
    }
}

async function regenReview(platform) {
    var btn = document.getElementById('btn-regen-' + platform);
    var textarea = document.getElementById('post-' + platform);
    if (!window._lastReviewData) return;
    btn.textContent = '⏳';
    btn.disabled = true;
    try {
        var data = window._lastReviewData;
        var book = data.book || {};
        var fd = new FormData();
        fd.append('platform', platform);
        fd.append('title', book.title || '');
        fd.append('author', book.author || '');
        fd.append('description', book.description || data.description || '');
        fd.append('shopee_url', data.affiliate_link || book.shopee_url || '');
        fd.append('word_count', platform === 'tiktok' ? '150' : '200');
        var audienceSel = document.getElementById('audience-select');
        if (audienceSel) fd.append('audience', audienceSel.value || '');
        var caField = document.getElementById('custom-audience-json');
        if (caField && caField.value) fd.append('custom_audience', caField.value);
        var styleSel = document.getElementById('review-style-select');
        if (styleSel) fd.append('review_style', styleSel.value || 'auto');
        if (book.rating) fd.append('scraped_rating', book.rating);
        if (book.rating_count) fd.append('scraped_rating_count', book.rating_count);
        if (book.sold_count) fd.append('scraped_sold_count', book.sold_count);
        if (book.reviews?.length) fd.append('scraped_reviews', JSON.stringify(book.reviews));
        if (window._shopeeBookmarkletData) {
            var sd = window._shopeeBookmarkletData;
            if (!book.rating && sd.rating) fd.append('scraped_rating', sd.rating);
            if (!book.rating_count && sd.rating_count) fd.append('scraped_rating_count', sd.rating_count);
            if (!book.sold_count && sd.sold_count) fd.append('scraped_sold_count', sd.sold_count);
            if (!book.reviews?.length && sd.reviews?.length) fd.append('scraped_reviews', JSON.stringify(sd.reviews));
        }
        var resp = await fetch('/regen-review', { method: 'POST', body: fd });
        var result = await resp.json();
        if (result.social_post) {
            textarea.value = result.social_post;
            if (!window._lastReviewData) window._lastReviewData = {};
            window._lastReviewData[platform] = result;
            if (!window._lastReviewData.facebook) window._lastReviewData.facebook = result;
            var captionEl = document.getElementById('caption-preview');
            if (captionEl) {
                var captionText = (result.social_post || '').replace(/\[[a-zA-Z_ ]+\]/g, '').replace(/  +/g, ' ').trim();
                var hashtags = (result.hashtags || []).map(h => '#' + h.replace(/^#/, '')).join(' ');
                var affLink = window._lastReviewData?.affiliate_link || window._lastReviewData?.book?.shopee_url || '';
                captionEl.textContent = captionText + (hashtags ? '\n\n' + hashtags : '') + (affLink ? '\n\n🛒 Mua ngay: ' + affLink : '');
            }
        }
    } catch (e) { alert('❌ ' + e.message); }
    btn.textContent = '🔄 Tạo lại';
    btn.disabled = false;
}
