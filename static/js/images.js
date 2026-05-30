/* Image fetching and gallery management */

async function fetchImages() {
    const urlInput = document.querySelector('#panel-url input[name="url"]');
    const url = urlInput?.value?.trim();
    if (!url) { alert('Nhập link Shopee trước!'); return; }
    document.getElementById('spinner').classList.add('show');
    document.getElementById('result').innerHTML = '';
    try {
        const fd = new FormData();
        fd.append('url', url);
        const resp = await fetch('/fetch-images', { method: 'POST', body: fd });
        if (!resp.ok) { const err = await resp.json(); throw new Error(err.detail || 'Lỗi'); }
        const data = await resp.json();
        let html = `<div class="book-meta">
            <strong>📖 ${data.title || ''}</strong>
            ${data.price ? ' | 💰 ' + data.price : ''}
            ${data.rating ? ' | ⭐ ' + data.rating + '/5' : ''}
        </div>`;
        const imgs = data.product_images || [];
        if (imgs.length > 0) {
            html += `<div class="result-card">
                <h3>🖼️ Ảnh & Video sản phẩm (${imgs.length})</h3>
                <div style="margin-bottom:10px">
                    <label style="display:inline;font-weight:normal;cursor:pointer">
                        <input type="checkbox" id="select-all-imgs" onchange="toggleAllImages(this.checked)"> Chọn tất cả
                    </label>
                    <button class="btn" onclick="downloadSelectedImages()" style="padding:6px 16px;font-size:.85em;margin:0 0 0 12px">⬇️ Tải ảnh đã chọn</button>
                </div>
                <div style="display:flex;flex-wrap:wrap;gap:12px;padding:10px 0">
                    ${imgs.map((img, i) => {
            const isVideo = img.match(/\.mp4/i);
            return `<div style="position:relative">
                            <input type="checkbox" class="img-check" data-url="${img}" data-index="${i}"
                                   style="position:absolute;top:6px;left:6px;width:20px;height:20px;z-index:2;cursor:pointer">
                            ${isVideo
                    ? `<video src="${img}" style="height:180px;border-radius:8px" controls></video>`
                    : `<img src="${img}" style="height:180px;border-radius:8px;cursor:pointer"
                                       onclick="window.open('${img}','_blank')">`
                }
                        </div>`;
        }).join('')}
                </div>
            </div>`;
        } else {
            html += `<div class="result-card"><p>Không tìm thấy ảnh. Kiểm tra lại cookies Shopee.</p></div>`;
        }
        document.getElementById('result').innerHTML = html;
    } catch (e) {
        document.getElementById('result').innerHTML =
            `<div class="result-card" style="border-left:4px solid red"><h3>❌ Lỗi</h3><pre>${e.message}</pre></div>`;
    } finally {
        document.getElementById('spinner').classList.remove('show');
    }
}

function toggleAllImages(checked) {
    document.querySelectorAll('.img-check').forEach(cb => cb.checked = checked);
}

function downloadSelectedImages() {
    const checked = document.querySelectorAll('.img-check:checked');
    if (checked.length === 0) { alert('Chọn ít nhất 1 ảnh để tải!'); return; }
    checked.forEach(cb => {
        const url = cb.dataset.url;
        const i = cb.dataset.index;
        const a = document.createElement('a');
        a.href = url;
        a.download = `product_${i}.jpg`;
        document.body.appendChild(a); a.click(); a.remove();
    });
}
