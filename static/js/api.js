/* API call helpers and data fetchers */

function loadPlatforms() {
    fetch('/api/platforms').then(r => r.json()).then(d => {
        window._igConnected = !!(d.instagram && d.instagram.connected);
        ['tiktok', 'youtube', 'facebook', 'instagram', 'threads'].forEach(function (p) {
            var el = document.getElementById('plat-' + p);
            if (!el) return;
            var info = d[p] || {};
            var label = p.charAt(0).toUpperCase() + p.slice(1);
            if (info.connected) {
                el.textContent = '✅ ' + label + (info.name ? ' (' + info.name + ')' : '');
                if (p !== 'instagram') {
                    var a = document.createElement('a');
                    a.href = '#'; a.textContent = ' ngắt'; a.style.cssText = 'font-size:.8em;color:#999';
                    a.onclick = function (e) { e.preventDefault(); disconnectPlatform(p); };
                    el.appendChild(a);
                }
            } else {
                if (p === 'instagram') {
                    el.textContent = '❌ ' + label + ' ';
                    var s = document.createElement('span');
                    s.textContent = '(liên kết qua Facebook)';
                    s.style.cssText = 'font-size:.8em;color:#999';
                    el.appendChild(s);
                } else {
                    el.textContent = '❌ ' + label + ' ';
                    var a = document.createElement('a');
                    a.href = '/connect/' + p; a.target = '_blank'; a.textContent = 'kết nối';
                    a.style.cssText = 'font-size:.8em;color:#e94560';
                    a.onclick = function () { setTimeout(loadPlatforms, 5000); };
                    el.appendChild(a);
                }
            }
        });
    }).catch(function () { });
}

function disconnectPlatform(p) {
    fetch('/disconnect/' + p, { method: 'POST' }).then(function () { loadPlatforms(); });
}

function loadModels() {
    fetch('/api/models').then(r => r.json()).then(d => {
        var sel = document.getElementById('gemini-model');
        sel.innerHTML = '';
        var models = d.models || [];
        var current = d.current || 'gemini-2.5-flash-lite';
        models.forEach(function (m) {
            var opt = document.createElement('option');
            opt.value = m; opt.textContent = m;
            if (m === current) opt.selected = true;
            sel.appendChild(opt);
        });
    });
}

function loadKolStatus() {
    fetch('/api/kol-status').then(r => r.json()).then(d => {
        var count = d.count || 0;
        document.getElementById('kol-status-1').textContent = count >= 1 ? 'KOL 1 ✅' : 'KOL 1';
        document.getElementById('kol-status-2').textContent = count >= 2 ? 'KOL 2 ✅' : 'KOL 2';
    }).catch(() => { });
}

function loadReviewStyles() {
    fetch('/admin/prompts/api/list').then(r => r.json()).then(d => {
        var sel = document.getElementById('review-style-select');
        (d.presets || []).forEach(p => {
            var opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.name;
            sel.appendChild(opt);
        });
    }).catch(() => { });
}

function loadFbPageSelect(selectId) {
    fetch('/api/facebook-pages').then(r => r.json()).then(d => {
        var sel = document.getElementById(selectId);
        if (!sel || !d.pages || d.pages.length <= 1) return;
        sel.innerHTML = '';
        d.pages.forEach(function (p) {
            var opt = document.createElement('option');
            opt.value = p.page_id;
            opt.textContent = p.name;
            sel.appendChild(opt);
        });
    }).catch(() => { });
}
