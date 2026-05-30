/* Music browsing and playback */

async function loadMusicList(category, query, refresh) {
    try {
        const q = query || document.getElementById('music-search')?.value || '';
        const cat = category || '';
        const src = document.getElementById('music-source')?.value || 'freesound';
        const r = refresh ? '&refresh=true' : '';
        const resp = await fetch(`/api/music?category=${encodeURIComponent(cat)}&q=${encodeURIComponent(q)}&source=${src}${r}`);
        const data = await resp.json();
        const sel = document.getElementById('music-select');
        const catSel = document.getElementById('music-category');
        if (!sel) return;
        sel.innerHTML = '<option value="">Không nhạc nền</option>';
        if (data.error) {
            sel.innerHTML += `<option disabled>⚠️ ${data.error}</option>`;
        }
        (data.tracks || []).forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.url;
            opt.textContent = `🎵 ${t.name}${t.duration ? ' (' + Math.round(t.duration) + 's)' : ''}`;
            sel.appendChild(opt);
        });
        if (catSel.options.length <= 1 && data.categories) {
            data.categories.forEach(c => {
                const opt = document.createElement('option');
                opt.value = c;
                opt.textContent = c.charAt(0).toUpperCase() + c.slice(1);
                catSel.appendChild(opt);
            });
        }
    } catch (e) { }
}

function previewMusic() {
    const sel = document.getElementById('music-select');
    const audio = document.getElementById('music-preview');
    if (!sel.value) { audio.pause(); return; }
    audio.src = sel.value;
    audio.style.display = 'block';
    audio.style.width = '100%';
    audio.style.marginTop = '8px';
    audio.play();
}

function stopMusic() {
    const audio = document.getElementById('music-preview');
    audio.pause();
    audio.currentTime = 0;
}
