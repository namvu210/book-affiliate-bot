/* KOL profile management UI */

async function loadKolList() {
    var container = document.getElementById('kol-list');
    container.innerHTML = '<p style="color:#666">Đang tải...</p>';
    try {
        var resp = await fetch('/api/movie/kol/');
        var data = await resp.json();
        movieState.kols = data.profiles || [];
        renderKolList();
    } catch (e) {
        container.innerHTML = '<p style="color:red">Lỗi: ' + e.message + '</p>';
    }
}

function renderKolList() {
    var container = document.getElementById('kol-list');
    var kols = movieState.kols;
    if (!kols.length) {
        container.innerHTML = '<p style="color:#999;font-size:.9em">Chưa có KOL nào. Thêm KOL để bắt đầu tạo Movie Ad.</p>';
        return;
    }
    var html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px">';
    kols.forEach(function (k) {
        var thumb = k.turnaround_images.length ? k.turnaround_images[0] : '';
        var imgCount = k.turnaround_images.length;
        var selected = movieState.selectedKols.includes(k.id);
        html += '<div class="kol-card' + (selected ? ' selected' : '') + '" data-id="' + k.id + '" onclick="toggleKolSelect(\'' + k.id + '\')">';
        html += '<div style="position:relative">';
        if (thumb) html += '<img src="' + thumb + '" style="width:100%;height:140px;object-fit:cover;border-radius:8px 8px 0 0">';
        else html += '<div style="width:100%;height:140px;background:#f0f0f0;border-radius:8px 8px 0 0;display:flex;align-items:center;justify-content:center">📷</div>';
        html += '<span style="position:absolute;top:6px;right:6px;background:rgba(0,0,0,.6);color:#fff;padding:2px 8px;border-radius:10px;font-size:.75em">' + imgCount + ' ảnh</span>';
        if (selected) html += '<span style="position:absolute;top:6px;left:6px;background:#10b981;color:#fff;padding:2px 8px;border-radius:10px;font-size:.75em">✓ Đã chọn</span>';
        html += '</div>';
        html += '<div style="padding:10px">';
        html += '<strong style="font-size:.9em">' + k.name + '</strong>';
        if (k.description) html += '<p style="font-size:.8em;color:#666;margin:4px 0 0">' + k.description.substring(0, 60) + '</p>';
        html += '<div style="display:flex;gap:4px;margin-top:8px">';
        html += '<button onclick="event.stopPropagation();viewKolImages(\'' + k.id + '\')" style="border:none;background:#f0f2f5;border-radius:4px;padding:4px 8px;font-size:.75em;cursor:pointer">🖼️ Xem</button>';
        html += '<button onclick="event.stopPropagation();deleteKol(\'' + k.id + '\')" style="border:none;background:#fef2f2;color:#ef4444;border-radius:4px;padding:4px 8px;font-size:.75em;cursor:pointer">🗑️</button>';
        html += '</div></div></div>';
    });
    html += '</div>';
    container.innerHTML = html;
}

function toggleKolSelect(kolId) {
    var idx = movieState.selectedKols.indexOf(kolId);
    if (idx >= 0) {
        movieState.selectedKols.splice(idx, 1);
    } else {
        movieState.selectedKols.push(kolId);
    }
    renderKolList();
    updateStepStatus();
}

async function uploadKolProfile() {
    var name = document.getElementById('kol-name').value.trim();
    var desc = document.getElementById('kol-desc').value.trim();
    var files = document.getElementById('kol-images').files;

    if (!name) { alert('Nhập tên KOL'); return; }
    if (files.length < 1) { alert('Cần ít nhất 1 ảnh reference'); return; }

    var btn = document.getElementById('btn-add-kol');
    btn.disabled = true;
    btn.textContent = '⏳ Đang tải...';

    var fd = new FormData();
    fd.append('name', name);
    fd.append('description', desc);
    for (var i = 0; i < files.length; i++) {
        fd.append('images', files[i]);
    }

    try {
        var resp = await fetch('/api/movie/kol/', { method: 'POST', body: fd });
        if (!resp.ok) {
            var err = await resp.json();
            throw new Error(err.detail || 'Upload failed');
        }
        document.getElementById('kol-name').value = '';
        document.getElementById('kol-desc').value = '';
        document.getElementById('kol-images').value = '';
        document.getElementById('kol-upload-preview').innerHTML = '';
        await loadKolList();
    } catch (e) {
        alert('Lỗi: ' + e.message);
    } finally {
        btn.disabled = false;
        btn.textContent = '➕ Thêm KOL';
    }
}

async function deleteKol(kolId) {
    if (!confirm('Xóa KOL này? Không thể hoàn tác.')) return;
    try {
        await fetch('/api/movie/kol/' + kolId, { method: 'DELETE' });
        movieState.selectedKols = movieState.selectedKols.filter(function (id) { return id !== kolId; });
        await loadKolList();
    } catch (e) {
        alert('Lỗi: ' + e.message);
    }
}

function viewKolImages(kolId) {
    var kol = movieState.kols.find(function (k) { return k.id === kolId; });
    if (!kol) return;
    var dialog = document.getElementById('kol-images-dialog');
    var content = document.getElementById('kol-images-content');
    var html = '<h3 style="margin:0 0 12px">' + kol.name + '</h3>';
    html += '<div style="display:flex;flex-wrap:wrap;gap:8px">';
    kol.turnaround_images.forEach(function (url) {
        html += '<img src="' + url + '" style="height:200px;border-radius:8px;object-fit:cover">';
    });
    html += '</div>';
    content.innerHTML = html;
    dialog.showModal();
}

function previewKolImages(input) {
    var container = document.getElementById('kol-upload-preview');
    container.innerHTML = '';
    if (!input.files.length) return;
    var html = '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px">';
    for (var i = 0; i < Math.min(input.files.length, 8); i++) {
        var url = URL.createObjectURL(input.files[i]);
        html += '<img src="' + url + '" style="height:60px;border-radius:4px;object-fit:cover">';
    }
    html += '</div>';
    html += '<span style="font-size:.8em;color:#666">' + input.files.length + ' ảnh đã chọn</span>';
    container.innerHTML = html;
}
