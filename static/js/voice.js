/* Voice settings: TTS engine selection, ElevenLabs voices */

function onGlobalVoiceChange() {
    var sel = document.getElementById('global-voice-type');
    document.getElementById('global-el-voice').style.display = sel.value === 'elevenlabs' ? '' : 'none';
    document.getElementById('global-edge-voice').style.display = sel.value === 'edge' ? '' : 'none';
}

function getGlobalVoice() {
    var type = document.getElementById('global-voice-type')?.value || 'edge';
    var voiceId = document.getElementById('global-el-voice')?.value || '';
    var edgeVoice = document.getElementById('global-edge-voice')?.value || 'vi-VN-HoaiMyNeural';
    var speed = document.getElementById('global-voice-speed')?.value || '40';
    return { type: type, voiceId: voiceId, edgeVoice: edgeVoice, speed: speed };
}

function loadGlobalVoices() {
    fetch('/api/elevenlabs-voices').then(r => r.json()).then(d => {
        var sel = document.getElementById('global-el-voice');
        var defaultId = 'T4jrQr9x0Y24833yKCWR';
        sel.innerHTML = '';
        (d.voices || []).forEach(v => {
            var opt = document.createElement('option');
            opt.value = v.id;
            opt.textContent = v.name + (v.category ? ' (' + v.category + ')' : '');
            sel.appendChild(opt);
        });
        sel.value = defaultId;
        if (!sel.value && sel.options.length) sel.selectedIndex = 0;
    }).catch(() => {
        document.getElementById('global-el-voice').innerHTML = '<option value="">Không tải được</option>';
    });
}

function toggleELVoices(sel, platform) {
    var elSel = document.getElementById('el-voice-' + platform);
    if (sel.value === 'elevenlabs') {
        elSel.style.display = '';
        if (window._elVoicesLoaded && window._elVoicesCache.length) {
            if (!elSel.dataset.populated) {
                elSel.innerHTML = '';
                for (var j = 0; j < window._elVoicesCache.length; j++) {
                    var v = window._elVoicesCache[j];
                    var opt = document.createElement('option');
                    opt.value = v.id;
                    opt.textContent = v.name + (v.category ? ' (' + v.category + ')' : '');
                    elSel.appendChild(opt);
                }
                elSel.dataset.populated = '1';
            }
        } else if (!window._elVoicesLoaded) {
            elSel.innerHTML = '<option value="">Đang tải giọng...</option>';
            fetch('/api/elevenlabs-voices').then(function (r) { return r.json(); }).then(function (d) {
                window._elVoicesLoaded = true;
                window._elVoicesCache = d.voices || [];
                var allSels = document.querySelectorAll('[id^="el-voice-"]');
                for (var i = 0; i < allSels.length; i++) {
                    var s = allSels[i];
                    s.innerHTML = '';
                    for (var j = 0; j < window._elVoicesCache.length; j++) {
                        var v = window._elVoicesCache[j];
                        var opt = document.createElement('option');
                        opt.value = v.id;
                        opt.textContent = v.name + (v.category ? ' (' + v.category + ')' : '');
                        s.appendChild(opt);
                    }
                    s.dataset.populated = '1';
                    if (window._elVoicesCache.length === 0) s.innerHTML = '<option value="">Không có giọng</option>';
                }
            }).catch(function (e) {
                elSel.innerHTML = '<option value="">Lỗi: ' + e.message + '</option>';
            });
        }
    } else {
        elSel.style.display = 'none';
    }
}

async function generateSpeech(platform) {
    const textarea = document.getElementById('post-' + platform);
    const text = textarea.value.trim();
    if (!text) { alert('Nhập nội dung trước!'); return; }
    const voice = getGlobalVoice();
    const btn = document.getElementById('btn-speech-' + platform);
    const audioDiv = document.getElementById('audio-' + platform);
    btn.disabled = true;
    btn.textContent = '⏳ Đang tạo...';
    try {
        const fd = new FormData();
        fd.append('text', text);
        fd.append('platform', platform);
        fd.append('voice_type', voice.type);
        fd.append('speed', 100 + parseInt(voice.speed));
        fd.append('edge_voice', voice.edgeVoice);
        if (voice.type === 'elevenlabs' && voice.voiceId) fd.append('elevenlabs_voice_id', voice.voiceId);
        const resp = await fetch('/generate-speech', { method: 'POST', body: fd });
        if (!resp.ok) { const err = await resp.json(); throw new Error(err.detail || 'Lỗi'); }
        const data = await resp.json();
        audioDiv.innerHTML = `<audio controls style="height:36px"><source src="${data.audio_url}" type="audio/mpeg"></audio><a href="${data.audio_url}" download style="font-size:.85em;margin-left:4px">⬇️</a>`;
        if (window._lastReviewData && window._lastReviewData[platform]) {
            window._lastReviewData[platform].audio_url = data.audio_url;
            window._lastReviewData[platform].social_post = text;
        }
    } catch (e) {
        audioDiv.innerHTML = `<span style="color:red;font-size:.85em">❌ ${e.message}</span>`;
    } finally {
        btn.disabled = false;
        btn.textContent = '🔊 Tạo giọng nói';
    }
}
