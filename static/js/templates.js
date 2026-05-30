/* Video template save/load/delete */

async function loadTemplateList() {
    try {
        const resp = await fetch('/api/templates');
        const data = await resp.json();
        const sel = document.getElementById('template-list');
        if (!sel) return;
        sel.innerHTML = '<option value="">Chọn template...</option>';
        (data.templates || []).forEach(t => {
            sel.innerHTML += `<option value="${t.name}">${t.name}</option>`;
        });
    } catch (e) { }
}

function getVideoConfig() {
    return {
        aspect_ratio: document.getElementById('video-aspect')?.value,
        duration: document.getElementById('video-duration')?.value,
        music_volume: document.getElementById('music-volume')?.value,
        voice_speed: document.getElementById('voice-speed')?.value,
        img_transition: document.getElementById('img-transition')?.value,
        subtitle_style: document.getElementById('subtitle-style')?.value,
        highlight_color: document.getElementById('highlight-color')?.value,
        img_effect: document.getElementById('img-effect')?.value,
        img_style: document.getElementById('img-style')?.value,
        show_intro: document.getElementById('show-intro')?.checked,
        show_outro: document.getElementById('show-outro')?.checked,
        logo_position: document.getElementById('logo-position')?.value,
    };
}

function applyVideoConfig(cfg) {
    if (!cfg) return;
    const sets = {
        'video-aspect': cfg.aspect_ratio, 'video-duration': cfg.duration,
        'music-volume': cfg.music_volume, 'voice-speed': cfg.voice_speed,
        'img-transition': cfg.img_transition, 'subtitle-style': cfg.subtitle_style,
        'highlight-color': cfg.highlight_color, 'img-effect': cfg.img_effect,
        'logo-position': cfg.logo_position,
    };
    for (const [id, val] of Object.entries(sets)) {
        const el = document.getElementById(id);
        if (el && val !== undefined) el.value = val;
    }
    if (cfg.show_intro !== undefined) document.getElementById('show-intro').checked = cfg.show_intro;
    if (cfg.show_outro !== undefined) document.getElementById('show-outro').checked = cfg.show_outro;
    ['dur-val', 'vol-val', 'voice-speed-val', 'img-speed-val'].forEach(id => {
        const el = document.getElementById(id);
        const input = el?.parentElement?.querySelector('input[type=range]');
        if (el && input) el.textContent = input.value;
    });
}

async function saveTemplate() {
    const name = document.getElementById('template-name')?.value?.trim();
    if (!name) { alert('Nhập tên template!'); return; }
    const fd = new FormData();
    fd.append('name', name);
    fd.append('config', JSON.stringify(getVideoConfig()));
    await fetch('/api/templates', { method: 'POST', body: fd });
    loadTemplateList();
}

async function loadTemplate() {
    const name = document.getElementById('template-list')?.value;
    if (!name) return;
    const resp = await fetch(`/api/templates/${name}`);
    const cfg = await resp.json();
    applyVideoConfig(cfg);
}

async function deleteTemplate() {
    const name = document.getElementById('template-list')?.value;
    if (!name) return;
    await fetch(`/api/templates/${name}`, { method: 'DELETE' });
    loadTemplateList();
}

// Auto-cut Video
async function autoCutVideo() {
    const file = document.getElementById('autocut-video')?.files?.[0];
    if (!file) { alert('Chọn video trước!'); return; }
    const st = document.getElementById('autocut-status');
    st.textContent = '⏳ Đang cắt...';
    try {
        const fd = new FormData();
        fd.append('video', file);
        fd.append('max_duration', document.getElementById('video-duration')?.value || '30');
        const resp = await fetch('/auto-cut-video', { method: 'POST', body: fd });
        const data = await resp.json();
        st.textContent = `✅ ${data.original_duration}s → ${data.cut_duration}s`;
        document.getElementById('autocut-result').innerHTML = `
            <video controls style="max-width:300px;border-radius:8px"><source src="${data.video_url}" type="video/mp4"></video>
            <br><a href="${data.video_url}" download style="font-size:.85em">⬇️ Tải video đã cắt</a>`;
    } catch (e) { st.textContent = '❌ ' + e.message; }
}
