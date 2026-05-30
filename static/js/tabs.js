/* Tab switching and UI navigation */

function switchTab(name) {
    var tabs = document.getElementsByClassName('tab');
    for (var i = 0; i < tabs.length; i++) tabs[i].className = 'tab';
    var panels = document.getElementsByClassName('panel');
    for (var i = 0; i < panels.length; i++) panels[i].className = 'panel';
    var tab = document.querySelector('[data-tab="' + name + '"]');
    if (tab) tab.className = 'tab active';
    var panel = document.getElementById('panel-' + name);
    if (panel) panel.className = 'panel active';
    var voiceBar = document.getElementById('voice-settings-bar');
    if (voiceBar) voiceBar.style.display = (name === 'history') ? 'none' : 'flex';
    var voiceSel = document.getElementById('global-voice-type');
    if (voiceSel) {
        voiceSel.value = (name === 'batch') ? 'elevenlabs' : 'edge';
        voiceSel.disabled = (name === 'batch');
        if (typeof onGlobalVoiceChange === 'function') onGlobalVoiceChange();
    }
}

function copyText(id) {
    const el = document.getElementById(id);
    const text = el.value || el.textContent;
    navigator.clipboard.writeText(text);
    const btn = el.closest('.result-card').querySelector('.copy-btn');
    btn.textContent = '✅ Đã copy!';
    setTimeout(() => btn.textContent = '📋 Copy', 1500);
}
